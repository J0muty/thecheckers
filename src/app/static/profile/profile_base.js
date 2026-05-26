document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');

    const initTapFocusCleanup = () => {
        const interactiveSelector = 'a, button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"], .btn, .btn-icon, .theme-toggle, .nav-item, .menu-item';
        const shouldCleanFocus = () => window.matchMedia('(max-width: 970px), (hover: none)').matches;

        document.addEventListener('pointerup', event => {
            if (!shouldCleanFocus() || event.pointerType === 'mouse') return;
            const target = event.target.closest(interactiveSelector);
            if (!target) return;
            window.setTimeout(() => {
                const focused = document.activeElement;
                if (focused && focused !== document.body && focused.matches(interactiveSelector)) {
                    focused.blur();
                }
                if (target.matches(interactiveSelector) && typeof target.blur === 'function') {
                    target.blur();
                }
            }, 0);
        }, true);
    };

    initTapFocusCleanup();

    if (toggleBtn && sidebar) {
        const toggleIcon = toggleBtn.querySelector('i');
        let swipeStartX = 0;
        let swipeStartY = 0;
        let isTrackingSwipe = false;

        const setSidebarOpen = isOpen => {
            sidebar.classList.toggle('open', isOpen);
            sidebar.classList.remove('swiping');
            sidebar.style.setProperty('--sidebar-drag-x', '0px');
            sidebar.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
            toggleBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            toggleBtn.setAttribute('aria-label', isOpen ? 'Закрыть меню' : 'Открыть меню');
            if (toggleIcon) {
                toggleIcon.classList.toggle('fa-bars', !isOpen);
                toggleIcon.classList.toggle('fa-xmark', isOpen);
            }
        };

        toggleBtn.addEventListener('click', event => {
            event.stopPropagation();
            setSidebarOpen(!sidebar.classList.contains('open'));
        });

        sidebar.addEventListener('click', event => {
            event.stopPropagation();
        });

        sidebar.addEventListener('touchstart', event => {
            if (!sidebar.classList.contains('open') || !event.touches.length) return;
            const touch = event.touches[0];
            swipeStartX = touch.clientX;
            swipeStartY = touch.clientY;
            isTrackingSwipe = true;
        }, { passive: true });

        sidebar.addEventListener('touchmove', event => {
            if (!isTrackingSwipe || !event.touches.length) return;
            const touch = event.touches[0];
            const deltaX = touch.clientX - swipeStartX;
            const deltaY = touch.clientY - swipeStartY;
            const shouldDrag = sidebar.classList.contains('swiping') || (deltaX < -18 && Math.abs(deltaX) > Math.abs(deltaY) * 1.3);

            if (shouldDrag) {
                const maxDrag = sidebar.getBoundingClientRect().width;
                const dragX = Math.max(Math.min(deltaX, 0), -maxDrag);
                sidebar.classList.add('swiping');
                sidebar.style.setProperty('--sidebar-drag-x', `${dragX}px`);
            }
        }, { passive: true });

        const finishSwipe = event => {
            if (!isTrackingSwipe) return;
            const touch = event.changedTouches && event.changedTouches[0];
            isTrackingSwipe = false;
            sidebar.classList.remove('swiping');
            if (!touch) {
                sidebar.style.setProperty('--sidebar-drag-x', '0px');
                return;
            }

            const deltaX = touch.clientX - swipeStartX;
            const deltaY = touch.clientY - swipeStartY;
            if (deltaX < -64 && Math.abs(deltaX) > Math.abs(deltaY) * 1.25) {
                const maxDrag = sidebar.getBoundingClientRect().width;
                sidebar.style.setProperty('--sidebar-drag-x', `${-maxDrag}px`);
                setSidebarOpen(false);
            } else {
                sidebar.style.setProperty('--sidebar-drag-x', '0px');
            }
        };

        sidebar.addEventListener('touchend', finishSwipe, { passive: true });
        sidebar.addEventListener('touchcancel', finishSwipe, { passive: true });

        document.addEventListener('click', () => {
            if (sidebar.classList.contains('open')) {
                setSidebarOpen(false);
            }
        });

        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && sidebar.classList.contains('open')) {
                setSidebarOpen(false);
                toggleBtn.focus();
            }
        });

        setSidebarOpen(false);
    }

    const applyTheme = theme => {
        document.documentElement.classList.toggle('dark-mode', theme === 'dark');
        localStorage.theme = theme;
        if (themeIcon) {
            themeIcon.classList.toggle('fa-sun', theme === 'dark');
            themeIcon.classList.toggle('fa-moon', theme !== 'dark');
        }
        if (themeToggle) {
            themeToggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
            themeToggle.setAttribute('aria-label', theme === 'dark' ? 'Включить светлую тему' : 'Включить темную тему');
            themeToggle.title = theme === 'dark' ? 'Светлая тема' : 'Темная тема';
        }
    };

    const initialTheme = localStorage.theme === 'dark' || localStorage.theme === 'light'
        ? localStorage.theme
        : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(initialTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            applyTheme(document.documentElement.classList.contains('dark-mode') ? 'light' : 'dark');
        });
    }

    document.querySelectorAll('.nav-item').forEach(item => {
        if (item.getAttribute('href') === window.location.pathname) {
            item.classList.add('active');
        }
    });

    const buildSessionWsUrl = token => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/session/${token}`;
    };

    function setupSessionWs() {
        if (!window.globalSessionToken || window.__sessionWsStarted) return;
        window.__sessionWsStarted = true;
        const ws = new WebSocket(buildSessionWsUrl(window.globalSessionToken));
        window.__sessionWs = ws;
        ws.addEventListener('message', e => {
            try {
                const data = JSON.parse(e.data);
                if (data.action === 'logout') {
                    window.location.href = '/';
                }
            } catch {}
        });
        ws.addEventListener('close', () => {
            if (window.__sessionWs === ws) {
                window.__sessionWsStarted = false;
                window.__sessionWs = null;
                setTimeout(setupSessionWs, 1000);
            }
        });
    }

    if (window.globalSessionToken) setupSessionWs();

    async function loadTopbarWallet() {
        try {
            const res = await fetch('/api/wallet', {cache: 'no-store'});
            if (!res.ok) return;
            const wallet = await res.json();
            document.querySelectorAll('[data-soft-balance]').forEach(el => {
                el.textContent = Number(wallet.soft_balance || 0).toLocaleString('ru-RU');
            });
            document.querySelectorAll('[data-rub-balance]').forEach(el => {
                el.textContent = Number(wallet.rub_balance || 0).toLocaleString('ru-RU');
            });
        } catch (error) {
            console.error('Failed to load wallet:', error);
        }
    }

    loadTopbarWallet();
});
