import asyncio

from src.app.game.draw_logic import initial_draw_state, update_draw_state
from src.app.game.game_logic import (
    apply_move,
    game_status,
    opponent,
    piece_capture_moves,
    rebuild_board_from_moves,
)
from src.app.game.single_logic import bot_turn, choose_turn


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
