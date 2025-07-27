document.addEventListener('DOMContentLoaded', () => {
    function buildSessionWsUrl(token) {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/session/${token}`;
    }

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