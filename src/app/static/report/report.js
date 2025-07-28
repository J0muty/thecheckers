document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('report-form');
    if (!form) return;

    document.body.classList.add('no-scroll');

    const fileInput = document.getElementById('report-file');
    const preview = document.getElementById('file-preview');
    const message = document.getElementById('report-message');
    const MAX_FILES = 5;
    const MAX_TEXTAREA_HEIGHT = 250;

    const sanitize = (str) => {
        const div = document.createElement('div');
        div.textContent = str;
        return div.textContent;
    };

    function clampTextareaHeight(el) {
        el.style.height = 'auto';
        const targetHeight = Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT);
        el.style.height = targetHeight + 'px';
        el.style.overflowY = targetHeight >= MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden';
    }
    if (message) {
        clampTextareaHeight(message);
        message.addEventListener('input', () => clampTextareaHeight(message));
    }

    function ensureViewer() {
        let backdrop = document.getElementById('img-viewer-backdrop');
        if (backdrop) return backdrop;
        backdrop = document.createElement('div');
        backdrop.id = 'img-viewer-backdrop';
        const img = document.createElement('img');
        img.id = 'img-viewer';
        const close = document.createElement('button');
        close.id = 'img-viewer-close';
        close.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        backdrop.appendChild(img);
        backdrop.appendChild(close);
        document.body.appendChild(backdrop);

        function hide() {
            backdrop.style.display = 'none';
            document.body.style.overflow = '';
            img.src = '';
        }

        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop || e.target.closest('#img-viewer-close')) hide();
        });
        document.addEventListener('keydown', (e) => {
            if (backdrop.style.display === 'flex' && e.key === 'Escape') hide();
        });

        return backdrop;
    }

    function showImage(src) {
        const backdrop = ensureViewer();
        const img = document.getElementById('img-viewer');
        img.src = src;
        backdrop.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }

    function refreshPreviews() {
        preview.innerHTML = '';
        const files = Array.from(fileInput.files);
        files.forEach((file, index) => {
            if (!file.type.startsWith('image/')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'preview-image';

            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.alt = file.name;
            img.addEventListener('click', () => showImage(img.src));

            const zoom = document.createElement('button');
            zoom.type = 'button';
            zoom.className = 'zoom-image';
            zoom.innerHTML = '<i class="fa-solid fa-magnifying-glass-plus"></i>';
            zoom.addEventListener('click', () => showImage(img.src));

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'remove-image';
            remove.innerHTML = '<i class="fa-solid fa-trash"></i>';
            remove.addEventListener('click', () => {
                const dt = new DataTransfer();
                files.forEach((f, i) => {
                    if (i !== index) dt.items.add(f);
                });
                fileInput.files = dt.files;
                refreshPreviews();
            });

            wrapper.appendChild(img);
            wrapper.appendChild(zoom);
            wrapper.appendChild(remove);
            preview.appendChild(wrapper);
        });
    }

    fileInput.addEventListener('change', () => {
        let files = Array.from(fileInput.files);

        if (files.length > MAX_FILES) {
            showNotification(`Можно загрузить максимум ${MAX_FILES} изображений`, 'error');
            files = files.slice(0, MAX_FILES);
            const dt = new DataTransfer();
            files.forEach(f => dt.items.add(f));
            fileInput.files = dt.files;
        }

        refreshPreviews();
    });

    form.addEventListener('submit', e => {
        const subject = document.getElementById('report-subject');
        const msg = sanitize(message.value.trim());
        const subj = sanitize(subject.value.trim());

        if (subj.length < 10) {
            e.preventDefault();
            showNotification('Тема слишком короткая', 'error');
            return;
        }
        if (msg.length < 50) {
            e.preventDefault();
            showNotification('Сообщение слишком короткое', 'error');
            return;
        }
    });
});
