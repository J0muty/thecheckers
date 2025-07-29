document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('friend-search');
    const friendsList = document.getElementById('friends-list');
    const requestsList = document.getElementById('requests-list');
    const requestsBlock = document.getElementById('requests');
    const friendsBlock = document.getElementById('friends');
    const resultsList = document.getElementById('results-list');
    const resultsBlock = document.getElementById('results');
    const friendTemplate = document.getElementById('friend-item-template');
    const chatToggle = document.getElementById('chat-toggle');
    const chatPanel = document.getElementById('chat-panel');
    const chatList = document.getElementById('chat-list');
    const chatWindow = document.getElementById('chat-window');
    const chatTitle = document.getElementById('chat-title');
    const chatBack = document.getElementById('chat-back');
    const chatClose = document.getElementById('chat-close');

    function closeAllDropdowns(){
        document.querySelectorAll('.dropdown.open').forEach(d=>d.classList.remove('open'));
    }
    document.addEventListener('click',e=>{
        if(!e.target.closest('.menu-wrapper')) closeAllDropdowns();
        if(chatPanel.classList.contains('open')&&!e.target.closest('#chat-panel')&&!e.target.closest('#chat-toggle')){
            chatPanel.classList.remove('open');
        }
    });

    async function loadFriends(){
        try{
            const res=await fetch('/api/friends');
            if(!res.ok) return;
            const data=await res.json();

            friendsList.innerHTML='';
            data.friends.forEach(u=>{
                const li=friendTemplate.content.firstElementChild.cloneNode(true);
                li.querySelector('.friend-name').textContent=u.login;

                const dropdown=li.querySelector('.dropdown');
                const btnMsg=dropdown.querySelector('.msg');
                const btnRemove=dropdown.querySelector('.remove');
                const btnBlock=dropdown.querySelector('.block');

                btnMsg.addEventListener('click',e=>{
                    e.stopPropagation();
                    closeAllDropdowns();
                    chatPanel.classList.add('open');
                    window.chatModule.open(u.id);
                    chatTitle.textContent=u.login;
                    chatWindow.classList.add('open');
                    chatList.style.display='none';
                    chatBack.style.display='inline-block';
                });

                btnRemove.addEventListener('click',async()=>{
                    await fetch(`/api/friend_request?to_id=${u.id}&action=remove`,{method:'POST'});
                    showNotification('Удалён из друзей');
                    loadFriends();
                });

                btnBlock.addEventListener('click',async()=>{
                    await fetch(`/api/friend_request?to_id=${u.id}&action=block`,{method:'POST'});
                    showNotification('Пользователь заблокирован');
                    loadFriends();
                });

                li.querySelector('.menu-btn').addEventListener('click',e=>{
                    e.stopPropagation();
                    const alreadyOpen=dropdown.classList.contains('open');
                    closeAllDropdowns();
                    if(!alreadyOpen) dropdown.classList.add('open');
                });

                friendsList.appendChild(li);
            });

            requestsList.innerHTML='';
            const incoming=data.requests.incoming;
            if(incoming.length){
                requestsBlock.style.display='block';
                incoming.forEach(u=>{
                    const li=document.createElement('li');
                    li.textContent=u.login;

                    const btnAccept=document.createElement('button');
                    btnAccept.className='icon-btn';
                    btnAccept.innerHTML='<i class="fa-solid fa-check"></i>';
                    btnAccept.title='Принять';
                    btnAccept.addEventListener('click',async()=>{
                        await fetch(`/api/friend_request?to_id=${u.id}&action=accept`,{method:'POST'});
                        showNotification('Заявка принята');
                        loadFriends();
                    });

                    const btnReject=document.createElement('button');
                    btnReject.className='icon-btn';
                    btnReject.innerHTML='<i class="fa-solid fa-times"></i>';
                    btnReject.title='Отклонить';
                    btnReject.addEventListener('click',async()=>{
                        await fetch(`/api/friend_request?to_id=${u.id}&action=reject`,{method:'POST'});
                        showNotification('Заявка отклонена');
                        loadFriends();
                    });

                    const btnGroup=document.createElement('div');
                    btnGroup.className='request-actions';
                    btnGroup.append(btnAccept,btnReject);
                    li.appendChild(btnGroup);
                    requestsList.appendChild(li);
                });
            }else{
                requestsBlock.style.display='none';
            }
        }catch(err){
            console.error('Failed to load friends:',err);
            showNotification('Ошибка загрузки друзей','error');
        }
    }

    async function searchUsers(q){
        try{
            const res=await fetch('/api/search_users?q='+encodeURIComponent(q));
            if(!res.ok) return;
            const data=await res.json();

            resultsList.innerHTML='';
            data.users.forEach(u=>{
                const li=document.createElement('li');
                li.textContent=u.login;

                const btn=document.createElement('button');
                btn.className='icon-btn';
                btn.innerHTML=u.requested?'<i class="fa-solid fa-minus"></i>':'<i class="fa-solid fa-plus"></i>';
                btn.addEventListener('click',async()=>{
                    const action=u.requested?'cancel':'send';
                    await fetch(`/api/friend_request?to_id=${u.id}&action=${action}`,{method:'POST'});
                    showNotification(action==='send'?'Запрос отправлен':'Запрос отменён');
                    searchUsers(searchInput.value.trim());
                    loadFriends();
                });

                li.appendChild(btn);
                resultsList.appendChild(li);
            });

            resultsBlock.style.display=data.users.length?'block':'none';
        }catch(err){
            console.error('Failed to search users:',err);
            showNotification('Ошибка поиска пользователей','error');
        }
    }

    async function loadChats(){
        try{
            const res=await fetch('/api/chats');
            if(!res.ok) return;
            const data=await res.json();

            chatList.innerHTML='';
            data.chats.forEach(c=>{
                const li=document.createElement('li');
                li.textContent=c.title;
                li.addEventListener('click',()=>{
                    chatTitle.textContent=c.title;
                    chatWindow.classList.add('open');
                    chatList.style.display='none';
                    window.chatModule.open(c.id.split(':').find(id=>id!=userId));
                    chatBack.style.display='inline-block';
                });
                chatList.appendChild(li);
            });
        }catch(err){
            console.error('Failed to load chats:',err);
            showNotification('Ошибка загрузки чатов','error');
        }
    }

    function closeChat(){
        chatPanel.classList.remove('open');
        chatWindow.classList.remove('open');
        chatList.style.display='block';
        chatTitle.textContent='Чаты';
        chatBack.style.display='none';
    }

    chatToggle.addEventListener('click',()=>{
        chatPanel.classList.contains('open')?closeChat():(chatPanel.classList.add('open'),loadChats());
    });

    chatBack.addEventListener('click',()=>{
        chatWindow.classList.remove('open');
        chatList.style.display='block';
        chatTitle.textContent='Чаты';
        chatBack.style.display='none';
    });

    chatClose.addEventListener('click',closeChat);

    searchInput.addEventListener('input',()=>{
        const q=searchInput.value.trim();
        if(q){
            friendsBlock.style.display='none';
            requestsBlock.style.display='none';
            searchUsers(q);
        }else{
            resultsBlock.style.display='none';
            friendsBlock.style.display='block';
            loadFriends();
        }
    });

    function buildWsUrl(){
        const proto=location.protocol==='https:'?'wss':'ws';
        return `${proto}://${location.host}/ws/friends/${userId}`;
    }
    function setupWebSocket(){
        const ws=new WebSocket(buildWsUrl());
        ws.addEventListener('message',()=>loadFriends());
        ws.addEventListener('close',()=>setTimeout(setupWebSocket,1000));
    }

    loadFriends();
    if(typeof userId!=='undefined') setupWebSocket();
});
