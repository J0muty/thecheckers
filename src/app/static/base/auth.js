(function () {
    function isFilled(input) {
        return input.value.length > 0;
    }

    function syncInput(input) {
        const group = input.closest('.input-group');
        if (!group) return;
        group.classList.toggle('is-filled', isFilled(input));
    }

    function syncAll() {
        document.querySelectorAll('body.auth-page .input-group input').forEach(syncInput);
    }

    function scheduleSync() {
        syncAll();
        requestAnimationFrame(syncAll);
        setTimeout(syncAll, 120);
        setTimeout(syncAll, 600);
        setTimeout(syncAll, 1400);
    }

    function init() {
        document.querySelectorAll('body.auth-page .input-group input').forEach(input => {
            ['input', 'change', 'focus', 'blur'].forEach(eventName => {
                input.addEventListener(eventName, () => syncInput(input));
            });
            input.addEventListener('animationstart', () => syncInput(input));
        });
        scheduleSync();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.addEventListener('pageshow', scheduleSync);
})();
