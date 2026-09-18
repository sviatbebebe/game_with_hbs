import { Net } from './net.js';
import { Input } from './input.js';
import { Fx } from './fx.js';

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
const T_IRON = 4;
const T_COPPER = 5;
const T_COAL = 6;
const T_TIN = 7;
const T_FURNACE = 8;

const net = new Net();
const input = new Input();
const fx = new Fx();
// последние известные позиции снарядов — для искр попаданий
const lastProjPos = new Map();

window.gameApi = {
  sendSpendPoint: (stat) => net.sendSpendPoint(stat),
  sendCraft: (recipe) => net.sendCraft(recipe),
  sendEat: (item) => net.sendEat(item),
  sendPlace: (tx, ty) => net.sendPlace(tx, ty),
  sendPlaceFurnace: (tx, ty) => net.sendPlaceFurnace(tx, ty),
  sendFurnacePut: (id, item, count) => net.sendFurnacePut(id, item, count),
  sendFurnaceTake: (id) => net.sendFurnaceTake(id),
  sendChooseMod: (mod) => net.sendChooseMod(mod),
  sendAdminSet: (damage, speed) => net.sendAdminSet(damage, speed),
  sendAdminLevel: (level) => net.sendAdminLevel(level),
  sendAdminGod: (on) => net.sendAdminGod(on),
  sendAdminGive: (item, count) => net.sendAdminGive(item, count),
  sendAdminSpawn: (enemyType, count) => net.sendAdminSpawn(enemyType, count),
  getLocalPlayer: () => net.getSelf(),
  getFurnaces: () => [...net.furnaces.values()],
  isHost: () => net.id != null && net.id === net.hostId,
  getNet: () => net,
};

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
// зажатая ЛКМ — нужна скорострельному моду
let mouseHeld = false;
let lastAutoShot = 0;
function shootAt(clientX, clientY) {
  if (!myPlayer || net.gameState !== 'playing') return;
  const wx = clientX + camera.x;
  const wy = clientY + camera.y;
  const angle = Math.atan2(wy - myPlayer.y, wx - myPlayer.x);
  net.sendAttack(angle);
  // вспышка у дула (пули теперь появляются ближе в 2 раза)
  const off = (myPlayer.radius + 4) / 2;
  const big = myPlayer.shotMod === 'shotgun';
  fx.muzzle(myPlayer.x + Math.cos(angle) * off, myPlayer.y + Math.sin(angle) * off,
    angle, big ? '#f39c12' : '#f1c40f', big);
}
window.addEventListener('mousedown', (e) => {
  if (!myPlayer || net.gameState !== 'playing') return;
  const wx = e.clientX + camera.x;
  const wy = e.clientY + camera.y;
  const angle = Math.atan2(wy - myPlayer.y, wx - myPlayer.x);
  if (e.button === 0 && input.isDown('KeyF')) {
    net.sendPlace(Math.floor(wx / TILE), Math.floor(wy / TILE));
    return;
  }
  if (e.button === 0 && input.isDown('KeyG')) {
    // печка занимает 2x2, шлём левый верхний угол
    net.sendPlaceFurnace(Math.floor(wx / TILE), Math.floor(wy / TILE));
    return;
  }
  if (e.button === 0) {
    mouseHeld = true;
    input.mouse.down = true;
    lastAutoShot = performance.now();
    shootAt(e.clientX, e.clientY);
  }
  else if (e.button === 2) net.sendMelee(angle);
});
window.addEventListener('mouseup', (e) => {
  if (e.button === 0) { mouseHeld = false; input.mouse.down = false; }
});
window.addEventListener('blur', () => { mouseHeld = false; input.mouse.down = false; });

function nearestFurnace(maxDist) {
  if (!myPlayer) return null;
  let best = null, bestD = Infinity;
  for (const f of net.furnaces.values()) {
    const cx = f.tx * TILE + TILE;
    const cy = f.ty * TILE + TILE;
    const d = Math.hypot(myPlayer.x - cx, myPlayer.y - cy);
    if (d < maxDist && d < bestD) { bestD = d; best = f; }
  }
  return best;
}

