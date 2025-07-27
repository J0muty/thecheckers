function showNotification(message, type = 'success', duration = 2500) {
    if (typeof type === 'number') {
        duration = type;
        type = 'success';
    }
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.style.setProperty('--toast-duration', duration + 'ms');
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.remove();
        if (!container.children.length) container.remove();
    }, duration + 300);
}
window.showNotification = showNotification;