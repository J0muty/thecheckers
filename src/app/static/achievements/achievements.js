const ACHIEVEMENTS = [
  { icon: 'fa-bolt',              title: 'Молниеносный старт',        desc: 'Сыграйте свою первую игру' },
  { icon: 'fa-flag-checkered',    title: 'Первая кровь',              desc: 'Одержите первую победу' },
  { icon: 'fa-gamepad',           title: 'Десятка опыта',             desc: 'Сыграйте 10 игр' },
  { icon: 'fa-list-ol',           title: 'Полсотни партий',           desc: 'Сыграйте 50 игр' },
  { icon: 'fa-calendar-check',    title: 'Сотня игр',                 desc: 'Сыграйте 100 игр' },
  { icon: 'fa-chess-board',       title: '200 сыграно',               desc: 'Сыграйте 200 игр' },
  { icon: 'fa-layer-group',       title: '500 игр позади',            desc: 'Сыграйте 500 игр' },
  { icon: 'fa-infinity',          title: 'Тысячник',                  desc: 'Сыграйте 1000 игр' },

  { icon: 'fa-crown',             title: 'Победитель 10',             desc: 'Одержите 10 побед' },
  { icon: 'fa-star',              title: '50 триумфов',               desc: 'Одержите 50 побед' },
  { icon: 'fa-trophy',            title: 'Сотня побед',               desc: 'Одержите 100 побед' },
  { icon: 'fa-medal',             title: '200 побед',                 desc: 'Одержите 200 побед' },
  { icon: 'fa-gem',               title: '500 побед – полтысячи!',    desc: 'Одержите 500 побед' },
  { icon: 'fa-chess-king',        title: 'Килопобеда',                desc: 'Одержите 1000 побед' },

  { icon: 'fa-fire',              title: 'Серия 3',                   desc: 'Победите 3 раза подряд' },
  { icon: 'fa-fire-flame-curved', title: 'Серия 5',                   desc: 'Победите 5 раз подряд' },
  { icon: 'fa-meteor',            title: 'Серия 10',                  desc: 'Победите 10 раз подряд' },
  { icon: 'fa-dragon',            title: 'Серия 20',                  desc: 'Победите 20 раз подряд' },
  { icon: 'fa-shield-halved',     title: 'Непобеждённый',             desc: '20 игр подряд без поражений' },

  { icon: 'fa-check-double',      title: 'Идеальная партия',          desc: 'Выиграйте, не потеряв ни одной шашки' },
  { icon: 'fa-xmarks-lines',      title: 'Комбо ×3',                  desc: 'Захватите 3 шашки одним ходом' },
  { icon: 'fa-burst',             title: 'Комбо ×4+',                 desc: 'Захватите 4 или больше шашек одним ходом' },
  { icon: 'fa-heart-crack',       title: 'Один в поле воин',          desc: 'Выиграйте, имея одну шашку против 3+ у соперника' },
  { icon: 'fa-chess-queen',       title: 'Пять корон',                desc: 'Получите 5 дамок в одной игре' },
  { icon: 'fa-skull-crossbones',  title: 'Охотник на королев',        desc: 'Снесите 3 дамки соперника в одной игре' },
  { icon: 'fa-scissors',          title: 'Жертва ради победы',        desc: 'Пожертвуйте дамкой и выиграйте' },
  { icon: 'fa-scale-balanced',    title: 'Ничья на волоске',          desc: 'Сведите партию вничью, имея одну шашку' },

  { icon: 'fa-arrow-trend-up',    title: 'Бронза I',                  desc: 'Достигните рейтинга 300 (Бронза I)' },
  { icon: 'fa-arrow-trend-up',    title: 'Бронза II',                 desc: 'Достигните рейтинга 600 (Бронза II)' },
  { icon: 'fa-arrow-trend-up',    title: 'Бронза III',                desc: 'Достигните рейтинга 900 (Бронза III)' },
  { icon: 'fa-arrow-trend-up',    title: 'Серебро I',                 desc: 'Достигните рейтинга 1500 (Серебро I)' },
  { icon: 'fa-arrow-trend-up',    title: 'Серебро II',                desc: 'Достигните рейтинга 1800 (Серебро II)' },
  { icon: 'fa-arrow-trend-up',    title: 'Серебро III',               desc: 'Достигните рейтинга 2100 (Серебро III)' },
  { icon: 'fa-arrow-trend-up',    title: 'Золото I',                  desc: 'Достигните рейтинга 2500 (Золото I)' },
  { icon: 'fa-arrow-trend-up',    title: 'Золото II',                 desc: 'Достигните рейтинга 2800 (Золото II)' },
  { icon: 'fa-arrow-trend-up',    title: 'Золото III',                desc: 'Достигните рейтинга 3100 (Золото III)' },
  { icon: 'fa-arrow-trend-up',    title: 'Платина',                   desc: 'Достигните рейтинга 3600 (Платина)' },
  { icon: 'fa-arrow-trend-up',    title: 'Мастер',                    desc: 'Достигните рейтинга 4000 (Мастер)' },
  { icon: 'fa-arrow-trend-up',    title: 'Гран Мастер',               desc: 'Достигните рейтинга 5000 (Гран Мастер)' },
  { icon: 'fa-arrow-trend-up',    title: 'Чемпион',                   desc: 'Достигните рейтинга 7000 (Чемпион)' },
  { icon: 'fa-chart-line',        title: 'Спринт +100',               desc: 'Поднимите рейтинг на 100 за день' },
  { icon: 'fa-rocket',            title: 'Гиперрост +500',            desc: 'Поднимите рейтинг на 500 за неделю' },

  { icon: 'fa-hourglass-start',   title: 'Скоростной матч',           desc: 'Выиграйте партию менее чем за 2 минуты' },
  { icon: 'fa-stopwatch',         title: 'Время вышло',               desc: 'Победите соперника по таймеру' },
  { icon: 'fa-hourglass-end',     title: 'Марафон 60+',               desc: 'Партия длиннее 60 ходов' },

  { icon: 'fa-calendar-day',      title: 'Каждый день',               desc: 'Играйте 7 дней подряд' },
  { icon: 'fa-calendar-days',     title: 'Месяц в строю',             desc: 'Играйте 30 дней подряд' },
  { icon: 'fa-hand-holding-heart',title: 'Честная игра',              desc: '100 матчей без досрочных выходов' },
  { icon: 'fa-recycle',           title: 'Рематч!',                   desc: 'Сыграйте реванш сразу после игры' },

  { icon: 'fa-sitemap',           title: 'Турнирный дебют',           desc: 'Сыграйте в своём первом турнире' },
  { icon: 'fa-trophy',            title: 'Чемпион турнира',           desc: 'Займите 1-е место в турнире' },

  { icon: 'fa-robot',             title: 'Лёгкий? Легко!',            desc: 'Победите бота на лёгком уровне' },
  { icon: 'fa-robot',             title: 'Лёгкий ×10',                desc: 'Победите бота на лёгком уровне 10 раз' },
  { icon: 'fa-robot',             title: 'Лёгкий ×50',                desc: 'Победите бота на лёгком уровне 50 раз' },
  { icon: 'fa-robot',             title: 'Средний класс',             desc: 'Победите бота на среднем уровне' },
  { icon: 'fa-robot',             title: 'Средний ×10',               desc: 'Победите бота на среднем уровне 10 раз' },
  { icon: 'fa-robot',             title: 'Средний ×50',               desc: 'Победите бота на среднем уровне 50 раз' },
  { icon: 'fa-robot',             title: 'Железо повержено',          desc: 'Победите бота на сложном уровне' },
  { icon: 'fa-robot',             title: 'Хардкор ×10',               desc: 'Победите бота на сложном уровне 10 раз' },
  { icon: 'fa-robot',             title: 'Хардкор ×50',               desc: 'Победите бота на сложном уровне 50 раз' },

  { icon: 'fa-user-plus',         title: 'Новый товарищ',             desc: 'Добавьте первого друга' },
  { icon: 'fa-user-group',        title: 'Своя компания',             desc: 'Иметь 5 друзей' },
  { icon: 'fa-people-group',      title: 'Малая тусовка',             desc: 'Иметь 10 друзей' },
  { icon: 'fa-people-roof',       title: 'Клан образовался',          desc: 'Иметь 25 друзей' },
  { icon: 'fa-people-line',       title: 'Своя соцсеть',              desc: 'Иметь 50 друзей' },

  { icon: 'fa-comments',          title: 'Активист чата',             desc: 'Напишите 10 сообщений в чате' },
  { icon: 'fa-bug',               title: 'Истребитель багов',         desc: 'Сообщите о баге разработчикам' },
  { icon: 'fa-face-grin-squint',  title: 'Проиграл боту? Серьёзно?',  desc: 'Проиграйте боту на лёгком уровне' }
];

function setColumns(columns) {
  const list = document.querySelector('.achievements-list');
  const wrapper = document.querySelector('.achievements-scroll');
  list.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
  wrapper.style.maxWidth = columns === 1 ? '100%' : '1200px';
  document.querySelectorAll('.layout-selector i').forEach(icon => {
    icon.classList.toggle('active', Number(icon.dataset.columns) === columns);
  });
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
  block.style.height = (window.innerHeight - rect.top - 30) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  const list = document.querySelector('.achievements-list');
  const selector = document.querySelector('.layout-selector');

  selector.querySelectorAll('i').forEach(icon => {
    icon.addEventListener('click', () => setColumns(Number(icon.dataset.columns)));
  });

  setColumns(3);

  ACHIEVEMENTS.forEach(a => {
    const card = createCard(a, false);
    list.appendChild(card);
  });

  fixScrollHeight();
  window.addEventListener('resize', fixScrollHeight);
});
