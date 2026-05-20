const boardElement = document.getElementById('board');
const historyList = document.getElementById('historyList');
const timer1 = document.getElementById('timer1');
const timer2 = document.getElementById('timer2');
const player1 = document.querySelector('.player1');
const player2 = document.querySelector('.player2');
const returnButton = document.getElementById('returnButton');
const resignModal = document.getElementById('resignModal');
const confirmResignBtn = document.getElementById('confirmResignBtn');
const cancelResignBtn = document.getElementById('cancelResignBtn');
const drawOfferModal = document.getElementById('drawOfferModal');
const acceptDrawBtn = document.getElementById('acceptDrawBtn');
const declineDrawBtn = document.getElementById('declineDrawBtn');
const resultModal = document.getElementById('resultModal');
const resultText = document.getElementById('resultText');
const resultHomeBtn = document.getElementById('resultHomeBtn');
const resultCloseBtn = document.getElementById('resultCloseBtn');
const rematchBtn = document.getElementById('rematchBtn');
const rematchOfferModal = document.getElementById('rematchOfferModal');
const acceptRematchBtn = document.getElementById('acceptRematchBtn');
const declineRematchBtn = document.getElementById('declineRematchBtn');
const letters = ['', 'A','B','C','D','E','F','G','H',''];
const numbers = ['', '8','7','6','5','4','3','2','1',''];
const myColor = typeof playerColor !== 'undefined' && playerColor ? playerColor : null;
const moveCache = new Map();
const captureCache = new Map();
const MOVE_ANIMATION_MS = 280;
const MOVE_CHAIN_PAUSE_MS = 60;
let moveController = null;
let captureController = null;

function toBoardCoords(r, c) {
    return myColor === 'black' ? [7 - r, 7 - c] : [r, c];
}

function fromBoardCoords(r, c) {
    return myColor === 'black' ? [7 - r, 7 - c] : [r, c];
}

