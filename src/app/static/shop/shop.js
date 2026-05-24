const skinGrid = document.getElementById('skinGrid');
const storeStatus = document.getElementById('storeStatus');
const shopShell = document.querySelector('[data-shop-mode]');
const shopMode = shopShell?.dataset.shopMode || 'store';
let storeState = null;

function coinMarkup(kind) {
    if (kind === 'rub') {
        return '<span class="rub-mark" aria-hidden="true">₽</span>';
    }
    return `
        <span class="tc-coin-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" role="img" focusable="false">
                <circle cx="16" cy="16" r="14"></circle>
                <path d="M16 5.5 25 13.4 16 26.5 7 13.4Z"></path>
                <path d="M16 5.5v21M7 13.4h18M11.2 13.4 16 26.5l4.8-13.1"></path>
            </svg>
        </span>
    `;
}

function priceMarkup(skin) {
    if (skin.currency === 'soft') {
        return `${coinMarkup('soft')}<span>${Number(skin.soft_price || 0).toLocaleString('ru-RU')}</span>`;
    }
    if (skin.currency === 'rub') {
        return `${coinMarkup('rub')}<span>${Number(skin.rub_price || 0).toLocaleString('ru-RU')}</span>`;
    }
    return '<span>Бесплатно</span>';
}

function updateWallet(wallet) {
    document.querySelectorAll('[data-soft-balance]').forEach(el => {
        el.textContent = Number(wallet.soft_balance || 0).toLocaleString('ru-RU');
    });
    document.querySelectorAll('[data-rub-balance]').forEach(el => {
        el.textContent = Number(wallet.rub_balance || 0).toLocaleString('ru-RU');
    });
    document.querySelectorAll('[data-wallet-strip]').forEach(el => {
        el.hidden = false;
    });
}

function renderStoreActions(skin) {
    if (skin.owned) {
        return '<div class="skin-price skin-price-owned"><span>В инвентаре</span></div>';
    }
    return `
        <div class="skin-price">${priceMarkup(skin)}</div>
        <button class="skin-action-btn" type="button" data-action="buy">
            Купить
        </button>
    `;
}

function renderInventoryActions(skin) {
    return `
        <button class="skin-action-btn ${skin.selected ? 'selected' : ''}" type="button" data-action="select" ${skin.selected ? 'disabled' : ''}>
            ${skin.selected ? 'Выбран' : 'Выбрать'}
        </button>
    `;
}

function renderSkinCard(skin) {
    const card = document.createElement('article');
    card.className = `skin-card ${shopMode === 'inventory' ? 'inventory-card' : ''} ${skin.tier === 'premium' ? 'premium' : ''} ${skin.selected ? 'selected' : ''}`;
    card.dataset.skinId = skin.id;

    const flip = document.createElement('button');
    flip.className = 'skin-flip-btn';
    flip.type = 'button';
    flip.dataset.flipSkin = skin.id;
    flip.setAttribute('aria-label', 'Показать черные шашки');
    flip.setAttribute('aria-pressed', 'false');
    flip.innerHTML = '<i class="fa-solid fa-rotate" aria-hidden="true"></i>';

    const preview = document.createElement('div');
    preview.className = 'skin-preview';
    const stage = document.createElement('div');
    stage.className = 'skin-flip-stage';
    const front = document.createElement('div');
    front.className = 'skin-piece-pair skin-piece-face skin-piece-front';
    const back = document.createElement('div');
    back.className = 'skin-piece-pair skin-piece-face skin-piece-back';
    const whiteMan = document.createElement('img');
    const whiteKing = document.createElement('img');
    const blackMan = document.createElement('img');
    const blackKing = document.createElement('img');
    [whiteMan, whiteKing, blackMan, blackKing].forEach(img => {
        img.className = 'skin-piece-img';
        img.alt = '';
        img.draggable = false;
    });
    front.append(whiteMan, whiteKing);
    back.append(blackMan, blackKing);
    stage.append(front, back);
    preview.appendChild(stage);

    const copy = document.createElement('div');
    copy.className = 'skin-copy';
    copy.innerHTML = `
        <div class="skin-topline">
            <h2 class="skin-name">${skin.name}</h2>
        </div>
    `;

    const actions = document.createElement('div');
    actions.className = 'skin-actions';
    actions.innerHTML = shopMode === 'inventory' ? renderInventoryActions(skin) : renderStoreActions(skin);

    card.append(flip, preview, copy, actions);
    requestAnimationFrame(() => {
        window.Checker3D?.renderPreview(whiteMan, {
            skinId: skin.id,
            color: 'white',
            king: false,
            size: 360,
        });
        window.Checker3D?.renderPreview(whiteKing, {
            skinId: skin.id,
            color: 'white',
            king: true,
            size: 360,
        });
        window.Checker3D?.renderPreview(blackMan, {
            skinId: skin.id,
            color: 'black',
            king: false,
            size: 360,
        });
        window.Checker3D?.renderPreview(blackKing, {
            skinId: skin.id,
            color: 'black',
            king: true,
            size: 360,
        });
    });
    return card;
}

function renderStore() {
    if (!storeState) return;
    updateWallet(storeState.wallet);
    const skins = shopMode === 'inventory'
        ? storeState.skins.filter(skin => skin.owned)
        : storeState.skins;

    if (!skins.length) {
        skinGrid.replaceChildren();
        storeStatus.textContent = 'В инвентаре пока пусто';
        return;
    }

    skinGrid.replaceChildren(...skins.map(renderSkinCard));
    storeStatus.textContent = '';
}

async function loadStore() {
    storeStatus.textContent = '';
    const response = await fetch('/api/store', {cache: 'no-store'});
    if (!response.ok) {
        storeStatus.textContent = 'Магазин недоступен';
        return;
    }
    storeState = await response.json();
    renderStore();
}

function notify(message, type = 'success') {
    if (typeof window.showNotification === 'function') {
        showNotification(message, type);
        return;
    }
    storeStatus.textContent = message;
}

function errorText(error) {
    const messages = {
        not_enough_soft: 'Недостаточно внутренней валюты',
        not_enough_rub: 'Недостаточно рублей на балансе',
        skin_not_owned: 'Скин не найден в инвентаре',
        unknown_skin: 'Скин не найден',
    };
    return messages[error] || 'Не удалось выполнить действие';
}

async function postSkinAction(url, skinId) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({skin_id: skinId}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.error || 'request_failed');
    }
    return payload;
}

skinGrid?.addEventListener('click', async event => {
    const flipButton = event.target.closest('[data-flip-skin]');
    if (flipButton) {
        const card = flipButton.closest('.skin-card');
        const flipped = !card.classList.contains('is-flipped');
        card.classList.toggle('is-flipped', flipped);
        flipButton.setAttribute('aria-pressed', String(flipped));
        flipButton.setAttribute('aria-label', flipped ? 'Показать белые шашки' : 'Показать черные шашки');
        return;
    }

    const button = event.target.closest('[data-action]');
    if (!button) return;
    const card = button.closest('.skin-card');
    const skinId = card?.dataset.skinId;
    if (!skinId) return;
    button.disabled = true;
    try {
        if (button.dataset.action === 'buy') {
            await postSkinAction('/api/store/buy', skinId);
            notify('Скин добавлен в инвентарь');
        } else if (button.dataset.action === 'select') {
            await postSkinAction('/api/store/select', skinId);
            notify('Скин выбран');
        }
        await loadStore();
    } catch (error) {
        button.disabled = false;
        notify(errorText(error.message), 'error');
    }
});

document.addEventListener('DOMContentLoaded', loadStore);
