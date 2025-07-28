document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('report-form');
    if (!form) return;
    form.addEventListener('submit', e => {
        e.preventDefault();
        const subject = document.getElementById('report-subject');
        const message = document.getElementById('report-message');
        if (subject.value.trim().length < 10) {
            showNotification('Тема слишком короткая', 'error');
            return;
        }
        if (message.value.trim().length < 50) {
            showNotification('Сообщение слишком короткое', 'error');
            return;
        }
        showNotification('Спасибо, сообщение отправлено');
        form.reset();
    });
});