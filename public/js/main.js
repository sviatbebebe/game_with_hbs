import { Net } from './net.js';
import { Input } from './input.js';

const lobbyEl   = document.getElementById('lobby');
const gameUIEl  = document.getElementById('gameUI');
const playersListEl = document.getElementById('playersList');
const nameInput = document.getElementById('nameInput');
const nameBtn   = document.getElementById('nameBtn');
const readyBtn  = document.getElementById('readyBtn');
const startBtn  = document.getElementById('startBtn');

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
const hud = document.getElementById('hud');

const TILE = 32;
const CAM_LERP = 0.15;

// Цвета поверхностей
const T_GRASS = 0;
const T_STONE = 1;
const T_WATER = 2;
const T_FLOOR = 3;

function tileColor(t) {
  switch (t) {
    case T_GRASS: return '#2f4a2a';
    case T_STONE: return '#5a5a5a';
    case T_WATER: return '#1d3f63';
    case T_FLOOR: return '#3b3b3b';
    default: return '#000';
  }
}

const net = new Net();
const input = new Input();

const camera = { x: 0, y: 0 };
let mapData = null;
let myPlayer = null;
let camInit = false;

function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

window.addEventListener('mousemove', (e) => {
  input.mouse.x = e.clientX;
  input.mouse.y = e.clientY;
});

window.addEventListener('contextmenu', (e) => e.preventDefault());

window.addEventListener('mousedown', (e) => {
  if (!myPlayer || net.gameState !== 'playing') return;
  const wx = e.clientX + camera.x;
  const wy = e.clientY + camera.y;
  const angle = Math.atan2(wy - myPlayer.y, wx - myPlayer.x);
  if (e.button === 0) net.sendAttack(angle);
  else if (e.button === 2) net.sendMelee(angle);
});

// ---------- лобби ----------
function renderLobby() {
  const isHost = net.id === net.hostId;
  startBtn.style.display = isHost ? '' : 'none';

  const me = net.players.get(net.id);
  if (me && document.activeElement !== nameInput) {
    nameInput.value = me.name || '';
  }
  if (me && me.ready) {
    readyBtn.classList.add('ready-on');
    readyBtn.textContent = 'Не готов';
  } else {
    readyBtn.classList.remove('ready-on');
    readyBtn.textContent = 'Готов';
  }

  playersListEl.innerHTML = '';
  const list = [...net.players.values()].sort((a, b) => a.id - b.id);
  for (const p of list) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = p.name || ('Игрок ' + p.id);

    const badges = document.createElement('span');
    badges.style.display = 'flex';
    badges.style.gap = '6px';

    if (p.id === net.hostId) {
      const b = document.createElement('span');
      b.className = 'badge host'; b.textContent = 'ХОСТ';
      badges.appendChild(b);
    }
    if (p.ready) {
      const b = document.createElement('span');
      b.className = 'badge ready'; b.textContent = 'ГОТОВ';
      badges.appendChild(b);
    }

    li.appendChild(name);
    li.appendChild(badges);
    playersListEl.appendChild(li);
  }
}

function showLobby() {
  lobbyEl.style.display = 'flex';
  gameUIEl.style.display = 'none';
  resize();
  renderLobby();
}
function showGame() {
  lobbyEl.style.display = 'none';
  gameUIEl.style.display = 'block';
  resize();
  camInit = false;
}

nameBtn.addEventListener('click', () => {
  net.setName(nameInput.value.trim() || ('Игрок ' + net.id));
});
nameInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') nameBtn.click();
});
readyBtn.addEventListener('click', () => net.toggleReady());
startBtn.addEventListener('click', () => net.startGame());

net.on('init', (msg) => {
  mapData = msg.map;
  if (msg.gameState === 'playing') showGame();
  else showLobby();
});
net.on('lobby', () => {
  if (net.gameState === 'lobby') showLobby();
});
net.on('started', () => showGame());
net.on('state', () => {
  if (net.gameState === 'playing' && gameUIEl.style.display === 'none') showGame();
});

// ---------- движение ----------
setInterval(() => {
  if (net.gameState !== 'playing') return;
  const mv = input.getMove();
  net.sendMove(mv.dx, mv.dy);
}, 50);

