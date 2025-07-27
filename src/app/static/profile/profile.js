async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) return;
        const data = await res.json();
        totalGames = data.total_games;
        document.getElementById('total-games').textContent = data.total_games;
        document.getElementById('wins').textContent = data.wins;
        document.getElementById('draws').textContent = data.draws;
        document.getElementById('losses').textContent = data.losses;
        document.getElementById('elo').textContent = data.elo;
        document.getElementById('rank').textContent = data.rank;
        const icon = document.querySelector('.rank-icon');
        if (icon) {
            icon.src = `/static/images/profile/ranks/${encodeURIComponent(data.rank)}.png`;
            icon.alt = data.rank;
        }
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

let offset = 0;
const limit = 10;
let allLoaded = false;
let expanded = false;
let totalGames = 0;

function appendHistoryRows(items) {
    const tbody = document.getElementById('history-body');
    if (!tbody) return;
    items.forEach(item => {
        const tr = document.createElement('tr');
        const date = new Date(item.timestamp);
        const elo = item.elo_change;
        const eloText = elo === null || elo === undefined ? '-' : (elo > 0 ? `+${elo}` : `${elo}`);
        tr.innerHTML = `
            <td>${date.toLocaleString('ru-RU')}</td>
            <td>${item.mode}</td>
            <td class="result-cell ${item.result[0]}">${item.result[0].toUpperCase()}</td>
            <td>${eloText}</td>`;
        tr.dataset.gameId = item.id;
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', () => {
            if (item.id) {
                window.location.href = `/replay/${item.id}`;
            }
        });
        tbody.appendChild(tr);
    });
}

async function loadHistory() {
    try {
        const res = await fetch(`/api/history?offset=${offset}&limit=${limit}`);
        if (!res.ok) return;
        const data = await res.json();
        appendHistoryRows(data.history);
        offset += data.history.length;
        if (offset >= totalGames) allLoaded = true;
        if (offset > limit) expanded = true;
        updateButtons();
    } catch (e) {
        console.error('Failed to load history:', e);
    }
}

function hideHistory() {
    const tbody = document.getElementById('history-body');
    if (!tbody) return;

    Array.from(tbody.children).slice(limit).forEach(r => r.remove());

    offset = limit;
    allLoaded = offset >= totalGames;
    expanded  = false;

    updateButtons();
}

function updateButtons() {
    const loadBtn = document.getElementById('load-more-btn');
    const hideBtn = document.getElementById('hide-btn');

    if (loadBtn) {
        loadBtn.style.display = !allLoaded ? 'inline-block' : 'none';
    }

    if (hideBtn) {
        hideBtn.style.display = expanded ? 'inline-block' : 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('total-games')) {
        loadStats().then(loadHistory);
        const loadBtn = document.getElementById('load-more-btn');
        const hideBtn = document.getElementById('hide-btn');
        if (loadBtn) loadBtn.addEventListener('click', loadHistory);
        if (hideBtn) hideBtn.addEventListener('click', hideHistory);
    }
});
