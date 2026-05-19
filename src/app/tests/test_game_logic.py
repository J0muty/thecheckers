import asyncio

from src.app.game.draw_logic import initial_draw_state, update_draw_state
from src.app.game.game_logic import (
    apply_move,
    game_status,
    generate_turn_sequences,
    opponent,
    piece_capture_moves,
    rebuild_board_from_moves,
)
from src.app.game.bot_arena import ArenaBot, run_match
from src.app.game.bot_memory import MoveMemory, outcome_score
from src.app.game.bot_profiles import profile_for_difficulty
from src.app.game.single_logic import bot_turn, choose_turn, evaluate_board


def empty_board():
    return [[None for _ in range(8)] for _ in range(8)]


def board_with(*pieces):
    board = empty_board()
    for row, col, piece in pieces:
        board[row][col] = piece
    return board


def advance_draw_state(board, turns):
    state = initial_draw_state(board, "white")
    current_board = board
    current_player = "white"
    status = None
    for new_board, moved_piece_was_king, was_capture, was_promotion in turns:
        next_player = opponent(current_player)
        state, status = update_draw_state(
            state,
            current_board,
            new_board,
            current_player,
            next_player,
            moved_piece_was_king=moved_piece_was_king,
            was_capture=was_capture,
            was_promotion=was_promotion,
        )
        current_board = new_board
        current_player = next_player
    return state, status


def test_only_kings_is_not_automatic_draw():
    board = empty_board()
    board[2][1] = 'W'
    board[5][6] = 'B'

    assert game_status(board) is None


def test_forced_chain_must_continue_with_same_piece():
    board = empty_board()
    board[5][0] = 'w'
    board[5][4] = 'w'
    board[4][1] = 'b'
    board[4][5] = 'b'
    board[2][3] = 'b'

    board_after_first, captured = apply_move(board, (5, 0), (3, 2), 'white')
    blocked = [captured]

    try:
        apply_move(
            board_after_first,
            (5, 4),
            (3, 6),
            'white',
            blocked_positions=blocked,
            forced_start=(3, 2),
        )
    except ValueError as exc:
        assert 'Нужно продолжить взятие той же шашкой' in str(exc)
    else:
        raise AssertionError('switching to another piece during a capture chain must be rejected')


def test_king_cannot_move_through_square_of_already_captured_piece():
    board = empty_board()
    board[5][2] = 'W'
    board[4][3] = 'b'
    board[6][1] = 'b'

    board_after_first, captured = apply_move(board, (5, 2), (2, 5), 'white')

    assert piece_capture_moves(board_after_first, (2, 5), 'white') == [(7, 0)]
    assert piece_capture_moves(
        board_after_first,
        (2, 5),
        'white',
        blocked_positions=[captured],
    ) == []


def test_rebuild_board_replays_history_from_initial_position():
    moves = [
        ((5, 0), (4, 1)),
        ((2, 1), (3, 0)),
    ]

    board = rebuild_board_from_moves(moves)

    assert board[4][1] == 'w'
    assert board[3][0] == 'b'
    assert board[5][0] is None
    assert board[2][1] is None


def test_hard_bot_prefers_longer_capture_sequence():
    board = empty_board()
    board[5][0] = 'w'
    board[5][4] = 'w'
    board[4][1] = 'b'
    board[4][5] = 'b'
    board[2][3] = 'b'

    final_board, starts, ends = asyncio.run(bot_turn(board, 'white', 'hard'))

    assert starts == [(5, 0), (3, 2)]
    assert ends == [(3, 2), (1, 4)]
    assert final_board[1][4] == 'w'
    assert final_board[3][6] is None


def test_hard_bot_avoids_simple_hanging_move():
    board = empty_board()
    board[5][2] = 'w'
    board[3][4] = 'b'

    choice = choose_turn(board, 'white', 'hard')

    assert choice.steps == (((5, 2), (4, 1)),)


def test_hardcore_profile_rewards_active_king_more_than_hard():
    board = board_with((3, 2, 'W'), (0, 7, 'B'))

    hard_score = evaluate_board(board, 'white', profile_for_difficulty('hard').weights)
    hardcore_score = evaluate_board(board, 'white', profile_for_difficulty('hardcore').weights)

    assert hardcore_score > hard_score


def test_hardcore_bot_can_search_with_arena_limits():
    board = board_with((5, 0, 'w'), (2, 1, 'b'), (2, 5, 'b'))

    choice = choose_turn(board, 'white', 'hardcore', max_depth=1, time_limit=0.05)

    assert choice is not None


