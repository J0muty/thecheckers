const boardElement = document.getElementById('board');
const historyList = document.getElementById('historyList');
const timer1 = document.getElementById('timer1');
const timer2 = document.getElementById('timer2');
const player1 = document.querySelector('.player1');
const player2 = document.querySelector('.player2');
const returnButton = document.getElementById('returnButton');
const resultModal = document.getElementById('resultModal');
const resultText = document.getElementById('resultText');
const resultHomeBtn = document.getElementById('resultHomeBtn');
const resultCloseBtn = document.getElementById('resultCloseBtn');
const letters = ['', 'A','B','C','D','E','F','G','H',''];
const numbers = ['', '8','7','6','5','4','3','2','1',''];
const myColor = typeof playerColor !== 'undefined' && playerColor ? playerColor : null;
const MOVE_ANIMATION_MS = 280;
const MOVE_CHAIN_PAUSE_MS = 60;
const MOVE_MODE_KEY = 'checkerMoveMode';
let dragState = null;
let moveInputMode = normalizeMoveInputMode(
    typeof window.checkerMoveMode === 'string' ? window.checkerMoveMode : readFallbackMoveInputMode()
);
storeMoveInputMode(moveInputMode);

function normalizeMoveInputMode(mode) {
    return mode === 'drag' ? 'drag' : 'click';
}

function readFallbackMoveInputMode() {
    try {
        return localStorage.getItem(MOVE_MODE_KEY);
    } catch (_) {
        return 'click';
    }
}

function storeMoveInputMode(mode) {
    window.checkerMoveMode = mode;
    try {
        localStorage.setItem(MOVE_MODE_KEY, mode);
    } catch (_) {}
}

function setMoveInputMode(mode) {
    moveInputMode = normalizeMoveInputMode(mode);
    storeMoveInputMode(moveInputMode);
    updateBoardInputModeClasses();
}

function getMoveInputMode() {
    return moveInputMode;
}

function updateBoardInputModeClasses() {
    const isDrag = getMoveInputMode() === 'drag';
    boardElement.classList.toggle('input-drag', isDrag);
    boardElement.classList.toggle('input-click', !isDrag);
}

function getDragEventPoint(event) {
    return event.touches?.[0] || event.changedTouches?.[0] || event;
}

function getDragEventId(event) {
    return event.pointerId ?? event.touches?.[0]?.identifier ?? event.changedTouches?.[0]?.identifier ?? 'mouse';
}

function isSameDragEvent(event) {
    if (!dragState) return false;
    return getDragEventId(event) === dragState.pointerId;
}

document.querySelectorAll('.player-name').forEach(el => (el.style.display = 'none'));

function toBoardCoords(r, c) {
    return myColor === 'black' ? [7 - r, 7 - c] : [r, c];
}

function fromBoardCoords(r, c) {
    return myColor === 'black' ? [7 - r, 7 - c] : [r, c];
}

let boardState = [];
let pieceSkins = {white: 'classic', black: 'classic'};
let selected = null;
let possibleMoves = [];
let timers = {white: 600, black: 600, turn: 'white'};
let timerStart = Date.now();
let timerInterval = null;
let turn = 'white';
let gameOver = false;
let multiCapture = false;
let viewingHistory = false;
let forcedPieces = [];
let viewedMoveIndex = 0;
let isPerformingAutoMove = false;
let pendingMove = false;
let animatingBoard = false;
let timeoutCheckPending = false;
let lastHistoryLen = 0;
let locallyAnimatedMove = null;
let updateQueue = Promise.resolve();

function showModal(m) {
    m.classList.add('active');
}

function hideModal(m) {
    m.classList.remove('active');
}

function withinBounds(r, c) {
    return r >= 0 && r < 8 && c >= 0 && c < 8;
}

function pieceOwner(piece) {
    return piece.toLowerCase() === 'w' ? 'white' : 'black';
}

function isOpponent(piece, player) {
    return pieceOwner(piece) !== player;
}

