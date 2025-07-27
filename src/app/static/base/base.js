document.addEventListener('DOMContentLoaded', () => {
    const pending = localStorage.getItem('pendingToast');
    if (pending) {
        try {
            const { message, type } = JSON.parse(pending);
            if (message) {
                showNotification(message, type || 'success');
            }
        } catch {}
        localStorage.removeItem('pendingToast');
    }
    const root = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const setTheme = t => {
        if (t === 'dark') {
            root.classList.add('dark-mode');
            if (icon) icon.classList.replace('fa-moon', 'fa-sun');
        } else {
            root.classList.remove('dark-mode');
            if (icon) icon.classList.replace('fa-sun', 'fa-moon');
        }
        localStorage.theme = t;
    };
    setTheme(localStorage.theme === 'dark' ? 'dark' : 'light');
    const toggle = document.getElementById('theme-toggle');
    if (toggle) toggle.addEventListener('click', () => setTheme(root.classList.contains('dark-mode') ? 'light' : 'dark'));

    const bell = document.getElementById('notifBell');
    const panel = document.getElementById('notifPanel');
    const countEl = document.getElementById('notifCount');

    const buildNotifWsUrl = id => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/notifications/${id}`;
    };

    async function loadInvites() {
        const res = await fetch('/api/invites');
        if (!res.ok) return;
        const data = await res.json();
        panel.innerHTML = '';
        if (!data.invites.length) {
            panel.innerHTML = '<div class="notification-item">Нет оповещений</div>';
            if (countEl) countEl.style.display = 'none';
            return;
        }
        data.invites.forEach(inv => {
            const item = document.createElement('div');
            item.className = 'notification-item';
            const text = document.createElement('span');
            text.textContent = `${inv.from_login} приглашает в лобби`;
            const actions = document.createElement('div');
            actions.className = 'invite-actions';
            const accept = document.createElement('button');
            accept.className = 'invite-btn accept';
            accept.innerHTML = '<i class="fa-solid fa-check"></i>';
            accept.addEventListener('click', async e => {
                e.stopPropagation();
                await fetch(`/api/lobby/respond/${inv.lobby_id}?action=accept`, { method: 'POST' });
                window.location.href = `/lobby/${inv.lobby_id}`;
            });
            const decline = document.createElement('button');
            decline.className = 'invite-btn decline';
            decline.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            decline.addEventListener('click', async e => {
                e.stopPropagation();
                await fetch(`/api/lobby/respond/${inv.lobby_id}?action=decline`, { method: 'POST' });
                loadInvites();
            });
            actions.append(accept, decline);
            item.append(text, actions);
            panel.appendChild(item);
        });
        if (countEl) {
            countEl.textContent = data.invites.length;
            countEl.style.display = 'block';
        }
    }

    function setupNotifWs() {
        if (!window.globalUserId) return;
        const ws = new WebSocket(buildNotifWsUrl(window.globalUserId));
        ws.addEventListener('message', loadInvites);
        ws.addEventListener('close', () => setTimeout(setupNotifWs, 1000));
    }

    const buildSessionWsUrl = token => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/session/${token}`;
    };

    function setupSessionWs() {
        if (!window.globalSessionToken) return;
        const ws = new WebSocket(buildSessionWsUrl(window.globalSessionToken));
        ws.addEventListener('message', e => {
            try {
                const data = JSON.parse(e.data);
                if (data.action === 'logout') {
                    window.location.href = '/';
                }
            } catch {}
        });
        ws.addEventListener('close', () => setTimeout(setupSessionWs, 1000));
    }

    if (bell) {
        bell.addEventListener('click', () => {
            panel.classList.toggle('open');
            if (panel.classList.contains('open')) loadInvites();
        });
    }

    if (window.globalUserId) setupNotifWs();
    if (window.globalSessionToken) setupSessionWs();
});
