(function () {
    const root = document.documentElement;

    function preferredTheme() {
        if (localStorage.theme === 'dark' || localStorage.theme === 'light') {
            return localStorage.theme;
        }
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark'
            : 'light';
    }

    function updateThemeControl(theme) {
        const icon = document.getElementById('theme-icon');
        const toggle = document.getElementById('theme-toggle');
        if (icon) {
            icon.classList.toggle('fa-sun', theme === 'dark');
            icon.classList.toggle('fa-moon', theme !== 'dark');
        }
        if (toggle) {
            toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
            toggle.setAttribute('aria-label', theme === 'dark' ? 'Включить светлую тему' : 'Включить темную тему');
            toggle.title = theme === 'dark' ? 'Светлая тема' : 'Темная тема';
        }
    }

    function setTheme(theme) {
        root.classList.toggle('dark-mode', theme === 'dark');
        localStorage.theme = theme;
        updateThemeControl(theme);
    }

    document.addEventListener('DOMContentLoaded', () => {
        setTheme(preferredTheme());
        const toggle = document.getElementById('theme-toggle');
        if (toggle) {
            toggle.addEventListener('click', () => {
                setTheme(root.classList.contains('dark-mode') ? 'light' : 'dark');
            });
        }
    });
})();