function pieceCaptureMovesLocal(board, r, c, player) {
    const piece = board[r][c];
    if (!piece || pieceOwner(piece) !== player) return [];
    const caps = [];
    if (piece === piece.toLowerCase()) {
        const dirs = [[-2,-2],[-2,2],[2,-2],[2,2]];
        for (const [dr, dc] of dirs) {
            const mr = r + dr/2, mc = c + dc/2;
            const nr = r + dr, nc = c + dc;
            if (withinBounds(nr, nc) && board[nr][nc] === null &&
                board[mr][mc] && isOpponent(board[mr][mc], player)) {
                    caps.push([nr, nc]);
            }
        }
    } else {
        const dirs = [[-1,-1],[-1,1],[1,-1],[1,1]];
        for (const [dr, dc] of dirs) {
            let i = r + dr, j = c + dc;
            while (withinBounds(i, j) && board[i][j] === null) {
                i += dr; j += dc;
            }
            if (withinBounds(i, j) && board[i][j] && isOpponent(board[i][j], player)) {
                let i2 = i + dr, j2 = j + dc;
                while (withinBounds(i2, j2)) {
                    if (board[i2][j2] === null) {
                        caps.push([i2, j2]);
                    } else {
                        break;
                    }
                    i2 += dr; j2 += dc;
                }
            }
        }
    }
    return caps;
}

function pieceMovesLocal(board, r, c, player) {
    const piece = board[r][c];
    if (!piece || pieceOwner(piece) !== player) return [];
    const moves = [];
    if (piece === piece.toLowerCase()) {
        const directions = piece.toLowerCase() === 'w' ? [[-1, -1], [-1, 1]] : [[1, -1], [1, 1]];
        for (const [dr, dc] of directions) {
            const nr = r + dr;
            const nc = c + dc;
            if (withinBounds(nr, nc) && board[nr][nc] === null) {
                moves.push([nr, nc]);
            }
        }
    } else {
        const dirs = [[-1,-1],[-1,1],[1,-1],[1,1]];
        for (const [dr, dc] of dirs) {
            let i = r + dr;
            let j = c + dc;
            while (withinBounds(i, j)) {
                if (board[i][j] === null) {
                    moves.push([i, j]);
                } else {
                    break;
                }
                i += dr;
                j += dc;
            }
        }
    }
    return moves;
}

function cloneBoard(board) {
    return board.map(row => [...row]);
}

function parseMoveNotation(move) {
    const [startStr, endStr] = move.split('->');
    return {
        start: [8 - parseInt(startStr.slice(1), 10), startStr.charCodeAt(0) - 65],
        end: [8 - parseInt(endStr.slice(1), 10), endStr.charCodeAt(0) - 65],
    };
}

function formatMoveNotation(start, end) {
    return `${String.fromCharCode(65 + start[1])}${8 - start[0]}->${String.fromCharCode(65 + end[1])}${8 - end[0]}`;
}

function createPieceElement(piece, boardRow) {
    const el = document.createElement('div');
    const owner = piece.toLowerCase() === 'w' ? 'white' : 'black';
    const isKing =
        piece === piece.toUpperCase() ||
        (piece.toLowerCase() === 'w' && boardRow === 0) ||
        (piece.toLowerCase() === 'b' && boardRow === 7);
    el.classList.add('piece', owner);
    if (isKing) {
        el.classList.add('king');
    }
    if (window.Checker3D) {
        window.Checker3D.enhancePiece(el, {
            skinId: pieceSkins[owner],
            color: owner,
            king: isKing,
        });
    }
    return el;
}

function boardCell(boardRow, boardCol) {
    const [displayRow, displayCol] = fromBoardCoords(boardRow, boardCol);
    return boardElement.querySelector(`[data-row="${displayRow + 1}"][data-col="${displayCol + 1}"]`);
}

function cellToBoardCoords(cell) {
    if (!cell) return null;
    const row = Number(cell.dataset.row);
    const col = Number(cell.dataset.col);
    if (!Number.isInteger(row) || !Number.isInteger(col)) return null;
    if (row === 0 || row === 9 || col === 0 || col === 9) return null;
    return toBoardCoords(row - 1, col - 1);
}

function hasPossibleMove(r, c) {
    return possibleMoves.some(m => m[0] === r && m[1] === c);
}

function canInteractWithBoard() {
    return !gameOver &&
        !viewingHistory &&
        !pendingMove &&
        !animatingBoard &&
        (!myColor || turn === myColor);
}

