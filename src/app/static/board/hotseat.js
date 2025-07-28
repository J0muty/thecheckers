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

document.querySelectorAll('.player-name').forEach(el => (el.style.display = 'none'));

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

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

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

async function autoMoveIfSingle() {
    if (viewingHistory || gameOver || isPerformingAutoMove) return;
    if (myColor && turn !== myColor) return;
    if (forcedPieces.length === 1 && forcedPieces[0].moves.length === 1) {
        isPerformingAutoMove = true;
        try {
            await fetchBoard();
            if (!(forcedPieces.length === 1 && forcedPieces[0].moves.length === 1)) return;
            const fp = forcedPieces[0];
            selected = { row: fp.row, col: fp.col, isCapture: true };
            possibleMoves = fp.moves;
            renderBoard();
            await delay(300);
            await performMove(fp.row, fp.col, fp.moves[0][0], fp.moves[0][1], true);
        } finally {
            isPerformingAutoMove = false;
        }
    }
}

async function handleUpdate(data) {
    const finished = data.status && ['white_win','black_win','draw','ended'].includes(data.status);
    boardState = data.board;
    timers = data.timers;
    timerStart = Date.now();
    turn = data.timers.turn;
    viewedMoveIndex = data.history.length;
    updateHistory(data.history);
    viewingHistory = false;
    if (data.players) {
        if (data.players.white) player1.querySelector('.player-name').textContent = data.players.white;
        if (data.players.black) player2.querySelector('.player-name').textContent = data.players.black;
    }
    returnButton.style.display = 'none';
    if (finished) gameOver = true;
    setActivePlayer(turn);
    if (!gameOver && (turn === 'white' || turn === 'black')) {
        startTimers();
    } else {
        stopTimers();
    }
    computeForcedPieces();
    renderBoard();
    if (!gameOver && !isPerformingAutoMove) {
        await autoMoveIfSingle();
    }
    if (finished) {
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
    await handleUpdate(data);
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
    const res = await fetch(`/api/hotseat/move/${boardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start: [startR, startC],
            end: [endR, endC],
            player: turn
        })
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.detail || 'Неверный ход');
        return;
    }
    await handleUpdate(data);
    if (isCapture) {
        const nextCaps = await fetchCaptures(endR, endC);
        if (nextCaps.length === 1) {
            selected = { row: endR, col: endC, isCapture: true };
            possibleMoves = nextCaps;
            renderBoard();
            await delay(300);
            await performMove(endR, endC, nextCaps[0][0], nextCaps[0][1], true);
            return;
        } else if (nextCaps.length > 0) {
            selected = { row: endR, col: endC, isCapture: true };
            possibleMoves = nextCaps;
            multiCapture = true;
            renderBoard();
            return;
        }
    }
    multiCapture = false;
    selected = null;
    possibleMoves = [];
    renderBoard();
    await autoMoveIfSingle();
}

function renderBoard() {
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
                    const p = document.createElement('div');
                    p.classList.add('piece', piece.toLowerCase() === 'w' ? 'white' : 'black');
                    if (
                        piece === piece.toUpperCase() ||
                        (piece.toLowerCase() === 'w' && br === 0) ||
                        (piece.toLowerCase() === 'b' && br === 7)
                    ) {
                        p.classList.add('king');
                    }
                    cell.appendChild(p);
                }
                cell.addEventListener('click', onCellClick);
            }
            boardElement.appendChild(cell);
        }
    }
}

async function onCellClick(e) {
    if (gameOver || viewingHistory) return;
    if (myColor && turn !== myColor) return;
    const row = +e.currentTarget.dataset.row;
    const col = +e.currentTarget.dataset.col;
    if (row === 0 || row === 9 || col === 0 || col === 9) return;
    const rDisplay = row - 1;
    const cDisplay = col - 1;
    const [r, c] = toBoardCoords(rDisplay, cDisplay);
    if (multiCapture && !possibleMoves.some(m => m[0] === r && m[1] === c)) {
        return;
    }
    const piece = boardState[r][c];
    if (!selected) {
        if (forcedPieces.length && !forcedPieces.some(p => p.row === r && p.col === c)) {
            return;
        }
        if (!piece || (piece.toLowerCase() === 'w' ? 'white' : 'black') !== turn) return;
        const caps = await fetchCaptures(r, c);
        if (caps.length) {
            possibleMoves = caps;
            selected = { row: r, col: c, isCapture: true };
        } else {
            const moves = await fetchMoves(r, c);
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
    historyList.innerHTML = '';
    history.forEach((m, i) => {
        const li = document.createElement('li');
        li.textContent = displayMove(m);
        li.dataset.index = i + 1;
        li.addEventListener('click', onHistoryClick);
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
    const idx = parseInt(e.currentTarget.dataset.index);
    if (idx === historyList.childElementCount) {
        fetchBoard();
        return;
    }
    const data = await (await fetch(`/api/hotseat/snapshot/${boardId}/${idx}`)).json();
    boardState = data;
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
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
    try {
        const res = await fetch(`/api/hotseat/check_timeout/${boardId}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (data.status) {
                await handleUpdate(data);
            }
        }
    } catch (e) {}
}

function buildWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/board/${boardId}`;
}

function setupWebSocket() {
    const ws = new WebSocket(buildWsUrl());
    ws.addEventListener('message', async (e) => {
        if (gameOver) return;
        const data = JSON.parse(e.data);
        await handleUpdate(data);
    });
    ws.addEventListener('close', () => {
        setTimeout(setupWebSocket, 1000);
    });
}

fetchBoard();
setupWebSocket();

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
    stopTimers();
    fetch(`/api/hotseat/end/${boardId}`, { method: 'POST' }).catch(() => {});
}

document.getElementById('menuHome').addEventListener('click', () => {
    window.location.href = '/';
});

document.getElementById('menuEnd').addEventListener('click', async () => {
    rightSidebar.classList.remove('open');
    gameOver = true;
    stopTimers();
    const res = await fetch(`/api/hotseat/end/${boardId}`, { method: 'POST' });
    if (res.ok) {
        const data = await res.json();
        resultText.textContent = 'Игра окончена';
        await handleUpdate(data);
    }
});

resultHomeBtn.addEventListener('click', () => {
    window.location.href = '/';
});

resultCloseBtn.addEventListener('click', () => {
    hideModal(resultModal);
});
