(function(){
    const container = document.getElementById('lobbyChat');
    if(!container) return;
    const messagesEl = container.querySelector('.chat-messages');
    const form = container.querySelector('.chat-form');
    const input = container.querySelector('.chat-input');
    let ws;

    function append(msg) {
        const div = document.createElement('div');
        div.className = msg.sender == userId ? 'msg me' : 'msg';

        const header = document.createElement('div');
        header.className = 'msg-header';

        const avatar = document.createElement('span');
        avatar.className = 'avatar';
        avatar.textContent = (msg.login || String(msg.sender))[0].toUpperCase();

        const name = document.createElement('span');
        name.className = 'name';
        name.textContent = msg.login || msg.sender;

        header.append(avatar, name);

        const text = document.createElement('div');
        text.className = 'text';
        text.textContent = msg.text;

        div.append(header, text);
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function buildWsUrl(){
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return `${proto}://${location.host}/ws/lobby_chat/${lobbyId}`;
    }

    function setupWs(){
        if(ws) ws.close();
        ws = new WebSocket(buildWsUrl());
        ws.addEventListener('message', e=>{
            try{ append(JSON.parse(e.data)); }catch{}
        });
    }

    async function loadHistory(){
        const res = await fetch(`/api/lobby/messages/${lobbyId}`);
        if(res.ok){
            const data = await res.json();
            messagesEl.innerHTML = '';
            data.messages.forEach(append);
            setupWs();
        }
    }

    form.addEventListener('submit', e=>{
        e.preventDefault();
        const text = input.value.trim();
        if(!text) return;
        ws.send(JSON.stringify({sender: parseInt(userId), text}));
        input.value='';
    });

    document.addEventListener('DOMContentLoaded', loadHistory);
})();