function applyMoveLocal(board, start, end) {
    const nextBoard = cloneBoard(board);
    const piece = nextBoard[start[0]][start[1]];
    if (!piece) {
        return { board: nextBoard, capturedPositions: [] };
    }
    nextBoard[start[0]][start[1]] = null;

    const capturedPositions = [];
    const stepRow = Math.sign(end[0] - start[0]);
    const stepCol = Math.sign(end[1] - start[1]);
    let row = start[0] + stepRow;
    let col = start[1] + stepCol;
    while (row !== end[0] || col !== end[1]) {
        if (nextBoard[row][col] !== null) {
            capturedPositions.push([row, col]);
            nextBoard[row][col] = null;
            break;
        }
        row += stepRow;
        col += stepCol;
    }

    let movedPiece = piece;
    if (movedPiece === movedPiece.toLowerCase()) {
        if (movedPiece === 'w' && end[0] === 0) movedPiece = 'W';
        if (movedPiece === 'b' && end[0] === 7) movedPiece = 'B';
    }
    nextBoard[end[0]][end[1]] = movedPiece;
    return { board: nextBoard, capturedPositions };
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function queueHandleUpdate(data) {
    updateQueue = updateQueue
        .catch(() => {})
        .then(() => handleUpdate(data));
    return updateQueue;
}

async function animateMoveStep(boardBefore, move) {
    const { start, end } = parseMoveNotation(move);
    const piece = boardBefore[start[0]][start[1]];
    if (!piece) {
        return boardBefore;
    }

    const { board: boardAfter, capturedPositions } = applyMoveLocal(boardBefore, start, end);
    boardState = boardBefore;
    renderBoard();

    const sourceCell = boardCell(start[0], start[1]);
    const targetCell = boardCell(end[0], end[1]);
    const sourcePiece = sourceCell?.querySelector('.piece');
    if (!sourceCell || !targetCell || !sourcePiece) {
        boardState = boardAfter;
        renderBoard();
        return boardAfter;
    }

    const boardRect = boardElement.getBoundingClientRect();
    const sourceRect = sourceCell.getBoundingClientRect();
    const targetRect = targetCell.getBoundingClientRect();
    const pieceRect = sourcePiece.getBoundingClientRect();
    const animatedPiece = sourcePiece.cloneNode(true);
    animatedPiece.classList.add('piece-animated');
    animatedPiece.style.left = `${sourceRect.left - boardRect.left + (sourceRect.width - pieceRect.width) / 2}px`;
    animatedPiece.style.top = `${sourceRect.top - boardRect.top + (sourceRect.height - pieceRect.height) / 2}px`;
    animatedPiece.style.width = `${pieceRect.width}px`;
    animatedPiece.style.height = `${pieceRect.height}px`;
    animatedPiece.style.transform = 'translate3d(0px, 0px, 0px)';

    sourcePiece.classList.add('piece-moving-source');
    const capturedPieces = capturedPositions
        .map(([row, col]) => boardCell(row, col)?.querySelector('.piece'))
        .filter(Boolean);
    capturedPieces.forEach(el => el.classList.add('piece-captured'));

    boardElement.appendChild(animatedPiece);
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    const dx = targetRect.left - sourceRect.left;
    const dy = targetRect.top - sourceRect.top;
    animatedPiece.style.transform = `translate3d(${dx}px, ${dy}px, 0px) scale(1.03)`;
    await wait(MOVE_ANIMATION_MS);

    animatedPiece.remove();
    boardState = boardAfter;
    renderBoard();
    return boardAfter;
}

async function playIncomingAnimations(history, previousHistoryLen) {
    if (animatingBoard || !boardState.length) return;
    let visibleCount = previousHistoryLen;
    let newMoves = history.slice(previousHistoryLen);
    if (locallyAnimatedMove && newMoves[0] === locallyAnimatedMove) {
        visibleCount += 1;
        renderHistoryProgress(history, visibleCount);
        newMoves = newMoves.slice(1);
    } else if (locallyAnimatedMove) {
        locallyAnimatedMove = null;
    }
    if (!newMoves.length || newMoves.length > 8) {
        locallyAnimatedMove = null;
        return;
    }

    animatingBoard = true;
    try {
        let currentBoard = cloneBoard(boardState);
        for (const move of newMoves) {
            currentBoard = await animateMoveStep(currentBoard, move);
            visibleCount += 1;
            renderHistoryProgress(history, visibleCount);
            if (move !== newMoves[newMoves.length - 1]) {
                await wait(MOVE_CHAIN_PAUSE_MS);
            }
        }
    } finally {
        animatingBoard = false;
        locallyAnimatedMove = null;
    }
}

function computeForcedPieces() {
    forcedPieces = [];
    if (myColor && myColor !== turn) return;
    for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
            const piece = boardState[r][c];
            if (!piece || pieceOwner(piece) !== turn) continue;
            const caps = pieceCaptureMovesLocal(boardState, r, c, turn);
            if (caps.length) {
                forcedPieces.push({row: r, col: c, moves: caps});
            }
        }
    }
    if (myColor && forcedPieces.length === 1 && forcedPieces[0].moves.length > 1) {
        selected = { row: forcedPieces[0].row, col: forcedPieces[0].col, isCapture: true };
        possibleMoves = forcedPieces[0].moves;
    }
}

