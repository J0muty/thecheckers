document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
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
});
