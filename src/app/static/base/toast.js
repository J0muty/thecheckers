function showNotification(message, type = 'success', duration = 2500) {
    if (typeof type === 'number') { duration = type; type = 'success'; }

    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.style.setProperty('--toast-duration', duration + 'ms');
    toast.innerHTML = `
        <button class="toast-close" aria-label="Закрыть">&times;</button>
        <span class="toast-message">${message}</span>
    `;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));

    const autoCloseId = setTimeout(() => closeToast(toast), duration);

    toast.querySelector('.toast-close').addEventListener('click', () => {
        clearTimeout(autoCloseId);
        closeToast(toast);
    });

    addSwipeToClose(toast, autoCloseId);
}

function closeToast(toast) {
    if (toast.classList.contains('hide')) return;
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => {
        const container = toast.parentElement;
        toast.remove();
        if (container && !container.children.length) container.remove();
    }, 300);
}

function addSwipeToClose(toast, autoCloseId) {
    let startX = 0, currentX = 0, dragging = false;
    const threshold = 80;

    const down = (e) => {
        dragging = true;
        startX = e.clientX || e.touches?.[0].clientX;
        toast.style.transition = 'none';
        clearTimeout(autoCloseId);
    };
    const move = (e) => {
        if (!dragging) return;
        currentX = (e.clientX || e.touches?.[0].clientX) - startX;
        if (currentX > 0) {
            toast.style.transform = `translateX(${currentX}px)`;
            toast.style.opacity = 1 - Math.min(currentX / 200, 0.9);
        }
    };
    const up = () => {
        if (!dragging) return;
        dragging = false;
        toast.style.transition = '';
        if (currentX > threshold) {
            closeToast(toast);
        } else {
            toast.style.transform = '';
            toast.style.opacity = '';
        }
    };

    toast.addEventListener('pointerdown', down);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
}

window.showNotification = showNotification;
