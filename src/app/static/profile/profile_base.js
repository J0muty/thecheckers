document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
    }

    if (localStorage.theme === 'dark') {
        document.documentElement.classList.add('dark-mode');
        if (themeIcon) themeIcon.classList.replace('fa-moon', 'fa-sun');
    } else {
        document.documentElement.classList.remove('dark-mode');
        if (themeIcon) themeIcon.classList.replace('fa-sun', 'fa-moon');
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('dark-mode');
            localStorage.theme = isDark ? 'dark' : 'light';
            if (themeIcon) {
                themeIcon.classList.toggle('fa-moon');
                themeIcon.classList.toggle('fa-sun');
            }
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

    if (window.globalSessionToken) setupSessionWs();
});
