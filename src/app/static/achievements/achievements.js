const ACHIEVEMENTS = [
    { icon: 'fa-bolt', title: 'Молниеносный старт', desc: 'Сыграйте свою первую игру' },
    { icon: 'fa-crown', title: 'Победитель', desc: 'Одержите 10 побед' },
    { icon: 'fa-heart', title: 'Верный друг', desc: 'Добавьте первого друга' },
    { icon: 'fa-star', title: 'Звезда', desc: 'Достигните рейтинга 1000' },
    { icon: 'fa-gem', title: 'Коллекционер', desc: 'Соберите 5 редких предметов' },
    { icon: 'fa-trophy', title: 'Чемпион', desc: 'Завоюйте первое место в турнире' },
    { icon: 'fa-shield', title: 'Защитник', desc: 'Выиграйте матч, не потеряв ни одной жизни' },
    { icon: 'fa-magic', title: 'Магистр магии', desc: 'Используйте 100 заклинаний' },
    { icon: 'fa-dragon', title: 'Драконий охотник', desc: 'Победите дракона' },
    { icon: 'fa-rocket', title: 'Космический путешественник', desc: 'Исследуйте 10 звёздных систем' },
    { icon: 'fa-tree', title: 'Зелёный палец', desc: 'Посадите 50 деревьев' },
    { icon: 'fa-fire', title: 'Огненный воин', desc: 'Победите 500 врагов огнем' },
    { icon: 'fa-water', title: 'Мореплаватель', desc: 'Проплывите 1000 морских миль' },
    { icon: 'fa-mountain', title: 'Покоритель гор', desc: 'Поднимитесь на вершину Эвереста' },
    { icon: 'fa-bug', title: 'Истребитель багов', desc: 'Сообщите о 10 багах' },
    { icon: 'fa-code', title: 'Программист', desc: 'Напишите 1000 строк кода' },
    { icon: 'fa-music', title: 'Меломан', desc: 'Послушайте 100 треков' },
    { icon: 'fa-camera', title: 'Фотограф', desc: 'Сделайте 50 скриншотов' },
    { icon: 'fa-leaf', title: 'Эколог', desc: 'Сдайте 10 кг макулатуры на переработку' },
    { icon: 'fa-sun', title: 'Утренний жаворонок', desc: 'Играйте до 6 утра' }
];

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

function setColumns(columns) {
    const list = document.querySelector('.achievements-list');
    const wrapper = document.querySelector('.achievements-scroll');
    list.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    wrapper.style.maxWidth = columns === 1 ? '100%' : '1200px';
    document.querySelectorAll('.layout-selector i').forEach(icon => {
        icon.classList.toggle('active', Number(icon.dataset.columns) === columns);
    });
    localStorage.setItem('achievements_columns', String(columns));
}

function createCard(data, unlocked) {
    const card = document.createElement('div');
    card.className = unlocked ? 'achievement-card unlocked' : 'achievement-card';
    const icon = document.createElement('i');
    icon.className = `fa-solid ${data.icon}`;
    const info = document.createElement('div');
    info.className = 'achievement-info';
    const title = document.createElement('div');
    title.className = 'achievement-title';
    title.textContent = data.title;
    const desc = document.createElement('div');
    desc.className = 'achievement-desc';
    desc.textContent = data.desc;
    info.appendChild(title);
    info.appendChild(desc);
    card.appendChild(icon);
    card.appendChild(info);
    return card;
}

function fixScrollHeight() {
    const block = document.querySelector('.achievements-scroll');
    const rect = block.getBoundingClientRect();
    const h = window.innerHeight - rect.top - 30;
    block.style.height = h + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
    const list = document.querySelector('.achievements-list');
    const selector = document.querySelector('.layout-selector');

    selector.querySelectorAll('i').forEach(icon => {
        icon.addEventListener('click', () => setColumns(Number(icon.dataset.columns)));
    });

    const savedCols = Number(localStorage.getItem('achievements_columns')) || 3;
    setColumns(savedCols);

    const toDisplay = shuffleArray([...ACHIEVEMENTS]);
    toDisplay.forEach((achievement, idx) => {
        const unlocked = Math.random() > 0.5;
        const card = createCard(achievement, unlocked);
        list.appendChild(card);
        if (unlocked) {
            setTimeout(() => {
                card.classList.add('unlocked');
            }, 300 + idx * 100);
        }
    });

    fixScrollHeight();
    window.addEventListener('resize', fixScrollHeight);
});
