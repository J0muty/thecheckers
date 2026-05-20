document.addEventListener('DOMContentLoaded', () => {
    function buildSessionWsUrl(token) {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/session/${token}`;
    }

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
