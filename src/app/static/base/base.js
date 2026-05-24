(function () {
    function setVh() {
        document.documentElement.style.setProperty('--vh', `${window.innerHeight * 0.01}px`);
    }

    setVh();
    window.addEventListener('resize', setVh);
})();

document.addEventListener('DOMContentLoaded', () => {
    showPendingToast();
    initThemeToggle();
    initWalletStrip();
    initNotificationPanel();
    initSessionWs();
});

function showPendingToast() {
    const pending = localStorage.getItem('pendingToast');
    if (!pending) return;

    try {
        const { message, type } = JSON.parse(pending);
        if (message && typeof window.showNotification === 'function') {
            showNotification(message, type || 'success');
        }
    } catch {}

    localStorage.removeItem('pendingToast');
}

function initThemeToggle() {
    const root = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const toggle = document.getElementById('theme-toggle');

    const setTheme = theme => {
        root.classList.toggle('dark-mode', theme === 'dark');
        if (icon) {
            icon.classList.toggle('fa-sun', theme === 'dark');
            icon.classList.toggle('fa-moon', theme !== 'dark');
        }
        if (toggle) {
            toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
            toggle.setAttribute('aria-label', theme === 'dark' ? 'Включить светлую тему' : 'Включить темную тему');
            toggle.title = theme === 'dark' ? 'Светлая тема' : 'Темная тема';
        }
        localStorage.theme = theme;
    };

    const initialTheme = localStorage.theme === 'dark' || localStorage.theme === 'light'
        ? localStorage.theme
        : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

    setTheme(initialTheme);
    if (toggle) {
        toggle.addEventListener('click', () => setTheme(root.classList.contains('dark-mode') ? 'light' : 'dark'));
    }
}

async function initWalletStrip() {
    const strip = document.querySelector('[data-wallet-strip]');
    if (!strip || !window.globalUserId || String(window.globalUserId).startsWith('ghost_')) return;
    try {
        const response = await fetch('/api/wallet', {cache: 'no-store'});
        if (!response.ok) return;
        const wallet = await response.json();
        const soft = strip.querySelector('[data-soft-balance]');
        const rub = strip.querySelector('[data-rub-balance]');
        if (soft) soft.textContent = Number(wallet.soft_balance || 0).toLocaleString('ru-RU');
        if (rub) rub.textContent = Number(wallet.rub_balance || 0).toLocaleString('ru-RU');
        strip.hidden = false;
    } catch (error) {
        console.error('Failed to load wallet:', error);
    }
}

