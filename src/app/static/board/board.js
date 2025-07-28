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
    setActivePlayer(turn);
    startTimers();
    computeForcedPieces();
    renderBoard();

    if (!isPerformingAutoMove) {
        await autoMoveIfSingle();
    }

    if (data.status && !gameOver) {
        gameOver = true;
        stopTimers();
        let msg = '';
        if (data.status === 'white_win' || data.status === 'black_win') {
            const winner = data.status === 'white_win' ? 'white' : 'black';
            if (myColor) {
                msg = myColor === winner ? 'Вы выиграли!' : 'Вы проиграли!';
            } else {
                msg = winner === 'white' ? 'Белые победили!' : 'Чёрные победили!';
            }
            const reasonMap = {
                no_pieces: 'У противника не осталось шашек',
                no_moves: 'Противнику некуда ходить',
                resign: 'Противник сдался',
                timeout: 'У противника истекло время',
            };
            if (data.reason && reasonMap[data.reason]) {
                msg += ' ' + reasonMap[data.reason];
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
                const sign = delta > 0 ? '+' : '';
                msg += ` (${sign}${delta} Elo)`;
            }
        }
        resultText.textContent = msg;
        showModal(resultModal);
    }
}

async function fetchBoard() {
        const res = await fetch(`/api/board/${boardId}`);
    if (!res.ok) {
        console.error('Failed to fetch board', res.status);
        return;
    }
    const data = await res.json();
    await handleUpdate(data);
}

async function fetchMoves(r, c) {
    return await (await fetch(
        `/api/moves/${boardId}?row=${r}&col=${c}&player=${turn}`
    )).json();
}

async function fetchCaptures(r, c) {
    return await (await fetch(
        `/api/captures/${boardId}?row=${r}&col=${c}&player=${turn}`
    )).json();
}

async function performMove(startR, startC, endR, endC, isCapture) {
    const res = await fetch(`/api/move/${boardId}`, {
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
    const data = await (await fetch(`/api/snapshot/${boardId}/${idx}`)).json();
    boardState = data;
    clearInterval(timerInterval);
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
    let w = timers.white;
    let b = timers.black;
    if (timers.turn === 'white') w = Math.max(0, w - elapsed);
    else b = Math.max(0, b - elapsed);
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
    if (!gameOver) {
        timerInterval = setInterval(updateTimerDisplay, 1000);
    }
}

async function checkTimeout() {
    try {
        const res = await fetch(`/api/check_timeout/${boardId}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (data.status) {
                await handleUpdate(data);
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
            if (data.from !== myColor) {
                showModal(drawOfferModal);
            }
        } else if (data.type === 'draw_declined') {
            alert('Предложение ничьи отклонено');
        } else if (data.type === 'rematch_offer') {
            if (data.from !== myColor) {
                showModal(rematchOfferModal);
            }
        } else if (data.type === 'rematch_decline') {
            alert('Реванш отклонён');
        } else if (data.type === 'rematch_start') {
            window.location.href = `/board/${data.board_id}`;
        } else {
            await handleUpdate(data);
        }
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
if (closeSidebar) {
    closeSidebar.addEventListener('click', e => {
        e.stopPropagation();
        rightSidebar.classList.remove('open');
    });
}
rightSidebar.addEventListener('click', e => {
    e.stopPropagation();
});
document.addEventListener('click', () => {
    if (rightSidebar.classList.contains('open')) {
        rightSidebar.classList.remove('open');
    }
});
document.getElementById('menuHome').addEventListener('click', () => {
    window.location.href = '/';
});

document.getElementById('menuResign').addEventListener('click', () => {
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
        await handleUpdate(data);
    }
});

cancelResignBtn.addEventListener('click', () => hideModal(resignModal));

document.getElementById('menuDraw').addEventListener('click', async () => {
    rightSidebar.classList.remove('open');
    const res = await fetch(`/api/draw_offer/${boardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: myColor })
    });
    if (res.ok) alert('Предложение отправлено');
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
        await handleUpdate(data);
    }
}

resultHomeBtn.addEventListener('click', () => {
    window.location.href = '/';
});

resultCloseBtn.addEventListener('click', () => {
    hideModal(resultModal);
});

if (rematchBtn) {
    rematchBtn.addEventListener('click', async () => {
        hideModal(resultModal);
        const res = await fetch(`/api/rematch_request/${boardId}`, { method: 'POST' });
        if (res.ok) alert('Запрос на реванш отправлен');
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