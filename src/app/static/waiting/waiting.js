const timerEl = document.getElementById('waitTimer');
const cancelBtn = document.getElementById('cancelBtn');

let seconds = 0;
let timerInterval = null;
let ws = null;
let navigatingToBoard = false;

function soundLog(event, details = {}) {
    window.CheckersSound?.debugLog(`waiting:${event}`, {
        userId: window.userId || null,
        navigatingToBoard,
        seconds,
        ...details,
    });
}

window.CheckersSound?.preload(['gameFound']);
soundLog('script_loaded');

function cancelSearch(timeout = false) {
    const url = timeout ? '/api/cancel_game?timeout=1' : '/api/cancel_game';
    soundLog('cancel_search', {timeout, url});
    navigator.sendBeacon(url);
}
const formatTime = s => {
    s = Math.max(0, s);
    return `${Math.floor(s / 60).toString().padStart(2, '0')}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
};

async function startTimer() {
    soundLog('start_timer_request');
    const res  = await fetch('/api/user_status');
    const data = await res.json();
    soundLog('start_timer_user_status', data);

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
    const url = buildWsUrl();
    soundLog('ws_connecting', {url});
    ws = new WebSocket(url);

    ws.addEventListener('open', () => soundLog('ws_open'));

    ws.addEventListener('message', e => {
        soundLog('ws_message_raw', {data: e.data});
        const { board_id, play_sound } = JSON.parse(e.data);
        soundLog('ws_message_parsed', {boardId: board_id || null, playSound: play_sound === true});
        if (board_id) cleanupAndGo(board_id, {playSound: play_sound === true});
    });

    ws.addEventListener('error', () => soundLog('ws_error'));
    ws.addEventListener('close', event => {
        soundLog('ws_close', {code: event.code, reason: event.reason || '', wasClean: event.wasClean});
        setTimeout(setupWebSocket, 1000);
    });
}

function cleanupAndGo(boardId, options = {}) {
    soundLog('cleanup_and_go_enter', {boardId, options});
    if (navigatingToBoard) {
        soundLog('cleanup_and_go_skipped_already_navigating', {boardId});
        return;
    }
    navigatingToBoard = true;
    clearInterval(timerInterval);
    const soundPlayed = options.playSound === true && window.CheckersSound?.play('gameFound', {
        onceKey: `checkers:${boardId}:gameFound`,
    }) === true;
    soundLog('cleanup_and_go_sound_decision', {
        boardId,
        requestedPlaySound: options.playSound === true,
        soundPlayed,
        delayMs: soundPlayed ? 650 : 0,
    });
    setTimeout(() => {
        soundLog('cleanup_and_go_redirect', {boardId});
        location.href = `/board/${boardId}`;
    }, soundPlayed ? 650 : 0);
}

async function joinQueue() {
    soundLog('join_queue_request');
    const data = await (await fetch('/api/search_game', { method: 'POST' })).json();
    soundLog('join_queue_response', data);
    data.board_id ? cleanupAndGo(data.board_id, {playSound: data.play_sound === true}) : await startTimer();
}

cancelBtn.addEventListener('click', async () => {
    soundLog('cancel_button_click');
    await fetch('/api/cancel_game', { method: 'POST' });
    clearInterval(timerInterval);
    location.href = '/';
});

document.addEventListener('DOMContentLoaded', async () => {
    const navType = performance.getEntriesByType('navigation')[0]?.type || 'unknown';
    soundLog('dom_content_loaded', {navType});
    if (navType === 'back_forward') {
        soundLog('dom_content_loaded_skipped_back_forward');
        return;
    }

    setupWebSocket();

    const data = await (await fetch('/api/user_status')).json();
    soundLog('initial_user_status_response', data);
    if (data.board_id) {
        cleanupAndGo(data.board_id, {playSound: data.play_sound === true});
    } else if (data.timeout) {
        cancelSearch(true);
        location.href = '/';
    } else if (data.waiting_since) {
        await startTimer();
    } else {
        await joinQueue();
    }
});
