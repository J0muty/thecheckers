document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('report-form');
    if (!form) return;

    const fileInput = document.getElementById('report-file');
    const dropzone = document.getElementById('file-dropzone');
    const preview = document.getElementById('file-preview');
    const message = document.getElementById('report-message');
    const MAX_FILES = 5;
    const selectedFiles = [];
    const objectUrls = [];

    const sanitize = (str) => {
        const div = document.createElement('div');
        div.textContent = str;
        return div.textContent;
    };

    const formatBytes = (bytes) => {
        if (!bytes) return '0 Б';
        const units = ['Б', 'КБ', 'МБ'];
        let value = bytes;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }
        return `${value.toFixed(unit ? 1 : 0)} ${units[unit]}`;
    };

    const fileKey = (file) => `${file.name}:${file.size}:${file.lastModified}`;

    function syncFileInput() {
        try {
            const dt = new DataTransfer();
            selectedFiles.forEach(file => dt.items.add(file));
            fileInput.files = dt.files;
        } catch {
            fileInput.value = '';
        }
    }

    function clearObjectUrls() {
        objectUrls.splice(0).forEach(url => URL.revokeObjectURL(url));
    }

    function ensureViewer() {
        let backdrop = document.getElementById('img-viewer-backdrop');
        if (backdrop) return backdrop;

        backdrop = document.createElement('div');
        backdrop.id = 'img-viewer-backdrop';

        const img = document.createElement('img');
        img.id = 'img-viewer';
        img.alt = 'Просмотр вложения';

        const close = document.createElement('button');
        close.id = 'img-viewer-close';
        close.type = 'button';
        close.setAttribute('aria-label', 'Закрыть просмотр');
        close.innerHTML = '<i class="fa-solid fa-xmark"></i>';

        backdrop.append(img, close);
        document.body.appendChild(backdrop);

        function hide() {
            backdrop.style.display = 'none';
            document.body.style.overflow = '';
            img.src = '';
        }

        backdrop.addEventListener('click', (event) => {
            if (event.target === backdrop || event.target.closest('#img-viewer-close')) hide();
        });
        document.addEventListener('keydown', (event) => {
            if (backdrop.style.display === 'flex' && event.key === 'Escape') hide();
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
        clearObjectUrls();
        preview.innerHTML = '';

        selectedFiles.forEach((file, index) => {
            const url = URL.createObjectURL(file);
            objectUrls.push(url);

            const wrapper = document.createElement('div');
            wrapper.className = 'preview-image';

            const img = document.createElement('img');
            img.src = url;
            img.alt = file.name;
            img.addEventListener('click', () => showImage(url));

            const actions = document.createElement('div');
            actions.className = 'preview-actions';

            const zoom = document.createElement('button');
            zoom.type = 'button';
            zoom.className = 'preview-action zoom-image';
            zoom.setAttribute('aria-label', `Открыть ${file.name}`);
            zoom.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i>';
            zoom.addEventListener('click', () => showImage(url));

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'preview-action remove-image';
            remove.setAttribute('aria-label', `Удалить ${file.name}`);
            remove.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
            remove.addEventListener('click', () => {
                selectedFiles.splice(index, 1);
                syncFileInput();
                refreshPreviews();
            });

            const meta = document.createElement('div');
            meta.className = 'preview-meta';
            const name = document.createElement('span');
            name.className = 'preview-name';
            name.textContent = file.name;
            const size = document.createElement('span');
            size.className = 'preview-size';
            size.textContent = formatBytes(file.size);
            meta.append(name, size);

            actions.append(zoom, remove);
            wrapper.append(img, actions, meta);
            preview.appendChild(wrapper);
        });
    }

    function addFiles(fileList) {
        const incoming = Array.from(fileList || []);
        if (!incoming.length) return;

        const known = new Set(selectedFiles.map(fileKey));
        let added = 0;
        let skipped = 0;

        for (const file of incoming) {
            if (!file.type.startsWith('image/')) {
                skipped += 1;
                continue;
            }
            if (selectedFiles.length >= MAX_FILES) {
                skipped += 1;
                continue;
            }
            if (known.has(fileKey(file))) {
                skipped += 1;
                continue;
            }
            selectedFiles.push(file);
            known.add(fileKey(file));
            added += 1;
        }

        syncFileInput();
        refreshPreviews();

        if (added) {
            showNotification(`Добавлено ${added} файл${added > 1 ? 'а' : ''}`);
        }
        if (skipped) {
            showNotification(`Можно загрузить до ${MAX_FILES} изображений`, 'error');
        }
    }

    fileInput.addEventListener('change', () => addFiles(fileInput.files));

    if (dropzone) {
        dropzone.addEventListener('click', (event) => {
            if (event.target.closest('.file-btn')) return;
            fileInput.click();
        });

        dropzone.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            event.preventDefault();
            fileInput.click();
        });

        ['dragenter', 'dragover'].forEach(type => {
            dropzone.addEventListener(type, (event) => {
                event.preventDefault();
                dropzone.classList.add('is-dragover');
            });
        });

        ['dragleave', 'drop'].forEach(type => {
            dropzone.addEventListener(type, (event) => {
                event.preventDefault();
                dropzone.classList.remove('is-dragover');
            });
        });

        dropzone.addEventListener('drop', (event) => addFiles(event.dataTransfer?.files));
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const subject = document.getElementById('report-subject');
        const msg = sanitize(message.value.trim());
        const subj = sanitize(subject.value.trim());

        if (subj.length < 10) {
            showNotification('Тема слишком короткая', 'error');
            return;
        }
        if (msg.length < 50) {
            showNotification('Сообщение слишком короткое', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('username', form.username.value);
        formData.append('email', form.email.value);
        formData.append('subject', subj);
        formData.append('message', msg);
        selectedFiles.forEach(file => formData.append('files', file));

        try {
            const res = await fetch(form.action || '/report', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                showNotification('Сообщение отправлено');
                form.reset();
                selectedFiles.length = 0;
                syncFileInput();
                refreshPreviews();
            } else {
                showNotification('Ошибка отправки', 'error');
            }
        } catch {
            showNotification('Ошибка отправки', 'error');
        }
    });
});
