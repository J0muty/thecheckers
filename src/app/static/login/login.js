document.querySelectorAll('.toggle-password').forEach(toggle => {
    toggle.addEventListener('click', () => {
        const pwd = document.getElementById('password');
        const pwd2 = document.getElementById('confirm-password');
        const isHidden = pwd.type === 'password';
        pwd.type = isHidden ? 'text' : 'password';
        if (pwd2) {
            pwd2.type = isHidden ? 'text' : 'password';
        }
        document.querySelectorAll('.toggle-password').forEach(t => {
            t.querySelector('.eye').style.display = isHidden ? 'none' : 'inline';
            t.querySelector('.eye-slash').style.display = isHidden ? 'inline' : 'none';
        });
    });
});