async function selectPieceAt(r, c) {
    if (multiCapture) {
        if (!selected || selected.row !== r || selected.col !== c) return false;
        renderBoard();
        return true;
    }
    if (forcedPieces.length && !forcedPieces.some(p => p.row === r && p.col === c)) return false;

    const piece = boardState[r]?.[c];
    if (!piece || pieceOwner(piece) !== turn) return false;

    const caps = await fetchCaptures(r, c);
    if (caps.length) {
        possibleMoves = caps;
        selected = { row: r, col: c, isCapture: true };
    } else {
        const moves = await fetchMoves(r, c);
        if (!moves.length) return false;
        possibleMoves = moves;
        selected = { row: r, col: c, isCapture: false };
    }
    renderBoard();
    return true;
}

function selectPieceAtLocal(r, c) {
    if (multiCapture) {
        if (!selected || selected.row !== r || selected.col !== c) return false;
        renderBoard();
        return true;
    }
    if (forcedPieces.length && !forcedPieces.some(p => p.row === r && p.col === c)) return false;

    const piece = boardState[r]?.[c];
    if (!piece || pieceOwner(piece) !== turn) return false;

    if (forcedPieces.length > 0) {
        const fp = forcedPieces.find(p => p.row === r && p.col === c);
        if (!fp) return false;
        possibleMoves = fp.moves;
        selected = { row: r, col: c, isCapture: true };
    } else {
        const caps = pieceCaptureMovesLocal(boardState, r, c, turn);
        const moves = caps.length ? caps : pieceMovesLocal(boardState, r, c, turn);
        if (!moves.length) return false;
        possibleMoves = moves;
        selected = { row: r, col: c, isCapture: caps.length > 0 };
    }
    renderBoard();
    return true;
}

async function clearSelectionAfterMiss() {
    if (!multiCapture) {
        selected = null;
        possibleMoves = [];
        computeForcedPieces();
        await autoMoveIfSingle();
    }
    renderBoard();
}

function clearTransientState() {
    selected = null;
    possibleMoves = [];
    multiCapture = false;
    forcedPieces = [];
}

function renderHistoryProgress(history, visibleCount = history.length) {
    viewedMoveIndex = visibleCount;
    updateHistory(history.slice(0, visibleCount));
}

function applyForcedState(data) {
    clearTransientState();
    const hasForcedPiece = Array.isArray(data.forced_piece) && data.forced_piece.length === 2;
    const forcedMoves = Array.isArray(data.forced_moves) ? data.forced_moves : [];
    if (hasForcedPiece && forcedMoves.length && (!myColor || myColor === turn)) {
        const [row, col] = data.forced_piece;
        forcedPieces = [{ row, col, moves: forcedMoves }];
        selected = { row, col, isCapture: true };
        possibleMoves = forcedMoves;
        multiCapture = true;
        return;
    }
    computeForcedPieces();
}

async function autoMoveIfSingle() {
    if (viewingHistory || gameOver || isPerformingAutoMove || pendingMove || multiCapture || animatingBoard) return;
    if (myColor && turn !== myColor) return;
    if (forcedPieces.length === 1 && forcedPieces[0].moves.length === 1) {
        isPerformingAutoMove = true;
        try {
            const fp = forcedPieces[0];
            selected = { row: fp.row, col: fp.col, isCapture: true };
            possibleMoves = fp.moves;
            renderBoard();
            await performMove(fp.row, fp.col, fp.moves[0][0], fp.moves[0][1], true);
        } finally {
            isPerformingAutoMove = false;
        }
    }
}

function isFinishedUpdate(data) {
    return Boolean(data?.status || data?.timers?.turn === 'stopped');
}