def test_bot_arena_produces_progress_report():
    hardcore = ArenaBot(
        'candidate',
        'hardcore',
        profile_for_difficulty('hardcore'),
        max_depth=1,
        time_limit=0.02,
    )
    hard = ArenaBot(
        'baseline',
        'hard',
        profile_for_difficulty('hard'),
        max_depth=1,
        time_limit=0.02,
    )

    report = run_match(hardcore, hard, games=2, max_plies=2, seed=7, record_moves=False)

    assert report['summary']['games'] == 2
    assert set(report['summary']['wins']) == {'candidate', 'baseline', 'draws'}
    assert len(report['games']) == 2


def test_move_memory_can_choose_between_safe_moves():
    board = board_with((5, 2, 'w'), (2, 5, 'b'))
    memory = MoveMemory()
    bad_steps = (((5, 2), (4, 1)),)
    good_steps = (((5, 2), (4, 3)),)
    for _ in range(5):
        memory.record(board, 'white', bad_steps, -1.0)
        memory.record(board, 'white', good_steps, 1.0)

    choice = choose_turn(
        board,
        'white',
        'hardcore',
        max_depth=1,
        time_limit=0.05,
        memory=memory,
        memory_strength=10_000,
        use_default_memory=False,
    )

    assert choice.steps == good_steps


def test_move_memory_shares_mirrored_black_and_white_positions():
    white_board = board_with((5, 2, 'w'), (2, 5, 'b'))
    black_board = board_with((2, 5, 'b'), (5, 2, 'w'))
    memory = MoveMemory()
    white_steps = (((5, 2), (4, 3)),)
    black_steps = (((2, 5), (3, 4)),)

    memory.record(white_board, 'white', white_steps, 1.0)

    assert memory.average_score(black_board, 'black', black_steps) == 1.0


def test_move_memory_cannot_force_simple_hanging_move():
    board = board_with((5, 2, 'w'), (3, 0, 'b'))
    memory = MoveMemory()
    safe_steps = (((5, 2), (4, 3)),)
    hanging_steps = (((5, 2), (4, 1)),)
    for _ in range(10):
        memory.record(board, 'white', safe_steps, -1.0)
        memory.record(board, 'white', hanging_steps, 1.0)

    choice = choose_turn(
        board,
        'white',
        'hardcore',
        max_depth=1,
        time_limit=0.05,
        memory=memory,
        memory_strength=10_000,
        use_default_memory=False,
    )

    assert choice.steps == safe_steps


def test_hardcore_bot_avoids_immediate_uncompensated_hang():
    board = board_with(
        (0, 1, 'b'),
        (0, 3, 'b'),
        (0, 5, 'b'),
        (0, 7, 'b'),
        (1, 0, 'b'),
        (1, 6, 'b'),
        (2, 1, 'b'),
        (2, 3, 'b'),
        (2, 5, 'b'),
        (2, 7, 'b'),
        (3, 4, 'b'),
        (4, 3, 'w'),
        (5, 2, 'w'),
        (5, 6, 'w'),
        (6, 1, 'w'),
        (6, 3, 'w'),
        (6, 5, 'w'),
        (6, 7, 'w'),
        (7, 0, 'w'),
        (7, 2, 'w'),
        (7, 4, 'w'),
        (7, 6, 'w'),
    )

    choice = choose_turn(
        board,
        'white',
        'hardcore',
        max_depth=3,
        time_limit=0.2,
        use_default_memory=False,
    )

    assert choice.steps != (((4, 3), (3, 2)),)
    opponent_captures = [seq for seq in generate_turn_sequences(choice.board, 'black') if seq.is_capture]
    assert not any((4, 3) in seq.captured_positions for seq in opponent_captures)


def test_bot_arena_updates_learning_memory():
    memory = MoveMemory()
    hardcore = ArenaBot(
        'candidate',
        'hardcore',
        profile_for_difficulty('hardcore'),
        max_depth=1,
        time_limit=0.02,
        memory=memory,
    )
    hard = ArenaBot(
        'baseline',
        'hard',
        profile_for_difficulty('hard'),
        max_depth=1,
        time_limit=0.02,
    )

    run_match(hardcore, hard, games=1, max_plies=2, seed=7, record_moves=False, opening_plies=0)

    assert memory.total_updates > 0
    assert memory.position_count > 0


def test_draws_are_a_small_learning_penalty():
    assert outcome_score('draw', 'white') < 0
    assert outcome_score('white_win', 'white') > 0
    assert outcome_score('black_win', 'white') < outcome_score('draw', 'white')


def test_draw_pressure_revalues_old_neutral_draws():
    board = board_with((5, 2, 'w'), (2, 5, 'b'))
    memory = MoveMemory()
    steps = (((5, 2), (4, 3)),)
    memory.record(board, 'white', steps, 0.0)
    memory.record(board, 'white', steps, 0.0)

    changed = memory.apply_draw_pressure(-0.15)

    assert changed == 1
    assert memory.average_score(board, 'white', steps) == -0.15


