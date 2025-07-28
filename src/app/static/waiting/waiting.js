const timerEl = document.getElementById('waitTimer');
const cancelBtn = document.getElementById('cancelBtn');
let seconds = 0;
let timerInterval = null;
let ws = null;

function cancelSearch(timeout = false) {
    const url = timeout ? '/api/cancel_game?timeout=1' : '/api/cancel_game';
    navigator.sendBeacon(url);
}

function formatTime(s) {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
}

async function startTimer() {
    const res = await fetch('/api/user_status');
    const data = await res.json();
    if (data.timeout) {
        cancelSearch(true);
        window.location.href = '/';
        return;
    }
    const start = data.waiting_since
        ? data.waiting_since * 1000
        : Date.now();
    seconds = Math.floor((Date.now() - start) / 1000);
    timerEl.textContent = formatTime(seconds);
    clearInterval(timerInterval);
    timerInterval = setInterval(async () => {
        seconds += 1;
        timerEl.textContent = formatTime(seconds);
        if (seconds >= 600) {
            cancelSearch(true);
            clearInterval(timerInterval);
            window.location.href = '/';
            return;
        }
        if (seconds % 10 === 0) {
            const resp = await fetch('/api/user_status');
            const info = await resp.json();
            if (info.timeout) {
                cancelSearch(true);
                clearInterval(timerInterval);
                window.location.href = '/';
            }
        }
    }, 1000);
}

function buildWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/waiting/${userId}`;
}

function setupWebSocket() {
    ws = new WebSocket(buildWsUrl());
    ws.addEventListener('message', e => {
        const data = JSON.parse(e.data);
        if (data.board_id) {
            cleanupAndGo(data.board_id, data.color);
        }
    });
    ws.addEventListener('close', () => {
        setTimeout(setupWebSocket, 1000);
    });
}

function cleanupAndGo(boardId, color) {
    clearInterval(timerInterval);
    window.location.href = `/board/${boardId}`;
}

async function joinQueue() {
    const res = await fetch('/api/search_game', { method: 'POST' });
    const data = await res.json();
    if (data.board_id) {
        cleanupAndGo(data.board_id, data.color);
    } else {
        await startTimer();
    }
}

cancelBtn.addEventListener('click', async () => {
    await fetch('/api/cancel_game', { method: 'POST' });
    clearInterval(timerInterval);
    window.location.href = '/';
});

document.addEventListener('DOMContentLoaded', async () => {
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.type === 'back_forward') {
        return;
    }

    setupWebSocket();

    const res = await fetch('/api/user_status');
    const data = await res.json();

    if (data.board_id) {
        showNotification('Вы уже находитесь в сетевой игре', 'error');
        return;
    } else if (data.timeout) {
        cancelSearch(true);
        window.location.href = '/';
        return;
    } else if (data.waiting_since) {
        await startTimer();
    } else {
        await joinQueue();
    }
});
