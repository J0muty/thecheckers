const TOAST_TYPES = new Set(['success', 'error', 'warning', 'info']);

const TOAST_ICONS = {
    success: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    error: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    warning: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2.5 20.5h19L12 3z"/><path d="M12 9v5M12 17h.01"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17v-6M12 7h.01"/><circle cx="12" cy="12" r="9"/></svg>',
};

function getToastContainer() {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        container.setAttribute('aria-live', 'polite');
        container.setAttribute('aria-relevant', 'additions removals');
        document.body.appendChild(container);
    }
    return container;
}

function showNotification(message, type = 'success', duration = 3200) {
    if (typeof type === 'number') {
        duration = type;
        type = 'success';
    }

    const toastType = TOAST_TYPES.has(type) ? type : 'info';
    const container = getToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${toastType}`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);
    toast.setAttribute('role', toastType === 'error' ? 'alert' : 'status');

    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.innerHTML = TOAST_ICONS[toastType];

    const body = document.createElement('span');
    body.className = 'toast-message';
    body.textContent = String(message ?? '');

    const close = document.createElement('button');
    close.className = 'toast-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Закрыть уведомление');
    close.textContent = '×';

    const progress = document.createElement('span');
    progress.className = 'toast-progress';
    progress.setAttribute('aria-hidden', 'true');

    toast.append(icon, body, close, progress);
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));

    const autoCloseId = setTimeout(() => closeToast(toast), duration);
    toast.dataset.autoCloseId = String(autoCloseId);

    close.addEventListener('click', () => {
        clearTimeout(autoCloseId);
        closeToast(toast);
    });

    addSwipeToClose(toast, autoCloseId);
}

function closeToast(toast) {
    if (!toast || toast.classList.contains('hide')) return;
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => {
        const container = toast.parentElement;
        toast.remove();
        if (container && !container.children.length) container.remove();
    }, 260);
}

function addSwipeToClose(toast, autoCloseId) {
    let startX = 0;
    let currentX = 0;
    let dragging = false;
    const threshold = 76;

    const resetDrag = () => {
        currentX = 0;
        toast.style.transform = '';
        toast.style.opacity = '';
        toast.style.transition = '';
    };

    const down = event => {
        if (event.button !== undefined && event.button !== 0) return;
        if (event.target.closest('.toast-close')) return;
        dragging = true;
        startX = event.clientX;
        currentX = 0;
        toast.style.transition = 'none';
        clearTimeout(autoCloseId);
        if (toast.setPointerCapture) toast.setPointerCapture(event.pointerId);
    };

    const move = event => {
        if (!dragging) return;
        currentX = Math.max(0, event.clientX - startX);
        toast.style.transform = `translateX(${currentX}px)`;
        toast.style.opacity = String(1 - Math.min(currentX / 240, 0.82));
    };

    const up = () => {
        if (!dragging) return;
        dragging = false;
        if (currentX > threshold) {
            closeToast(toast);
            return;
        }
        resetDrag();
    };

    toast.addEventListener('pointerdown', down);
    toast.addEventListener('pointermove', move);
    toast.addEventListener('pointerup', up);
    toast.addEventListener('pointercancel', up);
}

window.showNotification = showNotification;