function initNotificationPanel() {
    const bell = document.getElementById('notifBell');
    const panel = document.getElementById('notifPanel');
    const countEl = document.getElementById('notifCount');
    const canUseNotifications = Boolean(
        bell &&
        panel &&
        window.globalUserId &&
        !String(window.globalUserId).startsWith('ghost_')
    );

    if (!bell || !panel) return;

    bell.dataset.codexNotifBound = '1';
    bell.setAttribute('role', 'button');
    bell.setAttribute('tabindex', '0');
    bell.setAttribute('aria-label', 'Оповещения');
    bell.setAttribute('aria-expanded', 'false');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Оповещения');
    panel.setAttribute('aria-hidden', 'true');

    const buildNotifWsUrl = id => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/notifications/${id}`;
    };

    const formatInviteCount = count => {
        if (!count) return 'Нет новых';
        const mod10 = count % 10;
        const mod100 = count % 100;
        const word = mod10 === 1 && mod100 !== 11
            ? 'приглашение'
            : (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'приглашения' : 'приглашений');
        return `${count} ${word}`;
    };

    const setCount = value => {
        if (!countEl) return;
        if (!value) {
            countEl.style.display = 'none';
            countEl.textContent = '';
            return;
        }
        countEl.textContent = value > 99 ? '99+' : String(value);
        countEl.style.display = 'inline-flex';
    };

    const createShell = metaText => {
        panel.replaceChildren();

        const header = document.createElement('div');
        header.className = 'notification-panel-header';

        const titleWrap = document.createElement('div');
        titleWrap.className = 'notification-heading';

        const title = document.createElement('strong');
        title.textContent = 'Оповещения';

        const meta = document.createElement('span');
        meta.textContent = metaText;

        const close = document.createElement('button');
        close.className = 'notification-close';
        close.type = 'button';
        close.setAttribute('aria-label', 'Закрыть оповещения');
        close.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        close.addEventListener('click', closePanel);

        titleWrap.append(title, meta);
        header.append(titleWrap, close);

        const list = document.createElement('div');
        list.className = 'notification-list';

        panel.append(header, list);
        return list;
    };

    const renderStatus = (kind, text) => {
        const metaText = kind === 'loading' ? 'Загрузка' : (kind === 'error' ? 'Ошибка' : 'Нет новых');
        const list = createShell(metaText);
        const empty = document.createElement('div');
        empty.className = `notification-empty notification-empty-${kind}`;

        const icon = document.createElement('span');
        icon.className = 'notification-empty-icon';
        icon.innerHTML = kind === 'error'
            ? '<i class="fa-solid fa-triangle-exclamation"></i>'
            : '<i class="fa-solid fa-bell"></i>';

        const message = document.createElement('span');
        message.textContent = text;

        empty.append(icon, message);
        list.appendChild(empty);
    };

    const createInviteButton = (className, label, iconClass) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `invite-btn ${className}`;
        button.setAttribute('aria-label', label);
        button.title = label;
        button.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
        return button;
    };

    const createInviteItem = invite => {
        const item = document.createElement('div');
        item.className = 'notification-item notification-invite';

        const icon = document.createElement('span');
        icon.className = 'notification-icon';
        icon.innerHTML = invite.type === 'rematch'
            ? '<i class="fa-solid fa-rotate-right"></i>'
            : '<i class="fa-solid fa-chess-board"></i>';

        const content = document.createElement('span');
        content.className = 'notification-content';

        const title = document.createElement('strong');
        title.textContent = invite.type === 'rematch' ? 'Реванш' : 'Лобби';

        const text = document.createElement('span');
        text.textContent = invite.type === 'rematch'
            ? `${invite.from_login} предлагает реванш`
            : `${invite.from_login} приглашает в лобби`;

        const actions = document.createElement('div');
        actions.className = 'invite-actions';

        const accept = createInviteButton('accept', 'Принять', 'fa-check');
        accept.addEventListener('click', async event => {
            event.stopPropagation();
            if (invite.type === 'rematch') {
                const response = await fetch(`/api/rematch_response/${invite.board_id}?action=accept`, { method: 'POST' });
                if (response.ok) {
                    const payload = await response.json();
                    window.location.href = `/board/${payload.board_id}`;
                }
                return;
            }
            await fetch(`/api/lobby/respond/${invite.lobby_id}?action=accept`, { method: 'POST' });
            window.location.href = `/lobby/${invite.lobby_id}`;
        });

        const decline = createInviteButton('decline', 'Отклонить', 'fa-xmark');
        decline.addEventListener('click', async event => {
            event.stopPropagation();
            if (invite.type === 'rematch') {
                await fetch(`/api/rematch_response/${invite.board_id}?action=decline`, { method: 'POST' });
            } else {
                await fetch(`/api/lobby/respond/${invite.lobby_id}?action=decline`, { method: 'POST' });
            }
            await loadInvites();
        });

        content.append(title, text);
        actions.append(accept, decline);
        item.append(icon, content, actions);
        return item;
    };

    const renderInvites = invites => {
        const list = createShell(formatInviteCount(invites.length));
        setCount(invites.length);

        if (!invites.length) {
            renderStatus('empty', 'Пока ничего нового');
            return;
        }

        invites.forEach(invite => list.appendChild(createInviteItem(invite)));
    };

    async function loadInvites() {
        if (!canUseNotifications) return;
        if (panel.classList.contains('open')) renderStatus('loading', 'Загружаем приглашения');

        try {
            const response = await fetch('/api/invites');
            if (!response.ok) {
                renderStatus('error', 'Не удалось загрузить оповещения');
                return;
            }
            const data = await response.json();
            renderInvites(Array.isArray(data.invites) ? data.invites : []);
        } catch {
            renderStatus('error', 'Не удалось загрузить оповещения');
        }
    }

    function openPanel() {
        panel.classList.add('open');
        panel.setAttribute('aria-hidden', 'false');
        bell.setAttribute('aria-expanded', 'true');
        loadInvites();
    }

    function closePanel() {
        panel.classList.remove('open');
        panel.setAttribute('aria-hidden', 'true');
        bell.setAttribute('aria-expanded', 'false');
    }

    const togglePanel = event => {
        event.preventDefault();
        event.stopPropagation();
        panel.classList.contains('open') ? closePanel() : openPanel();
    };

    const setupNotifWs = () => {
        if (!canUseNotifications || window.__notifWsStarted) return;
        window.__notifWsStarted = true;
        const ws = new WebSocket(buildNotifWsUrl(window.globalUserId));
        window.__notifWs = ws;

        ws.addEventListener('message', event => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'rematch_start') {
                    window.location.href = `/board/${data.board_id}`;
                    return;
                }
                if (data.type === 'lobby_start') {
                    window.location.href = `/board/${data.board_id}`;
                    return;
                }
                if (data.type === 'rematch_decline') {
                    const message = data.from_login ? `${data.from_login} отклонил реванш` : 'Реванш отклонён';
                    if (typeof window.showNotification === 'function') showNotification(message, 'error');
                    return;
                }
            } catch {}
            loadInvites();
        });

        ws.addEventListener('close', () => {
            if (window.__notifWs === ws) {
                window.__notifWsStarted = false;
                window.__notifWs = null;
                setTimeout(setupNotifWs, 1000);
            }
        });
    };

    bell.addEventListener('click', togglePanel);
    bell.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') togglePanel(event);
    });
    panel.addEventListener('click', event => event.stopPropagation());
    document.addEventListener('click', closePanel);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closePanel();
    });

    if (canUseNotifications) {
        setupNotifWs();
        loadInvites();
    }
}

function initSessionWs() {
    if (!window.globalSessionToken || window.__sessionWsStarted) return;

    const buildSessionWsUrl = token => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/session/${token}`;
    };

    window.__sessionWsStarted = true;
    const ws = new WebSocket(buildSessionWsUrl(window.globalSessionToken));
    window.__sessionWs = ws;

    ws.addEventListener('message', event => {
        try {
            const data = JSON.parse(event.data);
            if (data.action === 'logout') {
                window.location.href = '/';
            }
        } catch {}
    });

    ws.addEventListener('close', () => {
        if (window.__sessionWs === ws) {
            window.__sessionWsStarted = false;
            window.__sessionWs = null;
            setTimeout(initSessionWs, 1000);
        }
    });
}
