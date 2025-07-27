document.addEventListener('DOMContentLoaded', () => {
    const newPass = document.getElementById('new-password');
    const confirmPass = document.getElementById('confirm-password');
    const toggles = document.querySelectorAll('.toggle-password');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const isHidden = newPass.type === 'password';
            [newPass, confirmPass].forEach(inp => { if (inp) inp.type = isHidden ? 'text' : 'password'; });
            toggles.forEach(tg => {
                tg.querySelector('.eye').style.display = isHidden ? 'none' : 'inline';
                tg.querySelector('.eye-slash').style.display = isHidden ? 'inline' : 'none';
            });
        });
    });

    async function loadSessions() {
        const res = await fetch('/api/sessions');
        if (!res.ok) return;
        const data = await res.json();
        const list = document.querySelector('.device-list');
        if (!list) return;
        list.innerHTML = '';
        data.sessions.forEach(s => {
            const li = document.createElement('li');
            li.innerHTML = `<span class="device-icon">${s.device === 'mobile' ? '📱' : '💻'}</span> ${s.browser} • ${s.city || s.ip} <button class="logout-device" data-token="${s.id}">Выйти</button>`;
            list.appendChild(li);
        });
        document.querySelectorAll('.logout-device').forEach(btn => {
            btn.addEventListener('click', async () => {
                const token = btn.dataset.token;
                const resp = await fetch('/api/sessions/logout', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: new URLSearchParams({token})
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.logged_out) {
                        window.location.href = '/';
                        return;
                    }
                }
                btn.parentElement.remove();
            });
        });
    }

    const logoutAll = document.getElementById('logout-all-btn');
    if (logoutAll) {
        logoutAll.addEventListener('click', async e => {
            e.preventDefault();
            const resp = await fetch('/api/sessions/logout_all', {method: 'POST'});
            if (resp.ok) {
                const data = await resp.json();
                if (data.logged_out) {
                    window.location.href = '/';
                    return;
                }
            }
            loadSessions();
        });
    }

    const showModal = () => document.getElementById('twofa-modal').classList.remove('hidden');
    const hideModal = () => document.getElementById('twofa-modal').classList.add('hidden');

    const setupBtn = document.getElementById('setup-2fa-btn');
    const disableBtn = document.getElementById('disable-2fa-btn');
    const closeBtn = document.getElementById('twofa-close');
    const form = document.getElementById('twofa-form');
    const codeInput = document.getElementById('twofa-code');
    const title = document.getElementById('twofa-title');
    const qrBox = document.getElementById('qrcode');
    const secretText = document.getElementById('secret-text');
    let mode = 'enable';

    if (setupBtn) {
        setupBtn.addEventListener('click', async e => {
            e.preventDefault();
            mode = 'enable';
            const res = await fetch('/api/2fa/setup/start', {method: 'POST'});
            if (!res.ok) {
                showNotification('Ошибка при генерации секрета', 'error');
                return;
            }
            const data = await res.json();
            qrBox.innerHTML = '';
            new QRCode(qrBox, {text: data.uri, width: 180, height: 180, correctLevel: QRCode.CorrectLevel.M});
            qrBox.classList.remove('hidden');
            secretText.parentElement.classList.remove('hidden');
            secretText.textContent = data.secret;
            title.textContent = 'Настройка 2FA';
            codeInput.value = '';
            showModal();
        });
    }

    if (disableBtn) {
        disableBtn.addEventListener('click', e => {
            e.preventDefault();
            mode = 'disable';
            qrBox.innerHTML = '';
            qrBox.classList.add('hidden');
            secretText.textContent = '';
            secretText.parentElement.classList.add('hidden');
            title.textContent = 'Отключение 2FA';
            codeInput.value = '';
            showModal();
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', hideModal);
    }

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const code = codeInput.value.trim();
        const url = mode === 'enable' ? '/api/2fa/enable' : '/api/2fa/disable';
        const resp = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({code})
        });
        if (!resp.ok) {
            showNotification('Неверный код', 'error');
            return;
        }
        hideModal();
        const okMsg = mode === 'enable' ? 'Аутентификатор подключен' : 'Аутентификатор отключен';
        showNotification(okMsg, 'success');
        setTimeout(() => location.reload(), 700);
    });

    ['change-password-btn','change-email-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.addEventListener('click', e => {
                e.preventDefault();
                showNotification('Функционал ещё не реализован');
            });
        }
    });

    const buildWsUrl = uid => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/sessions/${uid}`;
    };

    function setupWs() {
        if (!window.globalUserId) return;
        const ws = new WebSocket(buildWsUrl(window.globalUserId));
        ws.addEventListener('message', loadSessions);
        ws.addEventListener('close', () => setTimeout(setupWs, 1000));
    }

    loadSessions();
    if (window.globalUserId) setupWs();
});
