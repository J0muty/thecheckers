export function initChat(container, currentUser) {
    const messageList = container.querySelector('.chat-messages');
    const form = container.querySelector('.chat-form');
    const input = container.querySelector('.chat-input');
    let ws;
    let chatId;
    let withId;

    function appendMessage(msg) {
        const div = document.createElement('div');
        div.className = msg.sender == currentUser ? 'msg me' : 'msg';

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
        messageList.appendChild(div);
        messageList.scrollTop = messageList.scrollHeight;
    }

    async function loadHistory(id) {
        const res = await fetch(`/api/messages/${id}`);
        if (!res.ok) return;
        const data = await res.json();
        chatId = data.chat_id;
        withId = id;
        messageList.innerHTML = '';
        data.messages.forEach(appendMessage);
        setupWs();
    }

    function setupWs() {
        if (ws) ws.close();
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        ws = new WebSocket(`${proto}://${location.host}/ws/chat/${chatId}`);
        ws.addEventListener('message', e => {
            const m = JSON.parse(e.data);
            appendMessage(m);
        });
    }

    form.addEventListener('submit', e => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        const payload = { sender: parseInt(currentUser), receiver: parseInt(withId), text };
        ws.send(JSON.stringify(payload));
        input.value = '';
    });

    return { open: loadHistory };
}