// ---------- отрисовка ----------
function draw() {
  requestAnimationFrame(draw);
  if (net.gameState !== 'playing') return;

  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  myPlayer = net.getSelf();
  if (!myPlayer || !mapData) return;

  const tcx = myPlayer.x - canvas.width / 2;
  const tcy = myPlayer.y - canvas.height / 2;
  if (!camInit) { camera.x = tcx; camera.y = tcy; camInit = true; }
  else {
    camera.x += (tcx - camera.x) * CAM_LERP;
    camera.y += (tcy - camera.y) * CAM_LERP;
  }

  const ox = -camera.x, oy = -camera.y;
  const tiles = mapData.tiles;
  const x0 = Math.max(0, Math.floor(camera.x / TILE));
  const y0 = Math.max(0, Math.floor(camera.y / TILE));
  const x1 = Math.min(mapData.w, Math.ceil((camera.x + canvas.width) / TILE) + 1);
  const y1 = Math.min(mapData.h, Math.ceil((camera.y + canvas.height) / TILE) + 1);

  for (let ty = y0; ty < y1; ty++) {
    for (let tx = x0; tx < x1; tx++) {
      const t = tiles[ty][tx];
      ctx.fillStyle = tileColor(t);
      ctx.fillRect(tx * TILE + ox, ty * TILE + oy, TILE, TILE);
      if (t === T_GRASS || t === T_FLOOR) {
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.lineWidth = 1;
        ctx.strokeRect(tx * TILE + ox + 0.5, ty * TILE + oy + 0.5, TILE - 1, TILE - 1);
      } else if (t === T_WATER) {
        ctx.strokeStyle = 'rgba(120,180,255,0.10)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(tx * TILE + ox + 4, ty * TILE + oy + TILE / 2);
        ctx.lineTo(tx * TILE + ox + TILE - 4, ty * TILE + oy + TILE / 2);
        ctx.stroke();
      }
    }
  }

  // враги
  for (const e of net.enemies.values()) {
    const sx = e.x + ox, sy = e.y + oy;
    ctx.fillStyle = '#c0392b';
    ctx.beginPath(); ctx.arc(sx, sy, e.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#e74c3c'; ctx.lineWidth = 2; ctx.stroke();
    const hpW = 30, hpX = sx - hpW / 2, hpY = sy - e.radius - 8;
    ctx.fillStyle = '#222'; ctx.fillRect(hpX, hpY, hpW, 4);
    ctx.fillStyle = '#e74c3c';
    ctx.fillRect(hpX, hpY, hpW * (e.hp / e.maxHp), 4);
  }

  // другие игроки
  for (const p of net.players.values()) {
    if (p.id === myPlayer.id) continue;
    const sx = p.x + ox, sy = p.y + oy;
    ctx.fillStyle = '#3498db';
    ctx.beginPath(); ctx.arc(sx, sy, p.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#5dade2'; ctx.lineWidth = 2; ctx.stroke();
  }

  // я
  {
    const sx = myPlayer.x + ox, sy = myPlayer.y + oy;
    ctx.fillStyle = '#2ecc71';
    ctx.beginPath(); ctx.arc(sx, sy, myPlayer.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#58d68d'; ctx.lineWidth = 2; ctx.stroke();
  }

  // снаряды
  for (const pr of net.projectiles.values()) {
    const sx = pr.x + ox, sy = pr.y + oy;
    ctx.fillStyle = '#f1c40f';
    ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill();
  }

  // прицел
  if (input.mouse.x || input.mouse.y) {
    ctx.strokeStyle = 'rgba(241,196,15,0.85)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(input.mouse.x, input.mouse.y, 8, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(input.mouse.x - 12, input.mouse.y);
    ctx.lineTo(input.mouse.x + 12, input.mouse.y);
    ctx.moveTo(input.mouse.x, input.mouse.y - 12);
    ctx.lineTo(input.mouse.x, input.mouse.y + 12);
    ctx.stroke();
  }

  hud.textContent = 'HP: ' + Math.max(0, Math.round(myPlayer.hp)) + '/' + myPlayer.maxHp
                  + '   Врагов: ' + net.enemies.size;
}
draw();

// ---------- подключение ----------
const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
net.connect(wsProto + '//' + location.host);
