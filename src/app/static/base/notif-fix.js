document.addEventListener('DOMContentLoaded', () => {
    if (!document.querySelector('link[data-codex-responsive-polish]')) {
        const css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = new URL('responsive-polish.css', import.meta.url).href;
        css.dataset.codexResponsivePolish = '1';
        document.head.appendChild(css);
    }

    const bell = document.getElementById('notifBell');
    const panel = document.getElementById('notifPanel');
    if (!bell || !panel || bell.dataset.codexNotifBound === '1') return;

    bell.dataset.codexNotifBound = '1';
    bell.setAttribute('role', 'button');
    bell.setAttribute('tabindex', '0');
    bell.setAttribute('aria-label', 'Оповещения');
    bell.setAttribute('aria-expanded', panel.classList.contains('open') ? 'true' : 'false');

    const renderEmpty = () => {
        panel.innerHTML = '<div class="notification-item">Нет оповещений</div>';
    };

    const loadInvitesFallback = async () => {
        try {
            const response = await fetch('/api/invites');
            if (!response.ok) {
                renderEmpty();
                return;
            }
            const data = await response.json();
            panel.innerHTML = '';
            if (!data.invites || data.invites.length === 0) {
                renderEmpty();
                return;
            }
            data.invites.forEach(invite => {
                const item = document.createElement('div');
                item.className = 'notification-item';
                const text = document.createElement('span');
                text.textContent = invite.type === 'rematch'
                    ? `${invite.from_login} предлагает реванш`
                    : `${invite.from_login} приглашает в лобби`;

                const actions = document.createElement('div');
                actions.className = 'invite-actions';

                const accept = document.createElement('button');
                accept.className = 'invite-btn accept';
                accept.type = 'button';
                accept.innerHTML = '<i class="fa-solid fa-check"></i>';
                accept.addEventListener('click', async event => {
                    event.stopPropagation();
                    if (invite.type === 'rematch') {
                        const res = await fetch(`/api/rematch_response/${invite.board_id}?action=accept`, { method: 'POST' });
                        if (res.ok) {
                            const payload = await res.json();
                            window.location.href = `/board/${payload.board_id}`;
                        }
                    } else {
                        await fetch(`/api/lobby/respond/${invite.lobby_id}?action=accept`, { method: 'POST' });
                        window.location.href = `/lobby/${invite.lobby_id}`;
                    }
                });

                const decline = document.createElement('button');
                decline.className = 'invite-btn decline';
                decline.type = 'button';
                decline.innerHTML = '<i class="fa-solid fa-xmark"></i>';
                decline.addEventListener('click', async event => {
                    event.stopPropagation();
                    if (invite.type === 'rematch') {
                        await fetch(`/api/rematch_response/${invite.board_id}?action=decline`, { method: 'POST' });
                    } else {
                        await fetch(`/api/lobby/respond/${invite.lobby_id}?action=decline`, { method: 'POST' });
                    }
                    loadInvitesFallback();
                });

                actions.append(accept, decline);
                item.append(text, actions);
                panel.appendChild(item);
            });
        } catch {
            renderEmpty();
        }
    };

    const openPanel = () => {
        panel.classList.add('open');
        bell.setAttribute('aria-expanded', 'true');
        loadInvitesFallback();
    };

    const closePanel = () => {
        panel.classList.remove('open');
        bell.setAttribute('aria-expanded', 'false');
    };

    const togglePanel = event => {
        event.preventDefault();
        event.stopPropagation();
        panel.classList.contains('open') ? closePanel() : openPanel();
    };

    bell.addEventListener('click', togglePanel, true);
    bell.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') togglePanel(event);
    });
    panel.addEventListener('click', event => event.stopPropagation());
    document.addEventListener('click', closePanel);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closePanel();
    });
});
