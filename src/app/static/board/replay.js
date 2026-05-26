const boardElement = document.getElementById('board');
const historyList = document.getElementById('historyList');
const letters = ['', 'A','B','C','D','E','F','G','H',''];
const numbers = ['', '8','7','6','5','4','3','2','1',''];
const myColor = typeof playerColor !== 'undefined' && playerColor ? playerColor : null;

let boardState = [];
let viewedMoveIndex = 0;

function pieceOwner(piece) {
    return piece.toLowerCase() === 'w' ? 'white' : 'black';
}

function cloneBoard(board) {
    return board.map(row => [...row]);
}

function createInitialBoardLocal() {
    const board = Array.from({ length: 8 }, () => Array(8).fill(null));
    for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 8; col++) {
            if ((row + col) % 2 === 1) board[row][col] = 'b';
        }
    }
    for (let row = 5; row < 8; row++) {
        for (let col = 0; col < 8; col++) {
            if ((row + col) % 2 === 1) board[row][col] = 'w';
        }
    }
    return board;
}

function parseMoveNotation(move) {
    const [startStr, endStr] = move.split('->');
    return {
        start: [8 - parseInt(startStr.slice(1), 10), startStr.charCodeAt(0) - 65],
        end: [8 - parseInt(endStr.slice(1), 10), endStr.charCodeAt(0) - 65],
    };
}

function applyMoveLocal(board, start, end) {
    const nextBoard = cloneBoard(board);
    const piece = nextBoard[start[0]][start[1]];
    if (!piece) return nextBoard;
    nextBoard[start[0]][start[1]] = null;

    const stepRow = Math.sign(end[0] - start[0]);
    const stepCol = Math.sign(end[1] - start[1]);
    let row = start[0] + stepRow;
    let col = start[1] + stepCol;
    while (row !== end[0] || col !== end[1]) {
        if (nextBoard[row][col] !== null) {
            nextBoard[row][col] = null;
            break;
        }
        row += stepRow;
        col += stepCol;
    }

    let movedPiece = piece;
    if (movedPiece === movedPiece.toLowerCase()) {
        if (movedPiece === 'w' && end[0] === 0) movedPiece = 'W';
        if (movedPiece === 'b' && end[0] === 7) movedPiece = 'B';
    }
    nextBoard[end[0]][end[1]] = movedPiece;
    return nextBoard;
}

function historyMoveOwners(history) {
    let replayBoard = createInitialBoardLocal();
    return history.map(move => {
        const { start, end } = parseMoveNotation(move);
        const piece = replayBoard[start[0]]?.[start[1]];
        const owner = piece ? pieceOwner(piece) : null;
        replayBoard = applyMoveLocal(replayBoard, start, end);
        return owner;
    });
}

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
                    p.draggable = false;
                    p.addEventListener('dragstart', event => event.preventDefault());
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
    const moveOwners = historyMoveOwners(history);
    history.forEach((m, i) => {
        const li = document.createElement('li');
        li.textContent = displayMove(m);
        li.dataset.index = i + 1;
        li.addEventListener('click', onHistoryClick);
        const isOwnMove = myColor && moveOwners[i] === myColor;
        if (isOwnMove) {
            li.classList.add('my-move');
        } else {
            li.classList.add('opponent-move');
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
