from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from src.app.game.bot_profiles import (
        BotProfile,
        TUNABLE_WEIGHT_FIELDS,
        load_profile,
        profile_for_difficulty,
        profile_to_dict,
        save_profile,
        weights_from_mapping,
        weights_to_dict,
    )
    from src.app.game.bot_memory import DEFAULT_MEMORY_PATH, MoveMemory, outcome_score, project_path
    from src.app.game.game_logic import (
        Board,
        create_initial_board,
        format_move,
        game_status,
        generate_turn_sequences,
        opponent,
    )
    from src.app.game.single_logic import (
        captured_material,
        choose_turn,
        evaluate_board,
        root_safety_penalty,
        root_tactical_bonus,
    )
else:
    from .bot_profiles import (
        BotProfile,
        TUNABLE_WEIGHT_FIELDS,
        load_profile,
        profile_for_difficulty,
        profile_to_dict,
        save_profile,
        weights_from_mapping,
        weights_to_dict,
    )
    from .bot_memory import DEFAULT_MEMORY_PATH, MoveMemory, outcome_score, project_path
    from .game_logic import Board, create_initial_board, format_move, game_status, generate_turn_sequences, opponent
    from .single_logic import captured_material, choose_turn, evaluate_board, root_safety_penalty, root_tactical_bonus

ArenaObserver = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class ArenaBot:
    name: str
    difficulty: str
    profile: BotProfile
    max_depth: int = 4
    time_limit: float = 0.05
    memory: MoveMemory | None = None
    memory_strength: int = 700
    learn: bool = True
    exploration: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _winner(status: str) -> str:
    if status == "white_win":
        return "white"
    if status == "black_win":
        return "black"
    return "draw"


def _material(board: Board) -> dict[str, int]:
    material = {"white_men": 0, "white_kings": 0, "black_men": 0, "black_kings": 0}
    for row in board:
        for piece in row:
            if piece == "w":
                material["white_men"] += 1
            elif piece == "W":
                material["white_kings"] += 1
            elif piece == "b":
                material["black_men"] += 1
            elif piece == "B":
                material["black_kings"] += 1
    return material


def _clone_board(board: Board) -> Board:
    return [row[:] for row in board]


def render_board(board: Board) -> str:
    lines = [
        "    A B C D E F G H",
        "  +-----------------+",
    ]
    for row_index, row in enumerate(board):
        rank = 8 - row_index
        cells = " ".join(piece or "." for piece in row)
        lines.append(f"{rank} | {cells} | {rank}")
    lines.extend([
        "  +-----------------+",
        "    A B C D E F G H",
    ])
    return "\n".join(lines)


def make_console_observer(delay: float = 0.25) -> ArenaObserver:
    def observer(event: dict[str, object]) -> None:
        event_type = event["type"]
        if event_type == "start":
            print()
            print(f"Game {event['game_index']}: white={event['white']} black={event['black']}", flush=True)
            print(render_board(event["board"]), flush=True)
            return

        if event_type == "move":
            print()
            print(
                f"Ply {event['ply']}: {event['player']} / {event['bot']} -> {event['move']}",
                flush=True,
            )
            print(render_board(event["board"]), flush=True)
            if delay > 0:
                time.sleep(delay)
            return

        if event_type == "end":
            print()
            print(f"Result: {event['status']} after {event['plies']} plies", flush=True)

    return observer


def _score_for_bot(status: str, bot_color: str) -> float:
    winner = _winner(status)
    if winner == "draw":
        return 0.5
    return 1.0 if winner == bot_color else 0.0


def _winner_bot(game: dict[str, object]) -> str:
    winner = str(game["winner"])
    if winner == "draw":
        return "draw"
    return str(game[winner])


def build_opening(
    *,
    opening_plies: int,
    seed: int,
    record_moves: bool = True,
) -> tuple[Board, str, int, list[str]]:
    random_state = random.getstate()
    random.seed(seed)
    try:
        board = create_initial_board()
        current = "white"
        moves: list[str] = []
        plies = 0
        status = game_status(board)
        while status is None and plies < opening_plies:
            sequences = generate_turn_sequences(board, current)
            if not sequences:
                break
            sequence = random.choice(sequences)
            if record_moves:
                moves.extend(format_move(start, end) for start, end in sequence.steps)
            board = sequence.board
            current = opponent(current)
            plies += 1
            status = game_status(board)
        return board, current, plies, moves
    finally:
        random.setstate(random_state)