def test_paired_openings_reuse_the_same_opening_line():
    hardcore = ArenaBot(
        'candidate',
        'hardcore',
        profile_for_difficulty('hardcore'),
        max_depth=1,
        time_limit=0.02,
    )
    hard = ArenaBot(
        'baseline',
        'hard',
        profile_for_difficulty('hard'),
        max_depth=1,
        time_limit=0.02,
    )

    report = run_match(
        hardcore,
        hard,
        games=2,
        max_plies=4,
        seed=9,
        opening_plies=2,
        paired_openings=True,
    )

    assert report['games'][0]['moves'][:2] == report['games'][1]['moves'][:2]


def test_draw_on_third_position_repetition():
    board = board_with((5, 0, 'W'), (2, 7, 'B'))
    turns = [
        (board_with((4, 1, 'W'), (2, 7, 'B')), True, False, False),
        (board_with((4, 1, 'W'), (3, 6, 'B')), True, False, False),
        (board_with((5, 0, 'W'), (3, 6, 'B')), True, False, False),
        (board_with((5, 0, 'W'), (2, 7, 'B')), True, False, False),
        (board_with((4, 1, 'W'), (2, 7, 'B')), True, False, False),
        (board_with((4, 1, 'W'), (3, 6, 'B')), True, False, False),
        (board_with((5, 0, 'W'), (3, 6, 'B')), True, False, False),
        (board_with((5, 0, 'W'), (2, 7, 'B')), True, False, False),
    ]

    _, status = advance_draw_state(board, turns)

    assert status == 'draw'


def test_draw_after_fifteen_king_only_moves():
    board = board_with((7, 0, 'W'), (0, 7, 'B'))
    white_path = [(6, 1), (5, 0), (4, 1), (3, 0), (2, 1), (1, 0), (0, 1), (1, 2)]
    black_path = [(1, 6), (2, 7), (3, 6), (4, 7), (5, 6), (6, 7), (7, 6)]

    turns = []
    white_pos = (7, 0)
    black_pos = (0, 7)
    for index in range(15):
        if index % 2 == 0:
            white_pos = white_path[index // 2]
        else:
            black_pos = black_path[index // 2]
        turns.append((board_with((white_pos[0], white_pos[1], 'W'), (black_pos[0], black_pos[1], 'B')), True, False, False))

    _, status = advance_draw_state(board, turns)

    assert status == 'draw'


def test_draw_after_five_moves_in_king_vs_king_endgame():
    board = board_with((6, 1, 'W'), (1, 6, 'B'))
    white_path = [(5, 0), (4, 1), (3, 0), (2, 1), (1, 0)]
    black_path = [(2, 7), (3, 6), (4, 7), (5, 6), (6, 7)]

    turns = []
    white_pos = (6, 1)
    black_pos = (1, 6)
    for index in range(10):
        if index % 2 == 0:
            white_pos = white_path[index // 2]
        else:
            black_pos = black_path[index // 2]
        turns.append((board_with((white_pos[0], white_pos[1], 'W'), (black_pos[0], black_pos[1], 'B')), True, False, False))

    _, status = advance_draw_state(board, turns)

    assert status == 'draw'


def test_draw_after_thirty_no_progress_moves_in_four_piece_endgame():
    board = board_with((6, 1, 'W'), (5, 4, 'w'), (1, 6, 'B'), (2, 3, 'b'))
    state = initial_draw_state(board, "white")
    state["no_progress_moves"] = 29
    new_board = board_with((5, 0, 'W'), (5, 4, 'w'), (1, 6, 'B'), (2, 3, 'b'))

    _, status = update_draw_state(
        state,
        board,
        new_board,
        "white",
        "black",
        moved_piece_was_king=True,
        was_capture=False,
        was_promotion=False,
    )

    assert status == 'draw'


def test_draw_after_five_long_diagonal_attacker_moves():
    board = board_with((6, 1, 'W'), (6, 3, 'W'), (6, 5, 'w'), (2, 5, 'B'))
    state = initial_draw_state(board, "white")
    state["regulation"] = {
        "type": "long_diagonal_five",
        "attacker": "white",
        "limit": 5,
        "attacker_moves": 4,
    }
    new_board = board_with((5, 0, 'W'), (6, 3, 'W'), (6, 5, 'w'), (2, 5, 'B'))

    _, status = update_draw_state(
        state,
        board,
        new_board,
        "white",
        "black",
        moved_piece_was_king=True,
        was_capture=False,
        was_promotion=False,
    )

    assert status == 'draw'
