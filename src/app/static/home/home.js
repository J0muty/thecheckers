const statusContainer = document.getElementById('statusContainer');
const netBox = document.getElementById('netStatus');
const netTimer = document.getElementById('netTimer');
const netReturn = document.getElementById('netReturn');
const netLeave = document.getElementById('netLeave');
const netTitle = document.getElementById('netTitle');

const singleBox = document.getElementById('singleStatus');
const singleTimer = document.getElementById('singleTimer');
const singleReturn = document.getElementById('singleReturn');
const singleLeave = document.getElementById('singleLeave');

const waitBox = document.getElementById('waitStatus');
const waitTimer = document.getElementById('waitTimer');
const waitReturn = document.getElementById('waitReturn');
const waitLeave = document.getElementById('waitLeave');
const lobbyBox = document.getElementById('lobbyStatus');
const lobbyReturn = document.getElementById('lobbyReturn');
const lobbyLeave = document.getElementById('lobbyLeave');

const leaveModal = document.getElementById('leaveModal');
const leaveYes = document.getElementById('leaveYes');
const leaveNo = document.getElementById('leaveNo');
const singleBtn = document.getElementById('singleBtn');
const netBtn = document.getElementById('netBtn');
const singleModal = document.getElementById('singleModal');
const singleCloseBtn = document.getElementById('singleCloseBtn');
const startSingleBtn = document.getElementById('startSingleBtn');
const netModal = document.getElementById('netModal');
const netSearchBtn = document.getElementById('netSearchBtn');
const netLobbyBtn = document.getElementById('netLobbyBtn');
const netBoardBtn = document.getElementById('netBoardBtn');

let netInterval = null;
let singleInterval = null;
let waitInterval = null;
let singleWs = null;
let currentSingleId = null;
let waitingWs = null;
let boardWs = null;
let currentBoardId = null;

function buildWaitingWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/waiting/${userId}`;
}

function buildBoardWsUrl(id) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/board/${id}`;
}