function setGameActionsVisible(visible) {
    ['menuEnd', 'menuDraw'].forEach(id => {
        const item = document.getElementById(id);
        if (item) {
            item.hidden = !visible;
            item.setAttribute('aria-hidden', String(!visible));
        }
    });
}

async function handleUpdate(data) {
    if (data.skins && typeof data.skins === 'object') {
        pieceSkins = {...pieceSkins, ...data.skins};
    }
    const wasGameOver = gameOver;
    const wasViewingHistory = viewingHistory;
    const previousHistoryLen = lastHistoryLen;
    if (!wasViewingHistory && boardState.length && data.history.length > previousHistoryLen) {
        await playIncomingAnimations(data.history, previousHistoryLen);
    }
    const finished = isFinishedUpdate(data);
    boardState = data.board;
    timers = data.timers;
    timerStart = Date.now();
    turn = data.timers.turn;
    lastHistoryLen = data.history.length;
    renderHistoryProgress(data.history);
    viewingHistory = false;
    if (data.players) {
        if (data.players.white) player1.querySelector('.player-name').textContent = data.players.white;
        if (data.players.black) player2.querySelector('.player-name').textContent = data.players.black;
    }
    returnButton.style.display = 'none';
    if (finished) gameOver = true;
    setGameActionsVisible(!finished);
    setActivePlayer(turn);
    if (!gameOver && (turn === 'white' || turn === 'black')) {
        startTimers();
    } else {
        stopTimers();
    }
    applyForcedState(data);
    renderBoard();
    if (!gameOver && !isPerformingAutoMove) {
        await autoMoveIfSingle();
    }
    if (finished && !wasGameOver) {
        let msg = '';
        if (data.status === 'white_win') msg = 'Белые победили!';
        else if (data.status === 'black_win') msg = 'Чёрные победили!';
        else if (data.status === 'draw') msg = 'Ничья!';
        else msg = 'Игра окончена';
        resultText.textContent = msg;
        showModal(resultModal);
        stopTimers();
    }
}

async function fetchBoard() {
    const data = await (await fetch(`/api/hotseat/board/${boardId}`)).json();
    await queueHandleUpdate(data);
}

async function fetchMoves(r, c) {
    return await (await fetch(
        `/api/hotseat/moves/${boardId}?row=${r}&col=${c}&player=${turn}`
    )).json();
}

async function fetchCaptures(r, c) {
    return await (await fetch(
        `/api/hotseat/captures/${boardId}?row=${r}&col=${c}&player=${turn}`
    )).json();
}

