const timerEl = document.getElementById('waitTimer');
const cancelBtn = document.getElementById('cancelBtn');

let seconds = 0;
let timerInterval = null;
let ws = null;

function cancelSearch(timeout = false) {
    const url = timeout ? '/api/cancel_game?timeout=1' : '/api/cancel_game';
    navigator.sendBeacon(url);
}
const formatTime = s =>
    `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`;

async function startTimer() {
    const res  = await fetch('/api/user_status');
    const data = await res.json();

    if (data.timeout) {
        cancelSearch(true);
        location.href = '/';
        return;
    }

    const start = data.waiting_since ? data.waiting_since * 1000 : Date.now();
    seconds = Math.floor((Date.now() - start) / 1000);
    timerEl.textContent = formatTime(seconds);

    clearInterval(timerInterval);
    timerInterval = setInterval(tick, 1000);
}

async function tick() {
    seconds += 1;
    timerEl.textContent = formatTime(seconds);

    if (seconds % 10 === 0) {
        const info = await (await fetch('/api/user_status')).json();
        if (info.timeout) {
            cancelSearch(true);
            clearInterval(timerInterval);
            location.href = '/';
            return;
        }
    }
    
    if (seconds >= 600) {
        cancelSearch(true);
        clearInterval(timerInterval);
        location.href = '/';
    }
}

function buildWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/waiting/${window.userId}`;
}

function setupWebSocket() {
    ws = new WebSocket(buildWsUrl());

    ws.addEventListener('message', e => {
        const { board_id } = JSON.parse(e.data);
        if (board_id) cleanupAndGo(board_id);
    });

    ws.addEventListener('close', () => setTimeout(setupWebSocket, 1000));
}

function cleanupAndGo(boardId) {
    clearInterval(timerInterval);
    location.href = `/board/${boardId}`;
}

async function joinQueue() {
    const data = await (await fetch('/api/search_game', { method: 'POST' })).json();
    data.board_id ? cleanupAndGo(data.board_id) : await startTimer();
}

cancelBtn.addEventListener('click', async () => {
    await fetch('/api/cancel_game', { method: 'POST' });
    clearInterval(timerInterval);
    location.href = '/';
});

document.addEventListener('DOMContentLoaded', async () => {
    if (performance.getEntriesByType('navigation')[0]?.type === 'back_forward') return;

    setupWebSocket();

    const data = await (await fetch('/api/user_status')).json();
    if (data.board_id) {
        showNotification('Вы уже находитесь в сетевой игре', 'error');
    } else if (data.timeout) {
        cancelSearch(true);
        location.href = '/';
    } else if (data.waiting_since) {
        await startTimer();
    } else {
        await joinQueue();
    }
});