window.addEventListener('keydown', (e) => {
  if (e.code === 'KeyE' && !e.repeat && net.gameState === 'playing') {
    if (e.defaultPrevented) return;
    if (window._furnaceClosedAt && Date.now() - window._furnaceClosedAt < 300) return;
    // если окно печки уже открыто — пусть закроется само
    if (window.furnaceUi && window.furnaceUi.isOpen && window.furnaceUi.isOpen()) return;
    // если рядом печка — открыть её интерфейс, иначе съесть еду
    const f = nearestFurnace(160);
    if (f && window.furnaceUi) {
      window.furnaceUi.open(f.id);
      e.preventDefault();
      return;
    }
    net.sendEat();
  }
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
  } else if (t === T_IRON || t === T_COPPER || t === T_COAL || t === T_TIN) {
    // рудные жилы: каменная основа + цветные вкрапления
    ctx.fillStyle = '#5a5a5a';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#4a4a4a';
    ctx.fillRect(px, py + TILE - 6, TILE, 6);
    ctx.fillStyle = '#6e6e6e';
    ctx.fillRect(px, py, TILE, 4);
    const oreColor = t === T_IRON ? '#dfe6e9'
      : t === T_COPPER ? '#e67e22'
      : t === T_COAL ? '#1a1a1a'
      : '#aef1f1';
    ctx.fillStyle = oreColor;
    for (let i = 0; i < 5; i++) {
      const rx = hash2(tx * 5 + i * 3, ty * 7 + i);
      const ry = hash2(tx * 11 + i, ty * 5 + i * 2);
      const x = px + 4 + rx * (TILE - 10);
      const y = py + 4 + ry * (TILE - 10);
      ctx.fillRect(x, y, 5, 5);
      ctx.fillStyle = 'rgba(255,255,255,0.25)';
      ctx.fillRect(x, y, 2, 2);
      ctx.fillStyle = oreColor;
    }
    ctx.strokeStyle = '#2b2b2b';
    ctx.lineWidth = 1;
    ctx.strokeRect(px + 0.5, py + 0.5, TILE - 1, TILE - 1);
  } else if (t === T_FURNACE) {
    // печка 2x2: кирпичная кладка с топкой
    ctx.fillStyle = '#7e5109';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#935e0b';
    ctx.fillRect(px + 2, py + 2, TILE - 4, TILE - 4);
    ctx.strokeStyle = '#4a2f05';
    ctx.lineWidth = 1;
    ctx.strokeRect(px + 4.5, py + 4.5, TILE - 9, TILE - 9);
    ctx.strokeRect(px + 0.5, py + 0.5, TILE - 1, TILE - 1);
    // топочное отверстие
    ctx.fillStyle = '#1a0f00';
    ctx.fillRect(px + 9, py + 18, TILE - 18, 10);
    ctx.fillStyle = 'rgba(255,120,0,0.8)';
    ctx.fillRect(px + 11, py + 20, TILE - 22, 3);
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
  renderMinimapBase();
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
net.on('tileChange', (msg) => {
  updateMinimapTile(msg.tx, msg.ty, msg.tile);
});

setInterval(() => {
  if (net.gameState !== 'playing') return;
  const mv = input.getMove();
  net.sendMove(mv.dx, mv.dy);
  // скорострел: огонь с зажатой ЛКМ
  const self = net.getSelf();
  if (mouseHeld && self && self.shotMod === 'rapid') {
    const now = performance.now();
    if (now - lastAutoShot >= 160) {
      lastAutoShot = now;
      shootAt(input.mouse.x, input.mouse.y);
    }
  }
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

// ---------- прогресс уровня ----------
function drawProgress(p) {
  const w = 300;
  const h = 10;
  const x = (canvas.width - w) / 2;
  const y = canvas.height - 30;
  const xp = p.xp || 0;
  const xpNext = p.xpNext || 0;
  const ratio = xpNext > 0 ? Math.max(0, Math.min(1, xp / xpNext)) : 0;
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = '#2ecc71';
  ctx.fillRect(x, y, w * ratio, h);
  ctx.strokeStyle = '#444';
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  const level = p.level || 1;
  const pts = p.points || 0;
  ctx.fillStyle = '#fff';
  ctx.font = '12px monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('Ур. ' + level + '  Опыт ' + xp + '/' + xpNext + '  Очки: ' + pts, canvas.width / 2, y + h + 10);
  // патроны и перезарядка
  const ammo = (p.ammo != null ? p.ammo : 10);
  const maxAmmo = p.maxAmmo || 10;
  const reloading = p.reloadingUntil && p.reloadingUntil > Date.now();
  const ay = y - 14;
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillRect(x, ay, w, 8);
  ctx.fillStyle = reloading ? '#e74c3c' : '#f1c40f';
  ctx.fillRect(x, ay, w * Math.max(0, ammo / maxAmmo), 8);
  ctx.strokeStyle = '#444';
  ctx.strokeRect(x + 0.5, ay + 0.5, w - 1, 7);
  ctx.fillStyle = reloading ? '#e74c3c' : '#f1c40f';
  ctx.font = '11px monospace';
  const modName = p.shotMod === 'shotgun' ? 'Дробь x5' : p.shotMod === 'rapid' ? 'Скорострел' : 'Обычный';
  ctx.fillText(reloading ? 'Перезарядка...' : 'Патроны ' + ammo + '/' + maxAmmo + '  •  ' + modName,
    canvas.width / 2, ay - 8);
}

// ---------- интерполяция между серверными снапшотами ----------
const TELEPORT_DIST = 150;
function interpPos(o) {
  if (o.px === undefined) return { x: o.x, y: o.y };
  const dx = o.x - o.px, dy = o.y - o.py;
  if (dx * dx + dy * dy > TELEPORT_DIST * TELEPORT_DIST) return { x: o.x, y: o.y };
  const iv = Math.max(1, net.stateInterval || 63);
  const a = Math.min(1, (performance.now() - net.lastStateAt) / iv);
  return { x: o.px + dx * a, y: o.py + dy * a };
}

// ---------- миникарта (левый нижний угол) ----------
const MINIMAP_W = 190;
const MINIMAP_H = 142;
const minimapBase = document.createElement('canvas');
function minimapColor(t) {
  if (t === T_STONE) return '#6a6a6a';
  if (t === T_WATER) return '#1a3a5c';
  if (t === T_FLOOR) return '#3a3a3a';
  if (t === T_IRON) return '#dfe6e9';
  if (t === T_COPPER) return '#b87333';
  if (t === T_COAL) return '#111111';
  if (t === T_TIN) return '#aef1f1';
  if (t === T_FURNACE) return '#e67e22';
  return '#2b4426';
}
function renderMinimapBase() {
  if (!mapData) return;
  minimapBase.width = mapData.w;
  minimapBase.height = mapData.h;
  const mctx = minimapBase.getContext('2d');
  const img = mctx.createImageData(mapData.w, mapData.h);
  const tiles = mapData.tiles;
  for (let y = 0; y < mapData.h; y++) {
    const row = tiles[y];
    for (let x = 0; x < mapData.w; x++) {
      const t = row[x];
      const i = (y * mapData.w + x) * 4;
      let r = 43, g = 68, b = 38;
      if (t === T_STONE) { r = 106; g = 106; b = 106; }
      else if (t === T_WATER) { r = 26; g = 58; b = 92; }
      else if (t === T_FLOOR) { r = 58; g = 58; b = 58; }
      else if (t === T_IRON) { r = 223; g = 230; b = 233; }
      else if (t === T_COPPER) { r = 184; g = 115; b = 51; }
      else if (t === T_COAL) { r = 20; g = 20; b = 20; }
      else if (t === T_TIN) { r = 174; g = 241; b = 241; }
      else if (t === T_FURNACE) { r = 230; g = 126; b = 34; }
      img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 255;
    }
  }
  mctx.putImageData(img, 0, 0);
}
function updateMinimapTile(tx, ty, t) {
  if (!minimapBase.width) return;
  const mctx = minimapBase.getContext('2d');
  mctx.fillStyle = minimapColor(t);
  mctx.fillRect(tx, ty, 1, 1);
}
function drawMinimap() {
  if (!mapData || !minimapBase.width) return;
  const mx = 10;
  const my = canvas.height - MINIMAP_H - 10;
  ctx.fillStyle = 'rgba(0,0,0,0.65)';
  ctx.fillRect(mx - 2, my - 2, MINIMAP_W + 4, MINIMAP_H + 4);
  ctx.drawImage(minimapBase, mx, my, MINIMAP_W, MINIMAP_H);
  ctx.strokeStyle = '#444';
  ctx.strokeRect(mx - 1.5, my - 1.5, MINIMAP_W + 3, MINIMAP_H + 3);
  const sx = MINIMAP_W / mapData.w;
  const sy = MINIMAP_H / mapData.h;
  // враги — красные точки
  ctx.fillStyle = '#e74c3c';
  for (const e of net.enemies.values()) {
    ctx.fillRect(mx + e.x / TILE * sx - 1, my + e.y / TILE * sy - 1, 2, 2);
  }
  // печки — оранжевые квадраты
  ctx.fillStyle = '#f39c12';
  for (const f of net.furnaces.values()) {
    ctx.fillRect(mx + f.tx * sx - 1, my + f.ty * sy - 1, 3, 3);
  }
  // другие игроки — синие
  ctx.fillStyle = '#3498db';
  for (const p of net.players.values()) {
    if (myPlayer && p.id === myPlayer.id) continue;
    ctx.fillRect(mx + p.x / TILE * sx - 1, my + p.y / TILE * sy - 1, 2, 2);
  }
  // я — зелёный + рамка обзора
  if (myPlayer) {
    const vx = camera.x / TILE * sx;
    const vy = camera.y / TILE * sy;
    const vw = canvas.width / TILE * sx;
    const vh = canvas.height / TILE * sy;
    ctx.strokeStyle = 'rgba(255,255,255,0.5)';
    ctx.strokeRect(mx + vx, my + vy, vw, vh);
    ctx.fillStyle = '#2ecc71';
    ctx.beginPath();
    ctx.arc(mx + myPlayer.x / TILE * sx, my + myPlayer.y / TILE * sy, 3, 0, Math.PI * 2);
    ctx.fill();
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
    const ep = interpPos(e); const sx = ep.x + ox, sy = ep.y + oy;
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
    const pp = interpPos(p); const sx = pp.x + ox, sy = pp.y + oy;
    ctx.fillStyle = '#3498db';
    ctx.beginPath(); ctx.arc(sx, sy, p.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#5dade2'; ctx.lineWidth = 2; ctx.stroke();
  }

  // я
  {
    const mp = interpPos(myPlayer); const sx = mp.x + ox, sy = mp.y + oy;
    ctx.fillStyle = '#2ecc71';
    ctx.beginPath(); ctx.arc(sx, sy, myPlayer.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#58d68d'; ctx.lineWidth = 2; ctx.stroke();
  }

  // снаряды — продолговатые, вдоль вектора скорости
  {
    const seen = new Set();
    for (const pr of net.projectiles.values()) {
      seen.add(pr.id);
      lastProjPos.set(pr.id, { x: pr.x, y: pr.y, ownerType: pr.ownerType });
      const qp = interpPos(pr); const sx = qp.x + ox, sy = qp.y + oy;
      const ang = Math.atan2(pr.vy || 0, pr.vx || 1);
      const enemy = pr.ownerType === 'enemy';
      const body = enemy ? '#e67e22' : '#f1c40f';
      const edge = enemy ? '#d35400' : '#f39c12';
      ctx.save();
      ctx.translate(sx, sy);
      ctx.rotate(ang);
      // светящаяся подложка
      ctx.fillStyle = enemy ? 'rgba(230,126,34,0.25)' : 'rgba(241,196,15,0.25)';
      ctx.beginPath();
      ctx.ellipse(0, 0, 11, 6, 0, 0, Math.PI * 2);
      ctx.fill();
      // корпус пули
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.ellipse(0, 0, 9, 3.2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = edge;
      ctx.lineWidth = 1;
      ctx.stroke();
      // яркий носик
      ctx.fillStyle = '#fff';
      ctx.fillRect(4, -1.2, 4, 2.4);
      ctx.restore();
    }
    // исчезнувшие снаряды — искры попаданий (не больше 5 за кадр)
    let bursts = 0;
    for (const [id, pos] of [...lastProjPos]) {
      if (!seen.has(id)) {
        if (bursts < 5) {
          fx.impact(pos.x, pos.y, pos.ownerType === 'enemy' ? '#e67e22' : '#f1c40f');
          bursts++;
        }
        lastProjPos.delete(id);
      }
    }
    if (lastProjPos.size > 600) {
      // страховка от утечки при лагах
      for (const id of [...lastProjPos.keys()].slice(0, lastProjPos.size - 600)) lastProjPos.delete(id);
    }
  }
  fx.update(1 / 60);
  fx.draw(ctx, ox, oy);

  // печки: прогресс плавки над центром 2x2
  for (const f of net.furnaces.values()) {
    const cx = f.tx * TILE + TILE + ox;
    const cy = f.ty * TILE + TILE + oy;
    if (cx < -80 || cy < -40 || cx > canvas.width + 80 || cy > canvas.height + 40) continue;
    if (f.smelting) {
      const ratio = f.smelting.total > 0 ? 1 - f.smelting.remaining / f.smelting.total : 0;
      ctx.fillStyle = '#222';
      ctx.fillRect(cx - 32, cy - 44, 64, 6);
      ctx.fillStyle = '#f39c12';
      ctx.fillRect(cx - 32, cy - 44, 64 * Math.max(0, Math.min(1, ratio)), 6);
      ctx.fillStyle = '#fff';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(f.smelting.type.replace('_ore', ''), cx, cy - 48);
    } else if ((f.coal || 0) > 0 || (f.charges || 0) > 0) {
      ctx.fillStyle = 'rgba(243,156,18,0.9)';
      ctx.font = '12px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('🔥', cx, cy - 44);
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
  drawProgress(myPlayer);
  drawMinimap();

  // HUD (сверху слева, миникарта теперь слева внизу)
  const godTag = myPlayer.god ? '  БОГ' : '';
  hud.textContent = 'HP: ' + Math.max(0, Math.round(myPlayer.hp)) + '/' + myPlayer.maxHp
                  + '   Врагов: ' + net.enemies.size + '/' + 300
                  + '   Печек: ' + net.furnaces.size + godTag;
}
draw();

// ---------- подключение ----------
const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
net.connect(wsProto + '//' + location.host);
