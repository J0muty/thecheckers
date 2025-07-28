const boardElement = document.getElementById('board');
const historyList = document.getElementById('historyList');
const letters = ['', 'A','B','C','D','E','F','G','H',''];
const numbers = ['', '8','7','6','5','4','3','2','1',''];
const myColor = typeof playerColor !== 'undefined' && playerColor ? playerColor : null;

let boardState = [];
let viewedMoveIndex = 0;

function toBoardCoords(r, c) {
    return myColor === 'black' ? [7 - r, 7 - c] : [r, c];
}

function renderBoard() {
    boardElement.innerHTML = '';
    for (let row = 0; row < 10; row++) {
        for (let col = 0; col < 10; col++) {
            const cell = document.createElement('div');
            cell.classList.add('square');
            if (row === 0 || row === 9) {
                cell.classList.add('label', row === 0 ? 'label-top' : 'label-bottom');
                cell.textContent = letters[col];
            } else if (col === 0 || col === 9) {
                cell.classList.add('label', col === 0 ? 'label-left' : 'label-right');
                cell.textContent = numbers[row];
            } else {
                const r = row - 1;
                const c = col - 1;
                const [br, bc] = toBoardCoords(r, c);
                cell.classList.add((r + c) % 2 ? 'dark' : 'light');
                const piece = boardState[br][bc];
                if (piece) {
                    const p = document.createElement('div');
                    p.classList.add('piece', piece.toLowerCase() === 'w' ? 'white' : 'black');
                    if (piece === piece.toUpperCase()) {
                        p.classList.add('king');
                    }
                    cell.appendChild(p);
                }
            }
            boardElement.appendChild(cell);
        }
    }
}

function updateHistory(history) {
    historyList.innerHTML = '';
    history.forEach((m, i) => {
        const li = document.createElement('li');
        li.textContent = displayMove(m);
        li.dataset.index = i + 1;
        li.addEventListener('click', onHistoryClick);
        if (myColor && ((myColor === 'white' && i % 2 === 0) || (myColor === 'black' && i % 2 === 1))) {
            li.classList.add('my-move');
        }
        if (viewedMoveIndex === i + 1) {
            li.classList.add('active-history');
        }
        historyList.appendChild(li);
    });
}

function highlightHistoryItem(index) {
    document.querySelectorAll('.history-list li').forEach(li => {
        li.classList.toggle('active-history', parseInt(li.dataset.index) === index);
    });
}

function displayMove(move) {
    if (myColor !== 'black') return move;
    const convert = (pos) => {
        const col = pos[0];
        const row = parseInt(pos.slice(1));
        const r = 8 - row;
        const c = col.charCodeAt(0) - 65;
        const r2 = 7 - r;
        const c2 = 7 - c;
        return String.fromCharCode(65 + c2) + (8 - r2);
    };
    const [start, end] = move.split('->');
    return `${convert(start)}->${convert(end)}`;
}

async function fetchGame() {
    const data = await (await fetch(`/api/replay/${boardId}`)).json();
    viewedMoveIndex = data.history.length ? 1 : 0;
    const snap = await (await fetch(`/api/replay/${boardId}/${viewedMoveIndex}`)).json();
    boardState = snap;
    updateHistory(data.history);
    renderBoard();
}

async function onHistoryClick(e) {
    const idx = parseInt(e.currentTarget.dataset.index);
    const data = await (await fetch(`/api/replay/${boardId}/${idx}`)).json();
    boardState = data;
    viewedMoveIndex = idx;
    highlightHistoryItem(idx);
    renderBoard();
}

fetchGame();