function buildSingleWsUrl(id) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/single/${id}`;
}

function formatTime(sec) {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

function setupWaitingWs() {
    if (waitingWs) return;
    waitingWs = new WebSocket(buildWaitingWsUrl());
    waitingWs.addEventListener('message', updateStatus);
    waitingWs.addEventListener('close', () => {
        waitingWs = null;
        if (waitBox.style.display === 'flex') setTimeout(setupWaitingWs, 1000);
    });
}

function setupBoardWs(id) {
    if (boardWs && currentBoardId === id) return;
    if (boardWs) boardWs.close();
    currentBoardId = id;
    boardWs = new WebSocket(buildBoardWsUrl(id));
    boardWs.addEventListener('message', e => {
        const d = JSON.parse(e.data);
        if (d.status) updateStatus();
    });
    boardWs.addEventListener('close', () => {
        boardWs = null;
        if (currentBoardId) setTimeout(() => setupBoardWs(currentBoardId), 1000);
    });
}

function setupSingleWs(id) {
    if (singleWs && currentSingleId === id) return;
    if (singleWs) singleWs.close();
    currentSingleId = id;
    singleWs = new WebSocket(buildSingleWsUrl(id));
    singleWs.addEventListener('message', e => {
        const d = JSON.parse(e.data);
        if (d.status) updateStatus();
    });
    singleWs.addEventListener('close', () => {
        singleWs = null;
        if (currentSingleId) setTimeout(() => setupSingleWs(currentSingleId), 1000);
    });
}

function clearIntervals() {
    clearInterval(netInterval);
    clearInterval(singleInterval);
    clearInterval(waitInterval);
}

async function updateStatus() {
    const res = await fetch('/api/user_status');
    if (!res.ok) return;
    const data = await res.json();
    let visible = false;
    if (data.hotseat_id) {
        visible = true;
        netBox.style.display = 'flex';
        netTitle.textContent = 'HOTSEAT - режим';
        setupBoardWs(data.hotseat_id);
        netReturn.onclick = () => window.location.href = `/hotseat/${data.hotseat_id}`;
        netLeave.onclick = async () => {
            await fetch(`/api/hotseat/end/${data.hotseat_id}`, {method: 'POST'});
            updateStatus();
        };
        clearInterval(netInterval);
        netInterval = setInterval(async () => {
            const tRes = await fetch(`/api/hotseat/timers/${data.hotseat_id}`);
            if (!tRes.ok) return;
            const t = await tRes.json();
            netTimer.textContent = formatTime(t[t.turn]);
        }, 1000);
        const tRes = await fetch(`/api/hotseat/timers/${data.hotseat_id}`);
        if (tRes.ok) {
            const t = await tRes.json();
            netTimer.textContent = formatTime(t[t.turn]);
        }
    } else if (data.board_id) {
        visible = true;
        netBox.style.display = 'flex';
        netTitle.textContent = 'Сетевая игра';
        setupBoardWs(data.board_id);
        netReturn.onclick = () => window.location.href = `/board/${data.board_id}`;
        netLeave.onclick = () => {
            leaveModal.classList.add('active');
            leaveYes.onclick = async () => {
                leaveModal.classList.remove('active');
                await fetch(`/api/resign/${data.board_id}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({player: data.color})
                });
                updateStatus();
            };
            leaveNo.onclick = () => leaveModal.classList.remove('active');
        };
        clearInterval(netInterval);
        netInterval = setInterval(async () => {
            const tRes = await fetch(`/api/timers/${data.board_id}`);
            if (!tRes.ok) return;
            const t = await tRes.json();
            netTimer.textContent = formatTime(t[data.color]);
        }, 1000);
        const tRes = await fetch(`/api/timers/${data.board_id}`);
        if (tRes.ok) {
            const t = await tRes.json();
            netTimer.textContent = formatTime(t[data.color]);
        }
    } else {
        netBox.style.display = 'none';
        netTitle.textContent = 'Сетевая игра';
        clearInterval(netInterval);
        if (boardWs) { boardWs.close(); boardWs = null; }
        currentBoardId = null;
    }

    if (data.single_game_id) {
        visible = true;
        singleBox.style.display = 'flex';
        setupSingleWs(data.single_game_id);
        singleReturn.onclick = () => window.location.href = `/singleplayer/${data.single_game_id}`;
        singleLeave.onclick = () => {
            leaveModal.classList.add('active');
            leaveYes.onclick = async () => {
                leaveModal.classList.remove('active');
                await fetch(`/api/single/resign/${data.single_game_id}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({player: data.single_color})
                });
                updateStatus();
            };
            leaveNo.onclick = () => leaveModal.classList.remove('active');
        };
        clearInterval(singleInterval);
        singleInterval = setInterval(async () => {
            const tRes = await fetch(`/api/single/timers/${data.single_game_id}`);
            if (!tRes.ok) return;
            const t = await tRes.json();
            singleTimer.textContent = formatTime(t[data.single_color]);
        }, 1000);
        const tRes = await fetch(`/api/single/timers/${data.single_game_id}`);
        if (tRes.ok) {
            const t = await tRes.json();
            singleTimer.textContent = formatTime(t[data.single_color]);
        }
    } else {
        singleBox.style.display = 'none';
        clearInterval(singleInterval);
        if (singleWs) { singleWs.close(); singleWs = null; }
        currentSingleId = null;
    }

    if (data.waiting_since) {
        visible = true;
        waitBox.style.display = 'flex';
        setupWaitingWs();
        waitReturn.onclick = () => window.location.href = `/waiting`;
        waitLeave.onclick = async () => {
            await fetch('/api/cancel_game', {method: 'POST'});
            updateStatus();
        };
        clearInterval(waitInterval);
        waitInterval = setInterval(() => {
            const sec = Math.floor((Date.now() - data.waiting_since * 1000) / 1000);
            waitTimer.textContent = formatTime(sec);
        }, 1000);
        const sec = Math.floor((Date.now() - data.waiting_since * 1000) / 1000);
        waitTimer.textContent = formatTime(sec);
    } else {
        waitBox.style.display = 'none';
        clearInterval(waitInterval);
        if (waitingWs) { waitingWs.close(); waitingWs = null; }
    }

    if (data.lobby_id) {
        visible = true;
        lobbyBox.style.display = 'flex';
        lobbyReturn.onclick = () => window.location.href = `/lobby/${data.lobby_id}`;
        lobbyLeave.onclick = async () => {
            await fetch(`/api/lobby/leave/${data.lobby_id}`, {method: 'POST'});
            updateStatus();
        };
    } else {
        lobbyBox.style.display = 'none';
    }
    statusContainer.style.display = visible ? 'flex' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    updateStatus();
    if (singleBtn) {
        singleBtn.addEventListener('click', () => {
            singleModal.classList.add('active');
        });
        singleCloseBtn.addEventListener('click', () => {
            singleModal.classList.remove('active');
        });
        startSingleBtn.addEventListener('click', async () => {
            if (currentSingleId) {
                showNotification('Вы уже находитесь в игре с ботом', 'error');
                return;
            }
            const diff = document.querySelector('input[name="difficulty"]:checked').value;
            const color = document.querySelector('input[name="spcolor"]:checked').value;
            const res = await fetch('/api/single/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ difficulty: diff, color })
            });
            const data = await res.json();
            window.location.href = `/singleplayer/${data.game_id}`;
        });
    }
    if (netBtn) {
        netBtn.addEventListener('click', e => {
            e.preventDefault();
            if (currentBoardId) {
                showNotification('Вы уже находитесь в сетевой игре', 'error');
            } else {
                netModal.classList.add('active');
            }
        });
        netSearchBtn.addEventListener('click', () => {
            window.location.href = '/waiting';
        });
        netLobbyBtn.addEventListener('click', () => {
            window.location.href = '/lobby/new';
        });
        netBoardBtn.addEventListener('click', () => {
            window.location.href = '/hotseat';
        });
    }
    [leaveModal, singleModal, netModal].forEach(o => {
        o.addEventListener('click', e => { if (e.target === o) o.classList.remove('active'); });
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            [leaveModal, singleModal, netModal].forEach(o => o.classList.remove('active'));
        }
    });
});