def _sequence_learning_score(board: Board, player: str, sequence, profile: BotProfile) -> int:
    weights = profile.weights
    own_capture_value = captured_material(board, sequence.captured_positions, opponent(player), weights)
    safety = root_safety_penalty(
        sequence.board,
        player,
        weights,
        own_capture_value=own_capture_value,
        own_capture_count=len(sequence.captured_positions),
    )
    return (
        evaluate_board(sequence.board, player, weights)
        + root_tactical_bonus(sequence, weights)
        - safety
    )


def _immediate_learning_score(board: Board, player: str, sequence, profile: BotProfile) -> float:
    before = evaluate_board(board, player, profile.weights)
    after = _sequence_learning_score(board, player, sequence, profile)
    scaled = (after - before) / 500
    return max(-0.6, min(0.6, scaled))


def choose_arena_turn(board: Board, player: str, bot: ArenaBot):
    sequence = choose_turn(
        board,
        player,
        bot.difficulty,
        max_depth=bot.max_depth,
        time_limit=bot.time_limit,
        weights=bot.profile.weights,
        memory=bot.memory,
        memory_strength=bot.memory_strength,
        use_default_memory=False,
    )
    if (
        sequence is None
        or bot.memory is None
        or not bot.learn
        or bot.exploration <= 0
        or random.random() >= bot.exploration
    ):
        return sequence, False

    sequences = generate_turn_sequences(board, player)
    if len(sequences) < 2:
        return sequence, False

    scored = sorted(
        ((_sequence_learning_score(board, player, candidate, bot.profile), candidate) for candidate in sequences),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score = scored[0][0]
    pool = [
        candidate
        for score, candidate in scored
        if candidate.steps != sequence.steps and score >= best_score - 180
    ]
    if not pool:
        return sequence, False
    return random.choice(pool[: min(3, len(pool))]), True


def play_game(
    white: ArenaBot,
    black: ArenaBot,
    *,
    max_plies: int = 160,
    seed: int | None = None,
    record_moves: bool = True,
    observer: ArenaObserver | None = None,
    game_index: int = 1,
    opening_plies: int = 2,
    draw_score: float = -0.15,
    initial_board: Board | None = None,
    initial_player: str = "white",
    initial_plies: int = 0,
    initial_moves: list[str] | None = None,
) -> dict[str, object]:
    random_state = random.getstate()
    if seed is not None:
        random.seed(seed)

    started = time.perf_counter()
    board = _clone_board(initial_board) if initial_board is not None else create_initial_board()
    current = initial_player if initial_board is not None else "white"
    moves: list[str] = list(initial_moves or []) if record_moves else []
    learned_decisions: list[dict[str, object]] = []
    status = game_status(board)
    plies = initial_plies if initial_board is not None else 0
    if observer is not None:
        observer({
            "type": "start",
            "game_index": game_index,
            "white": white.name,
            "black": black.name,
            "board": board,
        })

    try:
        while status is None and plies < max_plies:
            bot = white if current == "white" else black
            bot_name = bot.name
            board_before = _clone_board(board)
            if initial_board is None and plies < opening_plies:
                sequences = generate_turn_sequences(board, current)
                sequence = random.choice(sequences) if sequences else None
                explored = False
                bot_name = "opening"
            else:
                sequence, explored = choose_arena_turn(board, current, bot)
            if sequence is None:
                status = f"{opponent(current)}_win"
                break

            if bot.memory is not None and bot.learn and bot_name != "opening":
                learned_decisions.append(
                    {
                        "memory": bot.memory,
                        "board": board_before,
                        "player": current,
                        "steps": sequence.steps,
                        "ply": plies + 1,
                        "immediate_score": _immediate_learning_score(board_before, current, sequence, bot.profile),
                        "explored": explored,
                    }
                )
            if record_moves:
                moves.extend(format_move(start, end) for start, end in sequence.steps)
            move_text = " ".join(format_move(start, end) for start, end in sequence.steps)
            board = sequence.board
            plies += 1
            if observer is not None:
                observer({
                    "type": "move",
                    "game_index": game_index,
                    "ply": plies,
                    "player": current,
                    "bot": bot_name,
                    "move": move_text,
                    "board": board,
                })
            current = opponent(current)
            status = game_status(board)

        if status is None:
            status = "draw"
        for decision in learned_decisions:
            memory = decision["memory"]
            assert isinstance(memory, MoveMemory)
            player = str(decision["player"])
            ply = int(decision["ply"])
            final_credit = outcome_score(status, player, draw_score=draw_score)
            final_credit *= 0.96 ** max(0, plies - ply)
            immediate_credit = float(decision.get("immediate_score", 0.0))
            credit = final_credit * 0.7 + immediate_credit * 0.3
            memory.record(
                decision["board"],
                player,
                decision["steps"],
                credit,
            )
        if observer is not None:
            observer({
                "type": "end",
                "game_index": game_index,
                "status": status,
                "plies": plies,
                "board": board,
            })
    finally:
        random.setstate(random_state)

    return {
        "white": white.name,
        "black": black.name,
        "status": status,
        "winner": _winner(status),
        "plies": plies,
        "moves": moves,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "material": _material(board),
    }


def _summarize_games(games: Iterable[dict[str, object]], bot_a: ArenaBot, bot_b: ArenaBot) -> dict[str, object]:
    game_list = list(games)
    bot_a_score = 0.0
    bot_b_score = 0.0
    bot_a_wins = bot_b_wins = draws = 0
    total_plies = 0
    total_duration = 0.0

    for game in game_list:
        white_name = str(game["white"])
        bot_a_color = "white" if white_name == bot_a.name else "black"
        score = _score_for_bot(str(game["status"]), bot_a_color)
        bot_a_score += score
        bot_b_score += 1.0 - score
        if score == 1.0:
            bot_a_wins += 1
        elif score == 0.0:
            bot_b_wins += 1
        else:
            draws += 1
        total_plies += int(game["plies"])
        total_duration += float(game["duration_ms"])

    count = len(game_list) or 1
    return {
        "games": len(game_list),
        "score": {
            bot_a.name: bot_a_score,
            bot_b.name: bot_b_score,
        },
        "wins": {
            bot_a.name: bot_a_wins,
            bot_b.name: bot_b_wins,
            "draws": draws,
        },
        "score_rate": round(bot_a_score / count, 4),
        "avg_plies": round(total_plies / count, 2),
        "avg_duration_ms": round(total_duration / count, 2),
    }


def run_match(
    bot_a: ArenaBot,
    bot_b: ArenaBot,
    *,
    games: int = 20,
    max_plies: int = 160,
    seed: int = 1,
    alternate_colors: bool = True,
    record_moves: bool = True,
    observer: ArenaObserver | None = None,
    progress: bool = False,
    progress_label: str = "game",
    opening_plies: int = 2,
    draw_score: float = -0.15,
    paired_openings: bool = True,
) -> dict[str, object]:
    played: list[dict[str, object]] = []
    index = 0
    while index < games:
        pair_board = pair_player = pair_plies = pair_moves = None
        if paired_openings and alternate_colors:
            pair_board, pair_player, pair_plies, pair_moves = build_opening(
                opening_plies=opening_plies,
                seed=seed + index // 2,
                record_moves=record_moves,
            )

        if alternate_colors and index % 2 == 1:
            pairings = [(bot_b, bot_a)]
        elif paired_openings and alternate_colors and index + 1 < games:
            pairings = [(bot_a, bot_b), (bot_b, bot_a)]
        else:
            pairings = [(bot_a, bot_b)]

        for white, black in pairings:
            if index >= games:
                break
            use_paired_opening = pair_board is not None
            current_game_index = index + 1
            game_seed = seed + index
            initial_moves = list(pair_moves or [])
            result = play_game(
                white,
                black,
                max_plies=max_plies,
                seed=game_seed,
                record_moves=record_moves,
                observer=observer,
                game_index=current_game_index,
                opening_plies=0 if use_paired_opening else opening_plies,
                draw_score=draw_score,
                initial_board=pair_board if use_paired_opening else None,
                initial_player=str(pair_player) if use_paired_opening else "white",
                initial_plies=int(pair_plies or 0) if use_paired_opening else 0,
                initial_moves=initial_moves if use_paired_opening else None,
            )
            result["winner_bot"] = _winner_bot(result)
            played.append(result)
            if progress:
                print(
                    f"{progress_label} {current_game_index}/{games}: winner_bot={result['winner_bot']} "
                    f"winner_color={result['winner']} status={result['status']} "
                    f"plies={result['plies']} duration_ms={result['duration_ms']}",
                    flush=True,
                )
            index += 1

    return {
        "created_at": _now_iso(),
        "bots": {
            bot_a.name: profile_to_dict(bot_a.profile),
            bot_b.name: profile_to_dict(bot_b.profile),
        },
        "settings": {
            "games": games,
            "max_plies": max_plies,
            "seed": seed,
            "alternate_colors": alternate_colors,
            "opening_plies": opening_plies,
            "paired_openings": paired_openings,
            "depth": bot_a.max_depth,
            "time_limit": bot_a.time_limit,
            "memory_enabled": bot_a.memory is not None,
            "memory_strength": bot_a.memory_strength if bot_a.memory is not None else 0,
            "exploration": bot_a.exploration if bot_a.memory is not None and bot_a.learn else 0.0,
            "draw_score": draw_score,
        },
        "summary": _summarize_games(played, bot_a, bot_b),
        "games": played,
    }


def mutate_profile(
    profile: BotProfile,
    rng: random.Random,
    *,
    scale: float = 0.18,
    name: str | None = None,
) -> BotProfile:
    data = weights_to_dict(profile.weights)
    for field in TUNABLE_WEIGHT_FIELDS:
        value = int(data[field])
        spread = max(1, round(abs(value) * scale))
        data[field] = max(0, value + rng.randint(-spread, spread))
    if data["king_value"] < data["man_value"] * 2:
        data["king_value"] = data["man_value"] * 2
    return BotProfile(
        name=name or f"{profile.name}_mutated",
        description=f"Mutated from {profile.name}",
        weights=weights_from_mapping(data, profile.weights),
    )


def tune_profile(
    start_profile: BotProfile,
    opponent_profile: BotProfile,
    *,
    rounds: int,
    candidates: int,
    games: int,
    depth: int,
    time_limit: float,
    max_plies: int,
    seed: int,
    scale: float,
    opening_plies: int,
    draw_score: float,
) -> tuple[BotProfile, list[dict[str, object]]]:
    rng = random.Random(seed)
    current = start_profile
    events: list[dict[str, object]] = []

    for round_index in range(1, rounds + 1):
        best_profile = current
        best_report = run_match(
            ArenaBot("candidate", "hardcore", current, depth, time_limit),
            ArenaBot("baseline", "hard", opponent_profile, depth, time_limit),
            games=games,
            max_plies=max_plies,
            seed=seed + round_index * 1000,
            record_moves=False,
            opening_plies=opening_plies,
            draw_score=draw_score,
        )
        best_score = float(best_report["summary"]["score_rate"])

        for candidate_index in range(1, candidates + 1):
            candidate = mutate_profile(
                current,
                rng,
                scale=scale,
                name=f"{current.name}_r{round_index}_c{candidate_index}",
            )
            report = run_match(
                ArenaBot("candidate", "hardcore", candidate, depth, time_limit),
                ArenaBot("baseline", "hard", opponent_profile, depth, time_limit),
                games=games,
                max_plies=max_plies,
                seed=seed + round_index * 1000 + candidate_index * 100,
                record_moves=False,
                opening_plies=opening_plies,
                draw_score=draw_score,
            )
            score = float(report["summary"]["score_rate"])
            if score > best_score:
                best_score = score
                best_profile = candidate
                best_report = report

        improved = best_profile != current
        current = best_profile
        events.append(
            {
                "round": round_index,
                "improved": improved,
                "best_score_rate": best_score,
                "best_profile": profile_to_dict(current),
                "summary": best_report["summary"],
            }
        )

    return current, events


def write_report(report: dict[str, object], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _load_named_profile(name_or_path: str) -> BotProfile:
    path = Path(name_or_path)
    if path.exists():
        return load_profile(path)
    repo_path = project_path(path)
    if repo_path.exists():
        return load_profile(repo_path)
    return profile_for_difficulty(name_or_path)


def _print_summary(report: dict[str, object], out: Path) -> None:
    summary = report["summary"]
    print(f"report: {out}")
    print(f"games: {summary['games']}")
    print(f"score_rate: {summary['score_rate']}")
    print(f"wins: {summary['wins']}")
    print(f"avg_plies: {summary['avg_plies']}")


def _memory_best_score(memory: MoveMemory) -> float:
    try:
        return float(memory.metadata.get("best_validation_score", float("-inf")))
    except (TypeError, ValueError):
        return float("-inf")


def _accept_validated_memory(
    *,
    memory: MoveMemory,
    memory_path: str | Path,
    validation_report: dict[str, object],
    min_delta: float,
) -> bool:
    score = float(validation_report["summary"]["score_rate"])
    best_score = _memory_best_score(memory)
    if score + 1e-12 < best_score + min_delta:
        print(
            f"validation: score_rate={score:.4f}, best={best_score:.4f}, rejected; memory rolled back",
            flush=True,
        )
        return False

    memory.metadata["best_validation_score"] = score
    memory.metadata["best_validation_at"] = _now_iso()
    memory.metadata["best_validation_summary"] = validation_report["summary"]
    memory.metadata["best_validation_settings"] = validation_report["settings"]
    print(f"validation: new best score_rate={score:.4f}; accepted into {project_path(memory_path)}", flush=True)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run self-play matches for checkers bot profiles.")
    parser.add_argument("--baseline", default="hard", help="Baseline profile name or JSON path.")
    parser.add_argument("--candidate", default="hardcore", help="Candidate profile name or JSON path.")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--time-limit", type=float, default=0.05)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--opening-plies", type=int, default=2, help="Random opening plies before bots take over.")
    parser.add_argument("--unpaired-openings", action="store_true", help="Disable paired openings.")
    parser.add_argument("--out", default="src/logs/bot_arena/latest.json")
    parser.add_argument("--loop", action="store_true", help="Keep running batches until stopped.")
    parser.add_argument("--same-colors", action="store_true", help="Do not alternate bot colors between games.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Pause between loop batches.")
    parser.add_argument("--tune-rounds", type=int, default=0)
    parser.add_argument("--candidates", type=int, default=6)
    parser.add_argument("--mutate-scale", type=float, default=0.18)
    parser.add_argument("--save-profile", default="", help="Where to save the best tuned profile JSON.")
    parser.add_argument("--memory", default=str(DEFAULT_MEMORY_PATH), help="Persistent move-memory JSON path.")
    parser.add_argument("--no-memory", action="store_true", help="Disable move-memory learning for candidate.")
    parser.add_argument("--memory-strength", type=int, default=700, help="How strongly learned move memory affects search.")
    parser.add_argument("--exploration", type=float, default=0.08, help="Chance to try a safe alternative move during learning.")
    parser.add_argument("--draw-score", type=float, default=-0.15, help="Learning reward for a draw; negative values discourage draw loops.")
    parser.add_argument("--no-draw-pressure", action="store_true", help="Do not revalue old pure-draw memories.")
    parser.add_argument("--validation-games", type=int, default=20, help="Benchmark games after each batch; set 0 to disable.")
    parser.add_argument("--validation-interval", type=int, default=1, help="Run validation every N batches.")
    parser.add_argument("--validation-seed", type=int, default=900_001)
    parser.add_argument("--best-min-delta", type=float, default=0.0)
    parser.add_argument("--watch", action="store_true", help="Print a live board after every move.")
    parser.add_argument("--watch-delay", type=float, default=0.25, help="Seconds to wait between watched moves.")
    parser.add_argument("--quiet", action="store_true", help="Do not print per-game progress.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline_profile = _load_named_profile(args.baseline)
    candidate_profile = _load_named_profile(args.candidate)
    move_memory = None if args.no_memory else MoveMemory.load(args.memory)
    if move_memory is not None:
        if not args.no_draw_pressure:
            changed = move_memory.apply_draw_pressure(args.draw_score)
            if changed:
                print(f"draw pressure: revalued {changed} pure-draw memories", flush=True)
        print(
            f"memory: {project_path(args.memory)} "
            f"positions={move_memory.position_count} moves={move_memory.move_count} "
            f"updates={move_memory.total_updates}",
            flush=True,
        )
    batch = 0

    while True:
        batch += 1
        batch_start_memory = move_memory.clone() if move_memory is not None else None
        print(
            f"batch {batch}: candidate={candidate_profile.name} baseline={baseline_profile.name} "
            f"games={args.games} depth={args.depth} time_limit={args.time_limit}",
            flush=True,
        )
        if args.tune_rounds > 0:
            print(
                f"tuning: rounds={args.tune_rounds} candidates={args.candidates} games_per_candidate={args.games}",
                flush=True,
            )
            candidate_profile, events = tune_profile(
                candidate_profile,
                baseline_profile,
                rounds=args.tune_rounds,
                candidates=args.candidates,
                games=args.games,
                depth=args.depth,
                time_limit=args.time_limit,
                max_plies=args.max_plies,
                seed=args.seed + batch * 10_000,
                scale=args.mutate_scale,
                opening_plies=args.opening_plies,
                draw_score=args.draw_score,
            )
        else:
            events = []

        candidate_bot = ArenaBot(
            "candidate",
            "hardcore",
            candidate_profile,
            max_depth=args.depth,
            time_limit=args.time_limit,
            memory=move_memory,
            memory_strength=args.memory_strength,
            exploration=args.exploration,
        )
        baseline_bot = ArenaBot("baseline", "hard", baseline_profile, args.depth, args.time_limit)
        report = run_match(
            candidate_bot,
            baseline_bot,
            games=args.games,
            max_plies=args.max_plies,
            seed=args.seed + batch * 100_000,
            alternate_colors=not args.same_colors,
            observer=make_console_observer(args.watch_delay) if args.watch else None,
            progress=not args.watch and not args.quiet,
            opening_plies=args.opening_plies,
            draw_score=args.draw_score,
            paired_openings=not args.unpaired_openings,
        )
        report["training"] = {
            "batch": batch,
            "tune_rounds": args.tune_rounds,
            "events": events,
        }

        out = project_path(args.out)
        write_report(report, out)
        if args.save_profile:
            save_profile(candidate_profile, project_path(args.save_profile))
        if move_memory is not None:
            should_validate = args.validation_games > 0 and batch % max(1, args.validation_interval) == 0
            if should_validate:
                if not args.quiet:
                    print(
                        f"validation: running {args.validation_games} games "
                        f"seed={args.validation_seed}",
                        flush=True,
                    )
                validation_candidate = ArenaBot(
                    "candidate",
                    "hardcore",
                    candidate_profile,
                    max_depth=args.depth,
                    time_limit=args.time_limit,
                    memory=move_memory,
                    memory_strength=args.memory_strength,
                    learn=False,
                )
                validation_report = run_match(
                    validation_candidate,
                    baseline_bot,
                    games=args.validation_games,
                    max_plies=args.max_plies,
                    seed=args.validation_seed,
                    alternate_colors=not args.same_colors,
                    record_moves=False,
                    progress=not args.quiet,
                    progress_label="validation game",
                    opening_plies=args.opening_plies,
                    draw_score=args.draw_score,
                    paired_openings=not args.unpaired_openings,
                )
                accepted = _accept_validated_memory(
                    memory=move_memory,
                    memory_path=args.memory,
                    validation_report=validation_report,
                    min_delta=args.best_min_delta,
                )
                if not accepted and batch_start_memory is not None:
                    move_memory = batch_start_memory
                else:
                    move_memory.save(args.memory)
                    print(
                        f"memory saved: positions={move_memory.position_count} "
                        f"moves={move_memory.move_count} updates={move_memory.total_updates}",
                        flush=True,
                    )
            else:
                move_memory.save(args.memory)
                print(
                    f"memory saved: positions={move_memory.position_count} "
                    f"moves={move_memory.move_count} updates={move_memory.total_updates}",
                    flush=True,
                )
        _print_summary(report, out)

        if not args.loop:
            break
        if args.sleep > 0:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
