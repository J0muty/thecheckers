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
let currentNetTimerColor = null;
let currentSingleTimerColor = null;

function resultNotificationKey(boardId) {
    return `resultToastShown:${boardId}`;
}

function formatEloDelta(delta) {
    if (typeof delta !== 'number') return '';
    if (delta > 0) return ` и получили +${delta} ELO`;
    if (delta < 0) return ` и потеряли ${Math.abs(delta)} ELO`;
    return ' и не потеряли ELO';
}

function buildGameResultMessage(data, color) {
    if (!data?.status) return null;
    const delta = color && data.rating_change ? data.rating_change[color] : undefined;
    const eloText = formatEloDelta(delta);

    if (data.status === 'draw') {
        return `Ничья${eloText}`;
    }

    if (data.status !== 'white_win' && data.status !== 'black_win') {
        return `Игра завершена${eloText}`;
    }

    const winner = data.status === 'white_win' ? 'white' : 'black';
    if (color) {
        return color === winner
            ? `Вы выиграли${eloText}`
            : `Вы проиграли${eloText}`;
    }

    return winner === 'white' ? 'Белые выиграли' : 'Чёрные выиграли';
}

function showHomeNotification(message, type = 'success', duration = 5200) {
    if (typeof window.showNotification === 'function') {
        showNotification(message, type, duration);
        return;
    }

    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type} show`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.innerHTML = type === 'error'
        ? '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 17h.01"/></svg>'
        : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

    const body = document.createElement('span');
    body.className = 'toast-message';
    body.textContent = message;

    const close = document.createElement('button');
    close.className = 'toast-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Закрыть уведомление');
    close.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';

    const progress = document.createElement('span');
    progress.className = 'toast-progress';
    progress.setAttribute('aria-hidden', 'true');

    const closeToast = () => {
        toast.classList.remove('show');
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
            if (!container.children.length) container.remove();
        }, 260);
    };

    close.addEventListener('click', closeToast);
    toast.append(icon, body, close, progress);
    container.appendChild(toast);
    setTimeout(closeToast, duration);
}

function showGameResultNotification(boardId, data, color) {
    if (!boardId || !data?.status) return;
    const key = resultNotificationKey(boardId);
    if (sessionStorage.getItem(key) === '1') return;
    sessionStorage.setItem(key, '1');

    const message = buildGameResultMessage(data, color);
    if (!message) return;

    const myWon = color && (
        (data.status === 'white_win' && color === 'white') ||
        (data.status === 'black_win' && color === 'black') ||
        data.status === 'draw'
    );
    showHomeNotification(message, myWon ? 'success' : 'error', 5200);
}

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

function stopNetClock() {
    clearInterval(netInterval);
    netInterval = null;
}

function stopSingleClock() {
    clearInterval(singleInterval);
    singleInterval = null;
}

function activeTimerKey(timers, displayColor) {
    if (displayColor === 'white' || displayColor === 'black') return displayColor;
    return timers?.turn === 'black' ? 'black' : 'white';
}

function timerSeconds(timers, displayColor, startedAt) {
    if (!timers) return 0;
    const key = activeTimerKey(timers, displayColor);
    let value = Number(timers[key] ?? 0);
    if (timers.turn === key) {
        value -= (Date.now() - startedAt) / 1000;
    }
    return Math.max(0, value);
}

function startClock(kind, timerEl, timers, displayColor) {
    const startedAt = Date.now();
    const tick = () => {
        timerEl.textContent = formatTime(timerSeconds(timers, displayColor, startedAt));
    };
    const stopClock = kind === 'net' ? stopNetClock : stopSingleClock;
    stopClock();
    tick();
    if (timers?.turn === 'white' || timers?.turn === 'black') {
        const interval = setInterval(tick, 1000);
        if (kind === 'net') netInterval = interval;
        else singleInterval = interval;
    }
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

function setupBoardWs(id, displayColor = null) {
    currentNetTimerColor = displayColor;
    if (boardWs && currentBoardId === id) return;
    if (boardWs) boardWs.close();
    currentBoardId = id;
    boardWs = new WebSocket(buildBoardWsUrl(id));
    boardWs.addEventListener('message', e => {
        const d = JSON.parse(e.data);
        if (d.timers) startClock('net', netTimer, d.timers, currentNetTimerColor);
        if (d.status) {
            showGameResultNotification(id, d, currentNetTimerColor);
            netBox.style.display = 'none';
            stopNetClock();
            updateStatus();
        }
    });
    boardWs.addEventListener('close', () => {
        boardWs = null;
        if (currentBoardId) setTimeout(() => setupBoardWs(currentBoardId), 1000);
    });
}

function setupSingleWs(id, displayColor = null) {
    currentSingleTimerColor = displayColor;
    if (singleWs && currentSingleId === id) return;
    if (singleWs) singleWs.close();
    currentSingleId = id;
    singleWs = new WebSocket(buildSingleWsUrl(id));
    singleWs.addEventListener('message', e => {
        const d = JSON.parse(e.data);
        if (d.timers) startClock('single', singleTimer, d.timers, currentSingleTimerColor);
        if (d.status) updateStatus();
    });
    singleWs.addEventListener('close', () => {
        singleWs = null;
        if (currentSingleId) setTimeout(() => setupSingleWs(currentSingleId), 1000);
    });
}

function clearIntervals() {
    stopNetClock();
    stopSingleClock();
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
        setupBoardWs(data.hotseat_id, null);
        netReturn.onclick = () => window.location.href = `/hotseat/${data.hotseat_id}`;
        netLeave.onclick = async () => {
            await fetch(`/api/hotseat/end/${data.hotseat_id}`, {method: 'POST'});
            updateStatus();
        };
        startClock('net', netTimer, data.hotseat_timers, null);
    } else if (data.board_id && data.board_timers?.turn !== 'stopped') {
        visible = true;
        netBox.style.display = 'flex';
        netTitle.textContent = 'Сетевая игра';
        setupBoardWs(data.board_id, data.color);
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
        startClock('net', netTimer, data.board_timers, data.color);
    } else {
        netBox.style.display = 'none';
        netTitle.textContent = 'Сетевая игра';
        stopNetClock();
        if (boardWs) { boardWs.close(); boardWs = null; }
        currentBoardId = null;
        currentNetTimerColor = null;
    }

    if (data.single_game_id) {
        visible = true;
        singleBox.style.display = 'flex';
        setupSingleWs(data.single_game_id, data.single_color);
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
        startClock('single', singleTimer, data.single_timers, data.single_color);
    } else {
        singleBox.style.display = 'none';
        stopSingleClock();
        if (singleWs) { singleWs.close(); singleWs = null; }
        currentSingleId = null;
        currentSingleTimerColor = null;
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
            const diff = Math.max(Date.now() - data.waiting_since * 1000, 0);
            const sec = Math.floor(diff / 1000);
            waitTimer.textContent = formatTime(sec);
        }, 1000);
        const diff = Math.max(Date.now() - data.waiting_since * 1000, 0);
        const sec = Math.floor(diff / 1000);
        waitTimer.textContent = formatTime(sec);
    } else {
        waitBox.style.display = 'none';
        clearInterval(waitInterval);
        if (waitingWs) { waitingWs.close(); waitingWs = null; }
    }

    if (data.lobby_id && !data.board_id) {
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
        if (singleCloseBtn) {
            singleCloseBtn.addEventListener('click', () => {
                singleModal.classList.remove('active');
            });
        }
        if (startSingleBtn) {
            startSingleBtn.addEventListener('click', async () => {
                if (currentSingleId) {
                    showNotification('Вы уже находитесь в игре с ботом', 'error');
                    return;
                }
                const diff = document.querySelector('input[name="difficulty"]:checked').value;
                const color = document.querySelector('input[name="spcolor"]:checked').value;
                startSingleBtn.disabled = true;
                try {
                    const res = await fetch('/api/single/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ difficulty: diff, color })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.game_id) {
                            window.location.href = `/singleplayer/${data.game_id}`;
                            return;
                        }
                    }
                    if (res.status === 401 || res.status === 403) {
                        const params = new URLSearchParams({ difficulty: diff, color });
                        window.location.href = `/singleplayer?${params.toString()}`;
                        return;
                    }
                    showNotification('Не удалось начать одиночную игру', 'error');
                } catch {
                    showNotification('Сервер недоступен. Попробуйте ещё раз', 'error');
                } finally {
                    startSingleBtn.disabled = false;
                }
            });
        }
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

        netSearchBtn && netSearchBtn.addEventListener('click', () => {
            window.location.href = '/waiting';
        });

        netLobbyBtn && netLobbyBtn.addEventListener('click', () => {
            window.location.href = '/lobby/new';
        });

        netBoardBtn && netBoardBtn.addEventListener('click', () => {
            window.location.href = '/hotseat';
        });
    }

    [leaveModal, singleModal, netModal].filter(Boolean).forEach(o => {
        o.addEventListener('click', e => {
            if (e.target === o) o.classList.remove('active');
        });
        o.querySelectorAll('[data-close-modal]').forEach(btn => {
            btn.addEventListener('click', () => o.classList.remove('active'));
        });
    });

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            [leaveModal, singleModal, netModal].filter(Boolean).forEach(o => o.classList.remove('active'));
        }
    });
});