async function performMove(startR, startC, endR, endC, isCapture) {
    if (pendingMove) return;
    pendingMove = true;
    const moveNotation = formatMoveNotation([startR, startC], [endR, endC]);
    const originalBoard = cloneBoard(boardState);
    const originalSelected = selected ? { ...selected } : null;
    const originalPossibleMoves = possibleMoves.map(move => [...move]);
    const originalForcedPieces = forcedPieces.map(piece => ({
        row: piece.row,
        col: piece.col,
        moves: piece.moves.map(move => [...move]),
    }));
    const originalMultiCapture = multiCapture;
    try {
        clearTransientState();
        animatingBoard = true;
        boardState = await animateMoveStep(originalBoard, moveNotation);
        animatingBoard = false;
        locallyAnimatedMove = moveNotation;
        const res = await fetch(`/api/hotseat/move/${boardId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: [startR, startC],
                end: [endR, endC],
                player: turn,
                history_len: lastHistoryLen
            })
        });
        const data = await res.json();
        if (!res.ok) {
            locallyAnimatedMove = null;
            boardState = originalBoard;
            selected = originalSelected;
            possibleMoves = originalPossibleMoves;
            forcedPieces = originalForcedPieces;
            multiCapture = originalMultiCapture;
            renderBoard();
            if (res.status === 409) {
                await fetchBoard();
            }
            showNotification(data.detail || 'Неверный ход', 'error');
            return;
        }
        await queueHandleUpdate(data);
        await autoMoveIfSingle();
    } catch (error) {
        locallyAnimatedMove = null;
        boardState = originalBoard;
        selected = originalSelected;
        possibleMoves = originalPossibleMoves;
        forcedPieces = originalForcedPieces;
        multiCapture = originalMultiCapture;
        renderBoard();
        showNotification('Ошибка соединения', 'error');
    } finally {
        animatingBoard = false;
        pendingMove = false;
    }
}

function renderBoard() {
    updateBoardInputModeClasses();
    boardElement.innerHTML = '';
    for (let row = 0; row < 10; row++) {
        for (let col = 0; col < 10; col++) {
            const cell = document.createElement('div');
            cell.classList.add('square');
            cell.dataset.row = row;
            cell.dataset.col = col;
            if (row === 0 || row === 9) {
                cell.classList.add('label', row === 0 ? 'label-top' : 'label-bottom');
                cell.textContent = letters[col];
            } else if (col === 0 || col === 9) {
                cell.classList.add('label', col === 0 ? 'label-left' : 'label-right');
                cell.textContent = numbers[row];
            } else {
                const r = row - 1;
                const c = col - 1;
                const [br, bc] = toBoardCoords(r, c);
                cell.classList.add((r + c) % 2 ? 'dark' : 'light');
                if (selected && selected.row === br && selected.col === bc) {
                    cell.classList.add('selected');
                }
                if (possibleMoves.some(m => m[0] === br && m[1] === bc)) {
                    cell.classList.add('highlight');
                }
                if (myColor === turn && forcedPieces.some(p => p.row === br && p.col === bc)) {
                    cell.classList.add('forced');
                }
                const piece = boardState[br][bc];
                if (piece) {
                    const p = createPieceElement(piece, br);
                    cell.appendChild(p);
                }
                cell.addEventListener('click', onCellClick);
            }
            boardElement.appendChild(cell);
        }
    }
}

async function onCellClick(e) {
    if (getMoveInputMode() === 'drag' || !canInteractWithBoard()) return;
    const coords = cellToBoardCoords(e.currentTarget);
    if (!coords) return;
    const [r, c] = coords;
    if (multiCapture && !hasPossibleMove(r, c)) return;
    if (!selected) {
        await selectPieceAt(r, c);
        return;
    }
    if (hasPossibleMove(r, c)) {
        const prev = selected;
        await performMove(prev.row, prev.col, r, c, prev.isCapture);
        return;
    }
    await clearSelectionAfterMiss();
}

function removeDragGhost() {
    dragState?.ghost?.remove();
    boardElement.classList.remove('dragging-piece');
    boardElement.querySelectorAll('.piece-drag-source').forEach(el => el.classList.remove('piece-drag-source'));
}

async function onBoardPointerDown(event) {
    const pointerKind = event.pointerType || (event.type.startsWith('touch') ? 'touch' : 'mouse');
    const isPrimaryPointer = pointerKind !== 'mouse' || event.button === 0;
    if (getMoveInputMode() !== 'drag' || !isPrimaryPointer || !canInteractWithBoard()) return;
    if (event.type === 'touchstart' && event.touches?.length !== 1) return;
    const pieceEl = event.target.closest('.piece');
    const cell = event.target.closest('.square');
    if (!pieceEl || !cell || !boardElement.contains(cell)) return;
    const coords = cellToBoardCoords(cell);
    if (!coords) return;
    const point = getDragEventPoint(event);
    if (!point) return;
    const [r, c] = coords;
    if (event.cancelable) event.preventDefault();
    try {
        if (event.pointerId !== undefined) boardElement.setPointerCapture(event.pointerId);
    } catch (_) {}
    if (!selectPieceAtLocal(r, c)) {
        try {
            if (event.pointerId !== undefined) boardElement.releasePointerCapture(event.pointerId);
        } catch (_) {}
        return;
    }

    const sourceCell = boardCell(r, c);
    const sourcePiece = sourceCell?.querySelector('.piece');
    if (!sourcePiece) {
        try {
            if (event.pointerId !== undefined) boardElement.releasePointerCapture(event.pointerId);
        } catch (_) {}
        return;
    }

    const boardRect = boardElement.getBoundingClientRect();
    const pieceRect = sourcePiece.getBoundingClientRect();
    const ghost = sourcePiece.cloneNode(true);
    ghost.classList.add('piece-drag-ghost');
    ghost.style.width = `${pieceRect.width}px`;
    ghost.style.height = `${pieceRect.height}px`;
    boardElement.appendChild(ghost);
    sourcePiece.classList.add('piece-drag-source');
    dragState = {
        pointerId: getDragEventId(event),
        start: { row: r, col: c },
        offsetX: pieceRect.width / 2,
        offsetY: pieceRect.height / 2,
        ghost,
    };
    boardElement.classList.add('dragging-piece');
    ghost.style.left = `${point.clientX - boardRect.left - dragState.offsetX}px`;
    ghost.style.top = `${point.clientY - boardRect.top - dragState.offsetY}px`;
}

function onBoardPointerMove(event) {
    if (!isSameDragEvent(event)) return;
    if (event.cancelable) event.preventDefault();
    const point = getDragEventPoint(event);
    if (!point) return;
    const boardRect = boardElement.getBoundingClientRect();
    dragState.ghost.style.left = `${point.clientX - boardRect.left - dragState.offsetX}px`;
    dragState.ghost.style.top = `${point.clientY - boardRect.top - dragState.offsetY}px`;
}

async function finishBoardDrag(event, cancelled = false) {
    if (!isSameDragEvent(event)) return;
    if (event.cancelable) event.preventDefault();
    const point = getDragEventPoint(event);
    const activeDrag = dragState;
    dragState = null;
    try {
        if (activeDrag.pointerId !== undefined) boardElement.releasePointerCapture(activeDrag.pointerId);
    } catch (_) {}
    removeDragGhost();

    const target = point ? document.elementFromPoint(point.clientX, point.clientY)?.closest('.square') : null;
    const coords = !cancelled && target && boardElement.contains(target) ? cellToBoardCoords(target) : null;
    if (coords && hasPossibleMove(coords[0], coords[1])) {
        await performMove(activeDrag.start.row, activeDrag.start.col, coords[0], coords[1], selected?.isCapture ?? false);
        return;
    }
    await clearSelectionAfterMiss();
}

function onBoardPointerCancel(event) {
    finishBoardDrag(event, true);
}

function updateHistory(history) {
    historyList.innerHTML = '';
    history.forEach((m, i) => {
        const li = document.createElement('li');
        li.textContent = displayMove(m);
        li.dataset.index = i + 1;
        li.addEventListener('click', onHistoryClick);
        if (myColor && ((myColor === 'white' && i % 2 === 0) || (myColor === 'black' && i % 2 === 1))) {
            li.classList.add('my-move');
        }
        if (viewedMoveIndex === i + 1) {
            li.classList.add('active-history');
        }
        historyList.appendChild(li);
    });
}

function highlightHistoryItem(index) {
    document.querySelectorAll('.history-list li').forEach(li => {
        li.classList.toggle('active-history', parseInt(li.dataset.index) === index);
    });
}

async function onHistoryClick(e) {
    if (pendingMove) return;
    const idx = parseInt(e.currentTarget.dataset.index);
    if (idx === historyList.childElementCount) {
        await fetchBoard();
        return;
    }
    const data = await (await fetch(`/api/hotseat/snapshot/${boardId}/${idx}`)).json();
    boardState = data;
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    clearTransientState();
    viewingHistory = true;
    viewedMoveIndex = idx;
    highlightHistoryItem(idx);
    returnButton.style.display = 'block';
    renderBoard();
}

function coord(p) {
    return 'ABCDEFGH'[p.col] + (8 - p.row);
}

function displayMove(move) {
    if (myColor !== 'black') return move;
    const convert = (pos) => {
        const col = pos[0];
        const row = parseInt(pos.slice(1));
        const r = 8 - row;
        const c = col.charCodeAt(0) - 65;
        const r2 = 7 - r;
        const c2 = 7 - c;
        return String.fromCharCode(65 + c2) + (8 - r2);
    };
    const [start, end] = move.split('->');
    return `${convert(start)}->${convert(end)}`;
}

function setActivePlayer(p) {
    player1.classList.toggle('active', p === 'white');
    player2.classList.toggle('active', p === 'black');
}

function formatTime(t) {
    const m = Math.floor(t / 60).toString().padStart(2, '0');
    const s = Math.floor(t % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

function updateTimerDisplay() {
    const active = timers.turn === 'white' || timers.turn === 'black';
    if (gameOver || !active) {
        timer1.textContent = formatTime(timers.white);
        timer2.textContent = formatTime(timers.black);
        return;
    }
    const elapsed = (Date.now() - timerStart) / 1000;
    let w = timers.white;
    let b = timers.black;
    if (timers.turn === 'white') {
        w = Math.max(0, w - elapsed);
    } else if (timers.turn === 'black') {
        b = Math.max(0, b - elapsed);
    }
    timer1.textContent = formatTime(w);
    timer2.textContent = formatTime(b);
    if (w <= 0 || b <= 0) {
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        checkTimeout();
    }
}

function stopTimers() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    updateTimerDisplay();
}

function startTimers() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    updateTimerDisplay();
    if (!gameOver && (timers.turn === 'white' || timers.turn === 'black')) {
        timerInterval = setInterval(updateTimerDisplay, 1000);
    }
}

async function checkTimeout() {
    if (timeoutCheckPending || gameOver) return;
    timeoutCheckPending = true;
    try {
        const res = await fetch(`/api/hotseat/check_timeout/${boardId}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (data.status) {
                await queueHandleUpdate(data);
            }
        }
    } catch (e) {
    } finally {
        timeoutCheckPending = false;
    }
}

function buildWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/board/${boardId}`;
}

function setupWebSocket() {
    const ws = new WebSocket(buildWsUrl());
    ws.addEventListener('message', async (e) => {
        const data = JSON.parse(e.data);
        await queueHandleUpdate(data);
    });
    ws.addEventListener('close', () => {
        setTimeout(setupWebSocket, 1000);
    });
}

fetchBoard();
setupWebSocket();
boardElement.addEventListener('pointerdown', onBoardPointerDown);
document.addEventListener('pointermove', onBoardPointerMove);
document.addEventListener('pointerup', event => finishBoardDrag(event));
document.addEventListener('pointercancel', onBoardPointerCancel);
document.addEventListener('mousemove', onBoardPointerMove);
document.addEventListener('mouseup', event => finishBoardDrag(event));
if (!window.PointerEvent) {
    boardElement.addEventListener('mousedown', onBoardPointerDown);
    boardElement.addEventListener('touchstart', onBoardPointerDown, { passive: false });
    document.addEventListener('touchmove', onBoardPointerMove, { passive: false });
    document.addEventListener('touchend', event => finishBoardDrag(event), { passive: false });
    document.addEventListener('touchcancel', onBoardPointerCancel, { passive: false });
}
window.addEventListener('storage', event => {
    if (event.key === MOVE_MODE_KEY) {
        setMoveInputMode(event.newValue);
    }
});

returnButton.addEventListener('click', () => {
    fetchBoard();
});

const menuToggle = document.querySelector('.menu-toggle');
const rightSidebar = document.querySelector('.right-sidebar');
const closeSidebar = document.querySelector('.close-sidebar');
menuToggle.addEventListener('click', e => {
    e.stopPropagation();
    rightSidebar.classList.toggle('open');
});
rightSidebar.addEventListener('click', e => {
    e.stopPropagation();
});
if (closeSidebar) {
    closeSidebar.addEventListener('click', e => {
        e.stopPropagation();
        rightSidebar.classList.remove('open');
    });
}
document.addEventListener('click', () => {
    if (rightSidebar.classList.contains('open')) {
        rightSidebar.classList.remove('open');
    }
});

function endHotseat() {
    gameOver = true;
    setGameActionsVisible(false);
    stopTimers();
    fetch(`/api/hotseat/end/${boardId}`, { method: 'POST' }).catch(() => {});
}

document.getElementById('menuHome').addEventListener('click', () => {
    window.location.href = '/';
});

const menuEnd = document.getElementById('menuEnd');
const menuDraw = document.getElementById('menuDraw');

menuEnd.addEventListener('click', async () => {
    if (gameOver) return;
    rightSidebar.classList.remove('open');
    setGameActionsVisible(false);
    stopTimers();
    const res = await fetch(`/api/hotseat/end/${boardId}`, { method: 'POST' });
    if (res.ok) {
        const data = await res.json();
        await queueHandleUpdate(data);
    }
});

menuDraw.addEventListener('click', async () => {
    if (gameOver) return;
    rightSidebar.classList.remove('open');
    setGameActionsVisible(false);
    stopTimers();
    const res = await fetch(`/api/hotseat/draw/${boardId}`, { method: 'POST' });
    if (res.ok) {
        const data = await res.json();
        await queueHandleUpdate(data);
    }
});

resultHomeBtn.addEventListener('click', () => {
    window.location.href = '/';
});

resultCloseBtn.addEventListener('click', () => {
    hideModal(resultModal);
});
