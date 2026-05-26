document.addEventListener('DOMContentLoaded', () => {
    const newPass = document.getElementById('new-password');
    const confirmPass = document.getElementById('confirm-password');
    const toggles = document.querySelectorAll('.toggle-password');
    const moveModeInputs = document.querySelectorAll('input[name="move-mode"]');
    const siteSoundsInput = document.getElementById('site-sounds');
    const MOVE_MODE_KEY = 'checkerMoveMode';
    const SOUNDS_KEY = 'checkerSoundsEnabled';

    function normalizeMoveMode(mode) {
        return mode === 'drag' ? 'drag' : 'click';
    }

    function applyMoveMode(mode) {
        const nextMode = normalizeMoveMode(mode);
        window.checkerMoveMode = nextMode;
        try {
            localStorage.setItem(MOVE_MODE_KEY, nextMode);
        } catch (_) {}
        moveModeInputs.forEach(input => {
            input.checked = input.value === nextMode;
        });
        return nextMode;
    }

    async function saveMoveMode(mode) {
        const nextMode = normalizeMoveMode(mode);
        const res = await fetch('/api/settings/move-input-mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: nextMode}),
        });
        if (!res.ok) {
            throw new Error('move_mode_save_failed');
        }
        const data = await res.json();
        return applyMoveMode(data.mode);
    }

    function normalizeSoundEnabled(value) {
        return value !== false && value !== 'false' && value !== '0' && value !== 'off';
    }

    function applySoundEnabled(enabled) {
        const nextEnabled = normalizeSoundEnabled(enabled);
        window.checkerSoundsEnabled = nextEnabled;
        try {
            localStorage.setItem(SOUNDS_KEY, nextEnabled ? '1' : '0');
        } catch (_) {}
        if (siteSoundsInput) {
            siteSoundsInput.checked = nextEnabled;
        }
        return nextEnabled;
    }

    async function saveSoundEnabled(enabled) {
        const nextEnabled = normalizeSoundEnabled(enabled);
        const res = await fetch('/api/settings/effects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: nextEnabled}),
        });
        if (!res.ok) {
            throw new Error('sound_setting_save_failed');
        }
        const data = await res.json();
        return applySoundEnabled(data.enabled);
    }

    if (moveModeInputs.length) {
        let currentMoveMode = applyMoveMode(window.checkerMoveMode);
        moveModeInputs.forEach(input => {
            input.addEventListener('change', async () => {
                if (!input.checked) return;
                const previousMoveMode = currentMoveMode;
                moveModeInputs.forEach(item => { item.disabled = true; });
                try {
                    currentMoveMode = await saveMoveMode(input.value);
                    if (typeof showNotification === 'function') {
                        showNotification('Настройка хода сохранена', 'success');
                    }
                } catch (error) {
                    currentMoveMode = applyMoveMode(previousMoveMode);
                    if (typeof showNotification === 'function') {
                        showNotification('Не удалось сохранить настройку', 'error');
                    }
                } finally {
                    moveModeInputs.forEach(item => { item.disabled = false; });
                }
            });
        });
    }

    if (siteSoundsInput) {
        let currentSoundEnabled = applySoundEnabled(window.checkerSoundsEnabled);
        siteSoundsInput.addEventListener('change', async () => {
            const previousSoundEnabled = currentSoundEnabled;
            siteSoundsInput.disabled = true;
            try {
                currentSoundEnabled = await saveSoundEnabled(siteSoundsInput.checked);
                if (typeof showNotification === 'function') {
                    showNotification(
                        currentSoundEnabled ? 'Звуки сайта включены' : 'Звуки сайта отключены',
                        'success'
                    );
                }
            } catch (error) {
                currentSoundEnabled = applySoundEnabled(previousSoundEnabled);
                if (typeof showNotification === 'function') {
                    showNotification('Не удалось сохранить настройку звуков', 'error');
                }
            } finally {
                siteSoundsInput.disabled = false;
            }
        });
    }

    toggles.forEach(toggle => {
        const toggleVisibility = () => {
            const isHidden = newPass.type === 'password';
            [newPass, confirmPass].forEach(inp => { if (inp) inp.type = isHidden ? 'text' : 'password'; });
            toggles.forEach(tg => {
                tg.querySelector('.eye').style.display = isHidden ? 'none' : 'inline';
                tg.querySelector('.eye-slash').style.display = isHidden ? 'inline' : 'none';
                tg.setAttribute('aria-label', isHidden ? 'Скрыть пароль' : 'Показать пароль');
            });
        };
        toggle.addEventListener('click', toggleVisibility);
        toggle.addEventListener('keydown', event => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            event.preventDefault();
            toggleVisibility();
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
            const icon = document.createElement('span');
            icon.className = 'device-icon';
            icon.innerHTML = `<i class="fa-solid ${s.device === 'mobile' ? 'fa-mobile-screen-button' : 'fa-desktop'}"></i>`;

            const info = document.createElement('span');
            info.textContent = `${s.browser} • ${s.city || s.ip}`;

            const button = document.createElement('button');
            button.className = 'logout-device';
            button.dataset.token = s.id;
            button.type = 'button';
            button.textContent = 'Выйти';

            li.append(icon, info, button);
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
    
    const delBtn = document.getElementById('delete-account-btn');
    const delModal = document.getElementById('delete-modal');
    const delClose = document.getElementById('delete-close');
    const delForm = document.getElementById('delete-form');
    const stepLogin = document.getElementById('delete-step-login');
    const stepCode = document.getElementById('delete-step-code');
    const stepConfirm = document.getElementById('delete-step-confirm');
    const nextLogin = document.getElementById('del-next');
    const nextCode = document.getElementById('del-next-code');
    const confirmBtn = document.getElementById('del-confirm');
    const cancelBtn = document.getElementById('del-cancel');
    const loginInput = document.getElementById('del-login');
    const passInput = document.getElementById('del-password');
    const codeInputDel = document.getElementById('del-code');


    function showDelModal() {
        delModal.classList.remove('hidden');
        stepLogin.classList.remove('hidden');
        if (stepCode) stepCode.classList.add('hidden');
        stepConfirm.classList.add('hidden');
    }
    function hideDelModal() {
        delModal.classList.add('hidden');
    }

    if (delBtn) delBtn.addEventListener('click', e => { e.preventDefault(); showDelModal(); });
    if (delClose) delClose.addEventListener('click', hideDelModal);
    if (nextLogin) nextLogin.addEventListener('click', e => {
        e.preventDefault();
        if (stepCode) {
            stepLogin.classList.add('hidden');
            stepCode.classList.remove('hidden');
        } else {
            stepLogin.classList.add('hidden');
            stepConfirm.classList.remove('hidden');
        }
    });
    if (nextCode) nextCode.addEventListener('click', e => {
        e.preventDefault();
        stepCode.classList.add('hidden');
        stepConfirm.classList.remove('hidden');
    });
    if (cancelBtn) cancelBtn.addEventListener('click', hideDelModal);
    if (confirmBtn) confirmBtn.addEventListener('click', async e => {
        e.preventDefault();
        const params = new URLSearchParams({
            login: loginInput.value.trim(),
            password: passInput.value,
        });
        if (codeInputDel) params.append('code', codeInputDel.value.trim());
        const resp = await fetch('/api/delete_account', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: params
        });
        if (resp.ok) {
            window.location.href = '/';
        } else {
            const data = await resp.json().catch(() => ({}));
            showNotification(data.error || 'Ошибка удаления', 'error');
            hideDelModal();
        }
    });
    if (delForm) {
        delForm.addEventListener('submit', e => {
            e.preventDefault();
        });
        stepConfirm.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                hideDelModal();
            }
        });
    }

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
