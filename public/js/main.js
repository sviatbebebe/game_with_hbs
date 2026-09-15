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

const T_GRASS = 0;
const T_STONE = 1;
const T_WATER = 2;
const T_FLOOR = 3;

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

// ---------- процедурный шум для текстур ----------
function hash2(x, y) {
  let h = (x * 374761393 + y * 668265263) | 0;
  h = (h ^ (h >> 13)) * 1274126177;
  h = (h ^ (h >> 16)) >>> 0;
  return h / 4294967296;
}

// ---------- отрисовка тайлов ----------
function drawTile(tx, ty, t, px, py) {
  const h = hash2(tx, ty);
  if (t === T_GRASS) {
    ctx.fillStyle = h > 0.5 ? '#2f4a2a' : '#2b4426';
    ctx.fillRect(px, py, TILE, TILE);
    // травинки
    for (let i = 0; i < 5; i++) {
      const rx = hash2(tx * 7 + i, ty * 13 + i);
      const ry = hash2(tx * 13 + i, ty * 7 + i);
      const x = px + 3 + rx * (TILE - 6);
      const y = py + 3 + ry * (TILE - 6);
      ctx.fillStyle = h > 0.5 ? '#3e5e35' : '#26401f';
      ctx.fillRect(x, y, 2, 3);
    }
  } else if (t === T_STONE) {
    ctx.fillStyle = '#6a6a6a';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#565656';
    ctx.fillRect(px, py + TILE - 6, TILE, 6);
    ctx.fillRect(px + TILE - 6, py, 6, TILE);
    ctx.fillStyle = '#7d7d7d';
    ctx.fillRect(px, py, TILE, 4);
    ctx.fillRect(px, py, 4, TILE);
    // трещины
    ctx.strokeStyle = 'rgba(0,0,0,0.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(px + 6 + h * 8, py + 6);
    ctx.lineTo(px + 10 + h * 12, py + TILE - 6);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(px + 4, py + 12 + h * 10);
    ctx.lineTo(px + TILE - 4, py + 18 + h * 8);
    ctx.stroke();
    // крапинки
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(px + 8, py + 8, 2, 2);
    ctx.fillRect(px + TILE - 12, py + TILE - 12, 2, 2);
    ctx.strokeStyle = '#2b2b2b';
    ctx.strokeRect(px + 0.5, py + 0.5, TILE - 1, TILE - 1);
  } else if (t === T_WATER) {
    ctx.fillStyle = '#1a3a5c';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.strokeStyle = 'rgba(120,180,255,0.35)';
    ctx.lineWidth = 1;
    for (let k = 0; k < 3; k++) {
      const y0 = py + 6 + k * 9 + ((h * 3) | 0);
      ctx.beginPath();
      for (let x = 0; x <= TILE; x += 4) {
        const yy = y0 + Math.sin((x + h * 20) * 0.5) * 1.5;
        if (x === 0) ctx.moveTo(px + x, yy);
        else ctx.lineTo(px + x, yy);
      }
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(200,230,255,0.25)';
    for (let i = 0; i < 3; i++) {
      const sx = px + 4 + hash2(tx * 3 + i, ty * 11 + i) * (TILE - 8);
      const sy = py + 4 + hash2(tx * 11 + i, ty * 3 + i) * (TILE - 8);
      ctx.fillRect(sx, sy, 2, 2);
    }
  } else if (t === T_FLOOR) {
    ctx.fillStyle = '#3a3a3a';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = h > 0.5 ? '#3e3e3e' : '#363636';
    ctx.fillRect(px + 2, py + 2, TILE - 4, TILE - 4);
    ctx.strokeStyle = '#222';
    ctx.lineWidth = 2;
    ctx.strokeRect(px + 1, py + 1, TILE - 2, TILE - 2);
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    ctx.fillRect(px + 6, py + 6, 3, 3);
    ctx.fillRect(px + TILE - 10, py + TILE - 10, 3, 3);
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.fillRect(px + TILE - 8, py + 6, 3, 3);
  }
}

// ---------- отрисовка фигур врагов ----------
function drawShape(shape, cx, cy, r, fill, stroke) {
  ctx.fillStyle = fill;
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (shape === 'square') {
    ctx.rect(cx - r, cy - r, r * 2, r * 2);
  } else if (shape === 'circle') {
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
  } else if (shape === 'pentagon') {
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      const x = cx + Math.cos(a) * r;
      const y = cy + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
  } else {
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
  }
  ctx.fill();
  ctx.stroke();
}

// ---------- лобби ----------
function renderLobby() {
  const isHost = net.id === net.hostId;
  startBtn.style.display = isHost ? '' : 'none';

  const me = net.players.get(net.id);
  if (me && document.activeElement !== nameInput) nameInput.value = me.name || '';
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

setInterval(() => {
  if (net.gameState !== 'playing') return;
  const mv = input.getMove();
  net.sendMove(mv.dx, mv.dy);
}, 50);

// ---------- инвентарь ----------
function drawInventory(player) {
  const inv = player.inventory || {};
  const items = Object.entries(inv);
  const slotW = 64, slotH = 52, gap = 6;
  const y = 10;

  if (items.length === 0) {
    const w = 200;
    const x = (canvas.width - w) / 2;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(x, y, w, slotH);
    ctx.strokeStyle = '#333';
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, slotH - 1);
    ctx.fillStyle = '#666';
    ctx.font = '13px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Инвентарь пуст', canvas.width / 2, y + slotH / 2);
    return;
  }

  const totalW = items.length * slotW + (items.length - 1) * gap;
  const x0 = (canvas.width - totalW) / 2;

  for (let i = 0; i < items.length; i++) {
    const id = items[i][0];
    const count = items[i][1];
    const meta = (net.items && net.items[id]) || { name: id, color: '#888' };
    const x = x0 + i * (slotW + gap);
    ctx.fillStyle = 'rgba(0,0,0,0.65)';
    ctx.fillRect(x, y, slotW, slotH);
    ctx.strokeStyle = '#444';
    ctx.strokeRect(x + 0.5, y + 0.5, slotW - 1, slotH - 1);
    // иконка
    ctx.fillStyle = meta.color;
    ctx.fillRect(x + 6, y + 6, slotW - 12, 24);
    ctx.strokeStyle = 'rgba(0,0,0,0.4)';
    ctx.strokeRect(x + 6.5, y + 6.5, slotW - 13, 23);
    // имя
    ctx.fillStyle = '#ddd';
    ctx.font = '11px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(meta.name, x + slotW / 2, y + 40);
    // счётчик
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.arc(x + slotW - 10, y + 10, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 11px monospace';
    ctx.fillText(String(count), x + slotW - 10, y + 10);
  }
}

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
      drawTile(tx, ty, tiles[ty][tx], tx * TILE + ox, ty * TILE + oy);
    }
  }

  // враги
  for (const e of net.enemies.values()) {
    const sx = e.x + ox, sy = e.y + oy;
    const shape = e.type === 'melee' ? 'square'
                : e.type === 'ranged' ? 'circle'
                : 'pentagon';
    const fill = e.type === 'melee' ? '#c0392b'
               : e.type === 'ranged' ? '#8e44ad'
               : '#d35400';
    const stroke = e.type === 'melee' ? '#e74c3c'
                 : e.type === 'ranged' ? '#a569bd'
                 : '#e67e22';
    drawShape(shape, sx, sy, e.radius, fill, stroke);

    const hpW = 34;
    const hpX = sx - hpW / 2;
    const hpY = sy - e.radius - 9;
    ctx.fillStyle = '#222';
    ctx.fillRect(hpX, hpY, hpW, 4);
    ctx.fillStyle = stroke;
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
    if (pr.ownerType === 'enemy') {
      ctx.fillStyle = '#e67e22';
      ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#d35400'; ctx.lineWidth = 1; ctx.stroke();
    } else {
      ctx.fillStyle = '#f1c40f';
      ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill();
    }
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

  // инвентарь
  drawInventory(myPlayer);

  // HUD (снизу слева, чтобы не мешать инвентарю)
  hud.textContent = 'HP: ' + Math.max(0, Math.round(myPlayer.hp)) + '/' + myPlayer.maxHp
                  + '   Врагов: ' + net.enemies.size;
}
draw();

// ---------- подключение ----------
const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
net.connect(wsProto + '//' + location.host);
