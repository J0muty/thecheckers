document.addEventListener('DOMContentLoaded', () => {
    const singleBtn = document.getElementById('singleBtn');
    const netBtn = document.getElementById('netBtn');
    const singleModal = document.getElementById('singleModal');
    const netModal = document.getElementById('netModal');
    const leaveModal = document.getElementById('leaveModal');
    const singleCloseBtn = document.getElementById('singleCloseBtn');
    const startSingleBtn = document.getElementById('startSingleBtn');
    const netSearchBtn = document.getElementById('netSearchBtn');
    const netLobbyBtn = document.getElementById('netLobbyBtn');
    const netBoardBtn = document.getElementById('netBoardBtn');
    const staticActions = document.querySelectorAll('[data-static-action]');
    const backendMessage = 'Эта страница открыта на GitHub Pages. Для игры, входа и лобби нужен запущенный FastAPI-сервер.';

    const openModal = modal => {
        if (modal) modal.classList.add('active');
    };

    const closeModal = modal => {
        if (modal) modal.classList.remove('active');
    };

    const showBackendNotice = event => {
        if (event) event.preventDefault();
        if (window.showNotification) {
            window.showNotification(backendMessage, 'error', 3500);
        }
    };

    if (singleBtn) singleBtn.addEventListener('click', () => openModal(singleModal));
    if (netBtn) netBtn.addEventListener('click', () => openModal(netModal));
    if (singleCloseBtn) singleCloseBtn.addEventListener('click', () => closeModal(singleModal));
    if (startSingleBtn) startSingleBtn.addEventListener('click', showBackendNotice);
    if (netSearchBtn) netSearchBtn.addEventListener('click', showBackendNotice);
    if (netLobbyBtn) netLobbyBtn.addEventListener('click', showBackendNotice);
    if (netBoardBtn) netBoardBtn.addEventListener('click', showBackendNotice);

    staticActions.forEach(action => {
        action.addEventListener('click', showBackendNotice);
    });

    [leaveModal, singleModal, netModal].filter(Boolean).forEach(overlay => {
        overlay.addEventListener('click', event => {
            if (event.target === overlay) closeModal(overlay);
        });
        overlay.querySelectorAll('[data-close-modal]').forEach(button => {
            button.addEventListener('click', () => closeModal(overlay));
        });
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            [leaveModal, singleModal, netModal].filter(Boolean).forEach(closeModal);
        }
    });
});
