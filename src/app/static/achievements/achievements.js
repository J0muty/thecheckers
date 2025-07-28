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

async function loadAchievements() {
  const resp = await fetch('/api/achievements');
  if (!resp.ok) return { achievements: [], unlocked: [] };
  return await resp.json();
}

document.addEventListener('DOMContentLoaded', async () => {
  const list = document.querySelector('.achievements-list');
  const selector = document.querySelector('.layout-selector');

  selector.querySelectorAll('i').forEach(icon => {
    icon.addEventListener('click', () => setColumns(Number(icon.dataset.columns)));
  });

  setColumns(3);

  const data = await loadAchievements();
  const unlocked = new Set(data.unlocked);
  data.achievements.forEach(a => {
    const card = createCard(a, unlocked.has(a.code));
    list.appendChild(card);
  });

  fixScrollHeight();
  window.addEventListener('resize', fixScrollHeight);
});