let boardState = [];
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
                i += dr;
                j += dc;
            }
            if (withinBounds(i, j) && board[i][j] && isOpponent(board[i][j], player)) {
                let i2 = i + dr, j2 = j + dc;
                while (withinBounds(i2, j2)) {
                    if (board[i2][j2] === null) {
                        caps.push([i2, j2]);
                    } else {
                        break;
                    }
                    i2 += dr;
                    j2 += dc;
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
            const nr = r + dr, nc = c + dc;
            if (withinBounds(nr, nc) && board[nr][nc] === null) {
                moves.push([nr, nc]);
            }
        }
    } else {
        const dirs = [[-1,-1],[-1,1],[1,-1],[1,1]];
        for (const [dr, dc] of dirs) {
            let i = r + dr, j = c + dc;
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
    el.classList.add('piece', piece.toLowerCase() === 'w' ? 'white' : 'black');
    if (
        piece === piece.toUpperCase() ||
        (piece.toLowerCase() === 'w' && boardRow === 0) ||
        (piece.toLowerCase() === 'b' && boardRow === 7)
    ) {
        el.classList.add('king');
    }
    return el;
}

function boardCell(boardRow, boardCol) {
    const [displayRow, displayCol] = fromBoardCoords(boardRow, boardCol);
    return boardElement.querySelector(`[data-row="${displayRow + 1}"][data-col="${displayCol + 1}"]`);
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

async function animateMoveCoordinates(boardBefore, start, end) {
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
        .map(([captureRow, captureCol]) => boardCell(captureRow, captureCol)?.querySelector('.piece'))
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

async function animateMoveStep(boardBefore, move) {
    const { start, end } = parseMoveNotation(move);
    return animateMoveCoordinates(boardBefore, start, end);
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

function clearTransientState() {
    selected = null;
    possibleMoves = [];
    multiCapture = false;
    forcedPieces = [];
    moveController?.abort();
    captureController?.abort();
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
            if (!(forcedPieces.length === 1 && forcedPieces[0].moves.length === 1)) return;
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
    ['menuResign', 'menuDraw'].forEach(id => {
        const item = document.getElementById(id);
        if (item) item.hidden = !visible;
    });
}

async function handleUpdate(data) {
    moveCache.clear();
    captureCache.clear();
    const finished = isFinishedUpdate(data);
    const shouldShowResult = Boolean(data.status && !gameOver);
    const wasViewingHistory = viewingHistory;
    const previousHistoryLen = lastHistoryLen;
    if (!wasViewingHistory && boardState.length && data.history.length > previousHistoryLen) {
        await playIncomingAnimations(data.history, previousHistoryLen);
    }
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
    startTimers();
    applyForcedState(data);
    renderBoard();
    if (!gameOver && !isPerformingAutoMove) {
        await autoMoveIfSingle();
    }
    if (shouldShowResult) {
        stopTimers();
        let msg = '';
        if (data.status === 'white_win' || data.status === 'black_win') {
            const winner = data.status === 'white_win' ? 'white' : 'black';
            msg = myColor
                ? (myColor === winner ? 'Вы выиграли!' : 'Вы проиграли!')
                : (winner === 'white' ? 'Белые победили!' : 'Чёрные победили!');
            const reasonMap = {
                no_pieces: () => myColor && myColor !== winner ? 'У вас не осталось шашек' : 'У противника не осталось шашек',
                no_moves:  () => myColor && myColor !== winner ? 'Вам некуда ходить' : 'Противнику некуда ходить',
                resign:    () => myColor && myColor !== winner ? 'Вы сдались' : 'Противник сдался',
                timeout:   () => myColor && myColor !== winner ? 'У вас истекло время' : 'У противника истекло время',
            };
            if (data.reason && reasonMap[data.reason]) {
                msg += ' ' + reasonMap[data.reason]();
            }
        } else if (data.status === 'draw') {
            msg = 'Ничья!';
            if (data.reason === 'agreement') {
                msg += ' По соглашению сторон';
            }
        } else {
            msg = 'Игра окончена';
        }
        if (data.rating_change && myColor) {
            const delta = data.rating_change[myColor];
            if (typeof delta === 'number') {
                msg += ` (${delta > 0 ? '+' : ''}${delta} Elo)`;
            }
        }
        resultText.textContent = msg;
        showModal(resultModal);
    } else if (finished) {
        stopTimers();
    }
}

async function fetchBoard() {
    const start = performance.now();
    const res = await fetch(`/api/board/${boardId}`);
    if (!res.ok) return console.error('Failed to fetch board', res.status);
    const data = await res.json();
    await queueHandleUpdate(data);
    logFrontend('fetchBoard', performance.now() - start);
}

async function fetchMoves(r, c) {
    const key = `${turn}|${r},${c}`;
    if (moveCache.has(key)) return moveCache.get(key);
    moveController?.abort();
    moveController = new AbortController();
    const start = performance.now();
    const p = fetch(`/api/moves/${boardId}?row=${r}&col=${c}&player=${turn}`, { signal: moveController.signal, cache: 'force-cache' })
        .then(res => res.json())
        .catch(err => err.name === 'AbortError' ? [] : Promise.reject(err))
        .finally(() => logFrontend('fetchMoves', performance.now() - start));
    moveCache.set(key, p);
    return p;
}

async function fetchCaptures(r, c) {
    const key = `${turn}|${r},${c}`;
    if (captureCache.has(key)) return captureCache.get(key);
    captureController?.abort();
    captureController = new AbortController();
    const start = performance.now();
    const p = fetch(`/api/captures/${boardId}?row=${r}&col=${c}&player=${turn}`, { signal: captureController.signal, cache: 'force-cache' })
        .then(res => res.json())
        .catch(err => err.name === 'AbortError' ? [] : Promise.reject(err))
        .finally(() => logFrontend('fetchCaptures', performance.now() - start));
    captureCache.set(key, p);
    return p;
}

async function performMove(startR, startC, endR, endC, isCapture) {
    if (pendingMove || viewingHistory || gameOver) return;
    const start = performance.now();
    pendingMove = true;
    const moveNotation = formatMoveNotation([startR, startC], [endR, endC]);
    const originalBoard = boardState.map(row => [...row]);
    const originalSelected = selected ? { ...selected } : null;
    const originalPossibleMoves = possibleMoves.map(move => [...move]);
    const originalForcedPieces = forcedPieces.map(piece => ({
        row: piece.row,
        col: piece.col,
        moves: piece.moves.map(move => [...move]),
    }));
    const originalMultiCapture = multiCapture;
    const piece = boardState[startR][startC];
    if (!piece) {
        pendingMove = false;
        return;
    }

    clearTransientState();
    animatingBoard = true;
    boardState = await animateMoveCoordinates(originalBoard, [startR, startC], [endR, endC]);
    animatingBoard = false;
    locallyAnimatedMove = moveNotation;

    try {
        const res = await fetch(`/api/move/${boardId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: [startR, startC],
                end: [endR, endC],
                player: turn,
                history_len: lastHistoryLen,
            }),
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
        pendingMove = false;
        logFrontend('performMove', performance.now() - start);
    }
}

function renderBoard() {
    const start = performance.now();
    const frag = document.createDocumentFragment();
    const pmSet = new Set(possibleMoves.map(m => `${m[0]}-${m[1]}`));
    const fpSet = new Set(forcedPieces.map(p => `${p.row}-${p.col}`));
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
                const r = row - 1, c = col - 1;
                const [br, bc] = toBoardCoords(r, c);
                cell.classList.add((r + c) % 2 ? 'dark' : 'light');
                if (selected && selected.row === br && selected.col === bc) cell.classList.add('selected');
                if (pmSet.has(`${br}-${bc}`)) cell.classList.add('highlight');
                if (myColor === turn && fpSet.has(`${br}-${bc}`)) cell.classList.add('forced');
                const piece = boardState[br][bc];
                if (piece) {
                    const p = createPieceElement(piece, br);
                    cell.appendChild(p);
                }
            }
            frag.appendChild(cell);
        }
    }
    boardElement.replaceChildren(frag);
    logFrontend('renderBoard', performance.now() - start);
}

async function onCellClick(e) {
    const target = e.target.closest('.square');
    if (!target || gameOver || viewingHistory || isPerformingAutoMove || pendingMove || animatingBoard || (myColor && turn !== myColor)) return;
    const row = +target.dataset.row, col = +target.dataset.col;
    if (row === 0 || row === 9 || col === 0 || col === 9) return;
    const [rDisplay, cDisplay] = [row - 1, col - 1];
    const [r, c] = toBoardCoords(rDisplay, cDisplay);
    if (multiCapture && !possibleMoves.some(m => m[0] === r && m[1] === c)) return;
    const piece = boardState[r][c];
    if (!selected) {
        if (forcedPieces.length && !forcedPieces.some(p => p.row === r && p.col === c)) return;
        if (!piece || pieceOwner(piece) !== turn) return;
        if (forcedPieces.length > 0) {
            const fp = forcedPieces.find(p => p.row === r && p.col === c);
            if (!fp) return;
            possibleMoves = fp.moves;
            selected = { row: r, col: c, isCapture: true };
        } else {
            const moves = pieceMovesLocal(boardState, r, c, turn);
            if (!moves.length) return;
            possibleMoves = moves;
            selected = { row: r, col: c, isCapture: false };
        }
        renderBoard();
        return;
    }
    if (possibleMoves.some(m => m[0] === r && m[1] === c)) {
        const prev = selected;
        await performMove(prev.row, prev.col, r, c, prev.isCapture);
        return;
    }
    if (!multiCapture) {
        selected = null;
        possibleMoves = [];
        computeForcedPieces();
        await autoMoveIfSingle();
    }
    renderBoard();
}

function updateHistory(history) {
    const frag = document.createDocumentFragment();
    history.forEach((m, i) => {
        const li = document.createElement('li');
        li.textContent = displayMove(m);
        li.dataset.index = i + 1;
        if (myColor && ((myColor === 'white' && i % 2 === 0) || (myColor === 'black' && i % 2 === 1))) {
            li.classList.add('my-move');
        }
        if (viewedMoveIndex === i + 1) {
            li.classList.add('active-history');
        }
        frag.appendChild(li);
    });
    historyList.replaceChildren(frag);
}

function highlightHistoryItem(index) {
    document.querySelectorAll('.history-list li').forEach(li => {
        li.classList.toggle('active-history', parseInt(li.dataset.index) === index);
    });
}

async function onHistoryClick(e) {
    const li = e.target.closest('li');
    if (!li || pendingMove) return;
    const idx = parseInt(li.dataset.index);
    if (idx === historyList.childElementCount) {
        await fetchBoard();
        return;
    }
    const data = await (await fetch(`/api/snapshot/${boardId}/${idx}`)).json();
    boardState = data;
    clearInterval(timerInterval);
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
    const elapsed = (Date.now() - timerStart) / 1000;
    let w = timers.white, b = timers.black;
    if (timers.turn === 'white') w = Math.max(0, w - elapsed);
    else if (timers.turn === 'black') b = Math.max(0, b - elapsed);
    timer1.textContent = formatTime(w);
    timer2.textContent = formatTime(b);
    if (!gameOver && (w <= 0 || b <= 0)) {
        clearInterval(timerInterval);
        checkTimeout();
    }
}

function stopTimers() {
    clearInterval(timerInterval);
    updateTimerDisplay();
}

function startTimers() {
    clearInterval(timerInterval);
    updateTimerDisplay();
    if (!gameOver && (timers.turn === 'white' || timers.turn === 'black')) {
        timerInterval = setInterval(updateTimerDisplay, 1000);
    }
}

async function checkTimeout() {
    try {
        const res = await fetch(`/api/check_timeout/${boardId}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (data.status) {
                await queueHandleUpdate(data);
            }
        }
    } catch (e) {
        console.error('timeout check failed', e);
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
        if (data.type === 'draw_offer') {
            if (data.from !== myColor) showModal(drawOfferModal);
        } else if (data.type === 'draw_declined') {
            showNotification('Предложение ничьи отклонено', 'error');
        } else if (data.type === 'rematch_offer') {
            if (data.from !== myColor) showModal(rematchOfferModal);
        } else if (data.type === 'rematch_decline') {
            showNotification('Реванш отклонён', 'error');
        } else if (data.type === 'rematch_start') {
            window.location.href = `/board/${data.board_id}`;
        } else {
            await queueHandleUpdate(data);
        }
    });
    ws.addEventListener('close', () => {
        setTimeout(setupWebSocket, 1000);
    });
}

fetchBoard();
setupWebSocket();
boardElement.addEventListener('click', onCellClick);
historyList.addEventListener('click', onHistoryClick);
returnButton.addEventListener('click', () => fetchBoard());

async function logFrontend(functionName, duration) {
    if (localStorage.debugPerf !== '1') return;
    fetch(`/api/frontend-log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ function: functionName, duration })
    }).catch(err => console.error('Log error', err));
}

const menuToggle = document.querySelector('.menu-toggle');
const rightSidebar = document.querySelector('.right-sidebar');
const closeSidebar = document.querySelector('.close-sidebar');
menuToggle.addEventListener('click', e => {
    e.stopPropagation();
    rightSidebar.classList.toggle('open');
});
if (closeSidebar) {
    closeSidebar.addEventListener('click', e => {
        e.stopPropagation();
        rightSidebar.classList.remove('open');
    });
}
rightSidebar.addEventListener('click', e => e.stopPropagation());
document.addEventListener('click', () => {
    if (rightSidebar.classList.contains('open')) {
        rightSidebar.classList.remove('open');
    }
});
document.getElementById('menuHome').addEventListener('click', () => {
    window.location.href = '/';
});
const menuResign = document.getElementById('menuResign');
const menuDraw = document.getElementById('menuDraw');

menuResign.addEventListener('click', () => {
    if (gameOver) return;
    rightSidebar.classList.remove('open');
    showModal(resignModal);
});
confirmResignBtn.addEventListener('click', async () => {
    hideModal(resignModal);
    const res = await fetch(`/api/resign/${boardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: myColor })
    });
    if (res.ok) {
        const data = await res.json();
        await queueHandleUpdate(data);
    }
});
cancelResignBtn.addEventListener('click', () => hideModal(resignModal));
menuDraw.addEventListener('click', async () => {
    if (gameOver) return;
    rightSidebar.classList.remove('open');
    const res = await fetch(`/api/draw_offer/${boardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: myColor })
    });
    if (res.ok) showNotification('Предложение отправлено');
});
acceptDrawBtn.addEventListener('click', () => respondDraw(true));
declineDrawBtn.addEventListener('click', () => respondDraw(false));
async function respondDraw(accept) {
    hideModal(drawOfferModal);
    const res = await fetch(`/api/draw_response/${boardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: myColor, accept })
    });
    if (res.ok && accept) {
        const data = await res.json();
        await queueHandleUpdate(data);
    }
}
resultHomeBtn.addEventListener('click', () => window.location.href = '/');
resultCloseBtn.addEventListener('click', () => hideModal(resultModal));
if (rematchBtn) {
    rematchBtn.addEventListener('click', async () => {
        hideModal(resultModal);
        const res = await fetch(`/api/rematch_request/${boardId}`, { method: 'POST' });
        if (res.ok) showNotification('Запрос на реванш отправлен');
    });
}
acceptRematchBtn.addEventListener('click', () => respondRematch(true));
declineRematchBtn.addEventListener('click', () => respondRematch(false));
async function respondRematch(accept) {
    hideModal(rematchOfferModal);
    const res = await fetch(`/api/rematch_response/${boardId}?action=${accept ? 'accept' : 'decline'}`, { method: 'POST' });
    if (res.ok && accept) {
        const data = await res.json();
        window.location.href = `/board/${data.board_id}`;
    }
}
