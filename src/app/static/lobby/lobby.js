const playersList=document.getElementById('players')
const startBtn=document.getElementById('startBtn')
const leaveBtn=document.getElementById('leaveBtn')
const friendsTable=document.getElementById('friendsTable')
const loadMoreBtn=document.getElementById('loadMoreBtn')
const hideBtn=document.getElementById('hideBtn')
const inviteSection=document.querySelector('.invite-section')
let currentHostId=typeof hostId!=='undefined'?hostId:null
let lobbyInfo=null
let friendsData=[]
let showAllFriends=false
let currentMenu=null
let leaving=false
function updateRoleUi(){
    const isHost=currentHostId===userId
    startBtn.style.display=isHost?'inline-block':'none'
    inviteSection.style.display=isHost?'flex':'none'
}
function renderLobbyInfo(info){
    lobbyInfo=info
    currentHostId=lobbyInfo.host
    if(lobbyInfo.board_id){window.location.href=`/board/${lobbyInfo.board_id}`;return}
    playersList.innerHTML=''
    lobbyInfo.players.forEach((name,idx)=>{
        const uid=lobbyInfo.player_ids[idx]
        const color=lobbyInfo.colors?lobbyInfo.colors[uid]:null
        const li=document.createElement('li')
        if(uid===currentHostId){
            const crown=document.createElement('span')
            crown.className='crown'
            crown.innerHTML='<i class="fa-solid fa-crown"></i>'
            li.appendChild(crown)
        }
        const nameSpan=document.createElement('span')
        nameSpan.textContent=color?`${name} (${color==='white'?'Белый':'Чёрный'})`:name
        li.appendChild(nameSpan)
        if(currentHostId===userId&&uid!==userId){
            li.style.cursor='pointer'
            li.addEventListener('click',e=>{e.stopPropagation();showPlayerMenu(li,uid)})
        }
        playersList.appendChild(li)
    })
    const myColor=lobbyInfo.colors?lobbyInfo.colors[userId]:null
    document.querySelectorAll('input[name="color"]').forEach(r=>{
        r.checked=r.value===myColor
        r.dataset.waschecked=r.checked
    })
    updateRoleUi()
    startBtn.removeAttribute('disabled')
    if(currentHostId===userId)loadFriends()
}
function buildLobbyWsUrl(id){
    const proto=location.protocol==='https:'?'wss':'ws'
    return`${proto}://${location.host}/ws/lobby/${id}`
}
function setupLobbyWs(){
    const ws=new WebSocket(buildLobbyWsUrl(lobbyId))
    ws.addEventListener('message',e=>{
        try{
            const d=JSON.parse(e.data)
            if(d.type==='start'){window.location.href=`/board/${d.board_id}`;return}
            if(d.type==='state'){
                if(!d.state.player_ids.includes(String(userId))){
                    if(!leaving){
                        localStorage.setItem('pendingToast',JSON.stringify({message:'Вас выгнали из лобби',type:'error'}))
                    }
                    window.location.href='/'
                    return
                }
                renderLobbyInfo(d.state)
                return
            }
            if(d.type==='closed'){window.location.href='/';return}
        }catch{}
    })
    ws.addEventListener('close',()=>setTimeout(setupLobbyWs,1000))
}
async function loadInfo(){
    const res=await fetch(`/api/lobby/${lobbyId}`)
    if(res.ok)renderLobbyInfo(await res.json())
}
async function loadFriends(){
    const res=await fetch('/api/friends')
    if(res.ok){const data=await res.json();friendsData=data.friends;renderFriends()}
}
async function sendInvite(id){
    const res=await fetch(`/api/lobby/invite/${lobbyId}?to_id=${id}`,{method:'POST'})
    res.ok?showNotification('Приглашение отправлено'):showNotification('Не удалось отправить приглашение','error')
}
function renderFriends(){
    friendsTable.innerHTML=''
    const list=showAllFriends?friendsData:friendsData.slice(0,5)
    list.forEach(f=>{
        const tr=document.createElement('tr')
        const nameTd=document.createElement('td')
        nameTd.textContent=f.login
        const btnTd=document.createElement('td')
        btnTd.style.flex='0 0 auto'
        const btn=document.createElement('button')
        btn.className='invite-btn'
        let status=''
        if(lobbyInfo.player_ids.includes(String(f.id))){status='in-room';btn.textContent='В комнате';btn.disabled=true}
        else if(lobbyInfo.invites[String(f.id)]){
            status=lobbyInfo.invites[String(f.id)]
            if(status==='sent'){btn.textContent='Отправлено';btn.disabled=true}
            else if(status==='declined'){btn.textContent='Отклонено';btn.classList.add('declined');btn.addEventListener('click',()=>sendInvite(f.id))}
            else if(status==='accepted'){btn.textContent='В комнате';btn.disabled=true;status='in-room'}
        }else{btn.textContent='Отправить';btn.addEventListener('click',()=>sendInvite(f.id))}
        if(status==='sent'||status==='in-room')btn.classList.add(status)
        btnTd.appendChild(btn)
        tr.append(nameTd,btnTd)
        friendsTable.appendChild(tr)
    })
    loadMoreBtn.style.display=friendsData.length>5&&!showAllFriends?'inline-block':'none'
    hideBtn.style.display=friendsData.length>5&&showAllFriends?'inline-block':'none'
}
function hidePlayerMenu(){
    if(currentMenu){currentMenu.remove();currentMenu=null}
}
function showPlayerMenu(li,uid){
    hidePlayerMenu()
    const menu=document.createElement('div')
    menu.className='player-menu'
    const giveBtn=document.createElement('button')
    giveBtn.textContent='Передать корону'
    giveBtn.addEventListener('click',async()=>{
        hidePlayerMenu()
        await fetch(`/api/lobby/host/${lobbyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({to_id:uid})})
    })
    const kickBtn=document.createElement('button')
    kickBtn.textContent='Выгнать'
    kickBtn.addEventListener('click',async()=>{
        hidePlayerMenu()
        await fetch(`/api/lobby/kick/${lobbyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:uid})})
    })
    menu.append(giveBtn,kickBtn)
    li.appendChild(menu)
    currentMenu=menu
    document.addEventListener('click',hidePlayerMenu,{once:true})
}
startBtn.addEventListener('click',async()=>{
    const latest=await fetch(`/api/lobby/${lobbyId}`)
    if(!latest.ok){showNotification('Не удалось обновить данные','error');return}
    lobbyInfo=await latest.json()
    if(lobbyInfo.player_ids.length<2){showNotification('Нужен второй игрок','error');return}
    const radio=document.querySelector('input[name="color"]:checked')
    if(!radio){showNotification('Выберите цвет','error');return}
    const myColor=radio.value
    const otherId=lobbyInfo.player_ids.find(id=>id!==userId)
    const otherColor=lobbyInfo.colors?lobbyInfo.colors[otherId]:null
    if(!otherColor){showNotification('Ожидаем выбор цвета другим игроком','error');return}
    if(otherColor===myColor){showNotification('Цвета совпадают','error');return}
    startBtn.disabled=true
    const res=await fetch(`/api/lobby/start/${lobbyId}`,{method:'POST'})
    const data=await res.json().catch(()=>({}))
    if(!res.ok){
        const d=data.detail
        if(d==='not enough players')showNotification('Нужен второй игрок','error')
        else if(d==='color not selected')showNotification('Цвет не выбран','error')
        else if(d==='colors conflict')showNotification('Цвета совпадают','error')
        else showNotification('Не удалось начать игру','error')
        startBtn.disabled=false
        return
    }
    if(data.board_id)window.location.href=`/board/${data.board_id}`
})
leaveBtn.addEventListener('click',async()=>{
    leaving=true
    await fetch(`/api/lobby/leave/${lobbyId}`,{method:'POST'})
    window.location.href='/'
})
document.querySelectorAll('input[name="color"]').forEach(r=>{
    r.addEventListener('click',async()=>{
        if(r.dataset.waschecked==='true'){
            r.checked=false
            r.dataset.waschecked='false'
            await fetch(`/api/lobby/color/${lobbyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({color:null})})
        }else{
            document.querySelectorAll('input[name="color"]').forEach(inp=>inp.dataset.waschecked='false')
            r.dataset.waschecked='true'
            await fetch(`/api/lobby/color/${lobbyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({color:r.value})})
        }
    })
})
loadMoreBtn.addEventListener('click',()=>{showAllFriends=true;renderFriends()})
hideBtn.addEventListener('click',()=>{showAllFriends=false;renderFriends()})
document.addEventListener('DOMContentLoaded',()=>{
    loadInfo()
    setupLobbyWs()
    updateRoleUi()
})
