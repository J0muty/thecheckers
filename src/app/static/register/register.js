document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.toggle-password').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const pwd = document.getElementById('password');
            const pwd2 = document.getElementById('confirm-password');
            const isHidden = pwd.type === 'password';
            pwd.type = pwd2.type = isHidden ? 'text' : 'password';
            document.querySelectorAll('.toggle-password').forEach(t => {
                t.querySelector('.eye').style.display = isHidden ? 'none' : 'inline';
                t.querySelector('.eye-slash').style.display = isHidden ? 'inline' : 'none';
            });
        });
    });
const loginInput = document.getElementById('login');
    const emailInput = document.getElementById('email');
    const loginErr = document.getElementById('login-error');
    const emailErr = document.getElementById('email-error');

    let loginTimer;
    let emailTimer;

    function toggleError(input, el, show, msg = '') {
        if (show) {
            input.classList.add('error');
            el.textContent = msg;
            el.classList.add('visible');
        } else {
            input.classList.remove('error');
            el.classList.remove('visible');
        }
    }

    async function check(field, value) {
        const params = new URLSearchParams();
        params.append(field, value);
        try {
            const res = await fetch('/api/check_user?' + params.toString());
            if (!res.ok) return;
            const data = await res.json();
            if (field === 'login') {
                toggleError(loginInput, loginErr, data.login_exists, 'Данный никнейм уже занят');
            } else {
                toggleError(emailInput, emailErr, data.email_exists, 'Данная почта уже занята');
            }
        } catch {}
    }

    loginInput.addEventListener('input', () => {
        clearTimeout(loginTimer);
        const value = loginInput.value.trim();
        if (!value) {
            toggleError(loginInput, loginErr, false);
            return;
        }
        loginTimer = setTimeout(() => check('login', value), 300);
    });

    emailInput.addEventListener('input', () => {
        clearTimeout(emailTimer);
        const value = emailInput.value.trim();
        if (!value) {
            toggleError(emailInput, emailErr, false);
            return;
        }
        emailTimer = setTimeout(() => check('email', value), 300);
    });
});
