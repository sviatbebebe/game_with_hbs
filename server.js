import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = process.env.PORT || 3000;
const TILE = 32;
const MAP_W = 60;
const MAP_H = 45;

// ---------- карта ----------
const map = [];
for (let y = 0; y < MAP_H; y++) {
  const row = [];
  for (let x = 0; x < MAP_W; x++) {
    const border = x === 0 || y === 0 || x === MAP_W - 1 || y === MAP_H - 1;
    const block = x % 10 === 0 && y % 10 === 0 && x > 0 && y > 0 && x < MAP_W - 1 && y < MAP_H - 1;
    row.push(border || block ? 1 : 0);
  }
  map.push(row);
}
function isSolid(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return true;
  return map[ty][tx] === 1;
}

// ---------- статика ----------
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
};
const server = http.createServer((req, res) => {
  let urlPath = decodeURIComponent(req.url.split('?')[0]);
  if (urlPath === '/') urlPath = '/index.html';
  const root = path.join(__dirname, 'public');
  const filePath = path.join(root, urlPath);
  if (!filePath.startsWith(root)) { res.writeHead(403); res.end('forbidden'); return; }
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    const ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

// ---------- игровое состояние ----------
const wss = new WebSocketServer({ server });
let gameState = 'lobby';
const players = new Map();
const enemies = new Map();
const projectiles = new Map();
const readySet = new Set();
let nextPlayerId = 1;
let nextEnemyId = 1;
let nextProjectileId = 1;
let hostId = null;

const PLAYER_RADIUS = 14;
const PLAYER_SPEED = 180;
const PLAYER_HP = 100;

const ENEMY_RADIUS = 14;
const ENEMY_HP = 30;
const ENEMY_DAMAGE = 10;
const ENEMY_ATTACK_CD = 1000;
const ENEMY_AGGRO = 350;
const ENEMY_CHASE_SPEED = 90;
const ENEMY_WANDER_SPEED = 35;
const ENEMY_HOME_LEASH = 80;

const GROUP_MIN = 3, GROUP_MAX = 5;
const GROUP_SIZE_MIN = 3, GROUP_SIZE_MAX = 5;
const GROUP_SPAWN_DIST = 400;

const PROJ_SPEED = 500;
const PROJ_RADIUS = 5;
const PROJ_DAMAGE = 10;
const PROJ_TTL = 1.5;

function findSpawn() {
  for (let i = 0; i < 300; i++) {
    const x = (5 + Math.random() * (MAP_W - 10)) * TILE;
    const y = (5 + Math.random() * (MAP_H - 10)) * TILE;
    if (!isSolid(x, y)) return { x, y };
  }
  return { x: TILE * 2, y: TILE * 2 };
}

function broadcast(msg) {
  const data = JSON.stringify(msg);
  for (const ws of wss.clients) if (ws.readyState === 1) ws.send(data);
}

function lobbyState() {
  return {
    type: 'lobby',
    hostId,
    players: [...players.values()].map(p => ({
      id: p.id, name: p.name, ready: readySet.has(p.id),
    })),
  };
}
function broadcastLobby() { broadcast(lobbyState()); }

// ---------- спавн врагов группами ----------
function spawnEnemyGroup() {
  for (let attempt = 0; attempt < 200; attempt++) {
    const cx = (5 + Math.random() * (MAP_W - 10)) * TILE;
    const cy = (5 + Math.random() * (MAP_H - 10)) * TILE;
    if (isSolid(cx, cy)) continue;

    let tooClose = false;
    for (const p of players.values()) {
      if (Math.hypot(p.x - cx, p.y - cy) < GROUP_SPAWN_DIST) { tooClose = true; break; }
    }
    if (tooClose) continue;

    const size = GROUP_SIZE_MIN + Math.floor(Math.random() * (GROUP_SIZE_MAX - GROUP_SIZE_MIN + 1));
    for (let i = 0; i < size; i++) {
      const ang = Math.random() * Math.PI * 2;
      const rad = 20 + Math.random() * 60;
      const ex = cx + Math.cos(ang) * rad;
      const ey = cy + Math.sin(ang) * rad;
      if (isSolid(ex, ey)) continue;
      const id = nextEnemyId++;
      enemies.set(id, {
        id, x: ex, y: ey,
        hp: ENEMY_HP, maxHp: ENEMY_HP,
        radius: ENEMY_RADIUS,
        speed: ENEMY_CHASE_SPEED,
        lastHit: 0,
        homeX: ex, homeY: ey,
      });
    }
    return true;
  }
  return false;
}

function countGroups() {
  const arr = [...enemies.values()];
  const used = new Set();
  let groups = 0;
  for (const e of arr) {
    if (used.has(e.id)) continue;
    groups++;
    used.add(e.id);
    for (const o of arr) {
      if (used.has(o.id)) continue;
      if (Math.hypot(e.x - o.x, e.y - o.y) < 150) used.add(o.id);
    }
  }
  return groups;
}

function resetGame() {
  enemies.clear();
  projectiles.clear();
  readySet.clear();
  for (const p of players.values()) {
    const s = findSpawn();
    p.x = s.x; p.y = s.y;
    p.hp = p.maxHp;
    p.dirX = 0; p.dirY = 0;
  }
}

function startGame() {
  gameState = 'playing';
  resetGame();
  const initial = GROUP_MIN + Math.floor(Math.random() * (GROUP_MAX - GROUP_MIN + 1));
  for (let i = 0; i < initial; i++) spawnEnemyGroup();
  broadcast({ type: 'started' });
  broadcast({
    type: 'state',
    players: [...players.values()],
    enemies: [...enemies.values()],
    projectiles: [...projectiles.values()],
  });
}

// ---------- подключения ----------
wss.on('connection', (ws) => {
  const id = nextPlayerId++;
  const spawn = findSpawn();
  const player = {
    id, name: 'Игрок ' + id,
    x: spawn.x, y: spawn.y,
    radius: PLAYER_RADIUS,
    hp: PLAYER_HP, maxHp: PLAYER_HP,
    dirX: 0, dirY: 0,
  };
  players.set(id, player);
  ws.playerId = id;
  if (hostId == null) hostId = id;

  ws.send(JSON.stringify({
    type: 'init',
    id,
    gameState,
    hostId,
    map: { tiles: map, tile: TILE, w: MAP_W, h: MAP_H },
    players: [...players.values()],
    enemies: [...enemies.values()],
    projectiles: [...projectiles.values()],
  }));

  if (gameState === 'playing') {
    broadcast({ type: 'state',
      players: [...players.values()],
      enemies: [...enemies.values()],
      projectiles: [...projectiles.values()],
    });
  } else {
    broadcastLobby();
  }

  ws.on('message', (raw) => {
    let msg; try { msg = JSON.parse(raw); } catch { return; }
    const p = players.get(id);
    if (!p) return;

    if (msg.type === 'setName') {
      p.name = String(msg.name || '').slice(0, 20) || ('Игрок ' + id);
      if (gameState === 'lobby') broadcastLobby();
    } else if (msg.type === 'ready') {
      if (gameState !== 'lobby') return;
      if (readySet.has(id)) readySet.delete(id); else readySet.add(id);
      broadcastLobby();
    } else if (msg.type === 'start') {
      if (id !== hostId || gameState !== 'lobby') return;
      startGame();
    } else if (msg.type === 'backToLobby') {
      if (id !== hostId) return;
      gameState = 'lobby';
      enemies.clear();
      projectiles.clear();
      readySet.clear();
      broadcastLobby();
    } else if (msg.type === 'move') {
      if (gameState !== 'playing') return;
      p.dirX = Number(msg.dx) || 0;
      p.dirY = Number(msg.dy) || 0;
    } else if (msg.type === 'attack') {
      if (gameState !== 'playing') return;
      const a = Number(msg.angle) || 0;
      const pid = nextProjectileId++;
      projectiles.set(pid, {
        id: pid,
        x: p.x + Math.cos(a) * (p.radius + 4),
        y: p.y + Math.sin(a) * (p.radius + 4),
        vx: Math.cos(a) * PROJ_SPEED,
        vy: Math.sin(a) * PROJ_SPEED,
        ownerId: id, ttl: PROJ_TTL,
      });
    }
  });

  ws.on('close', () => {
    players.delete(id);
    readySet.delete(id);
    if (id === hostId) {
      hostId = players.size ? [...players.keys()][0] : null;
    }
    if (players.size === 0 && gameState === 'playing') {
      gameState = 'lobby';
      enemies.clear();
      projectiles.clear();
    }
    if (gameState === 'lobby') broadcastLobby();
    else broadcast({ type: 'leave', id });
  });
});

// ---------- игровой тик ----------
function movePlayer(p, dt) {
  const len = Math.hypot(p.dirX, p.dirY) || 1;
  const nx = (p.dirX / len) * PLAYER_SPEED * dt;
  const ny = (p.dirY / len) * PLAYER_SPEED * dt;
  const newX = p.x + nx, newY = p.y + ny;
  if (!isSolid(newX, p.y)) p.x = newX;
  if (!isSolid(p.x, newY)) p.y = newY;
}

function updateEnemies(dt, now) {
  for (const e of enemies.values()) {
    let target = null, minD = Infinity;
    for (const p of players.values()) {
      const d = Math.hypot(p.x - e.x, p.y - e.y);
      if (d < ENEMY_AGGRO && d < minD) { minD = d; target = p; }
    }

    if (!target) {
      const dx = e.homeX - e.x, dy = e.homeY - e.y;
      const dl = Math.hypot(dx, dy);
      if (dl > ENEMY_HOME_LEASH) {
        const nx = e.x + (dx / dl) * ENEMY_WANDER_SPEED * dt;
        const ny = e.y + (dy / dl) * ENEMY_WANDER_SPEED * dt;
        if (!isSolid(nx, e.y)) e.x = nx;
        if (!isSolid(e.x, ny)) e.y = ny;
      }
      continue;
    }

    if (minD < e.radius + target.radius + 4) {
      if (now - e.lastHit > ENEMY_ATTACK_CD) {
        target.hp -= ENEMY_DAMAGE;
        e.lastHit = now;
        if (target.hp <= 0) {
          const s = findSpawn();
          target.x = s.x; target.y = s.y;
          target.hp = target.maxHp;
        }
      }
      continue;
    }

    const dx = target.x - e.x, dy = target.y - e.y;
    const l = Math.hypot(dx, dy) || 1;
    const nx = e.x + (dx / l) * e.speed * dt;
    const ny = e.y + (dy / l) * e.speed * dt;
    if (!isSolid(nx, e.y)) e.x = nx;
    if (!isSolid(e.x, ny)) e.y = ny;
  }
}

function updateProjectiles(dt) {
  for (const [id, pr] of projectiles) {
    pr.x += pr.vx * dt; pr.y += pr.vy * dt; pr.ttl -= dt;
    if (pr.ttl <= 0 || isSolid(pr.x, pr.y)) { projectiles.delete(id); continue; }
    let hit = false;
    for (const e of enemies.values()) {
      if (Math.hypot(pr.x - e.x, pr.y - e.y) < e.radius + PROJ_RADIUS) {
        e.hp -= PROJ_DAMAGE;
        if (e.hp <= 0) enemies.delete(e.id);
        hit = true; break;
      }
    }
    if (hit) projectiles.delete(id);
  }
}

let lastTick = Date.now();
setInterval(() => {
  const now = Date.now();
  const dt = Math.min((now - lastTick) / 1000, 0.1);
  lastTick = now;

  if (gameState !== 'playing') return;
  for (const p of players.values()) movePlayer(p, dt);
  updateEnemies(dt, now);
  updateProjectiles(dt);

  broadcast({
    type: 'state',
    players: [...players.values()],
    enemies: [...enemies.values()],
    projectiles: [...projectiles.values()],
  });
}, 50);

setInterval(() => {
  if (gameState !== 'playing' || players.size === 0) return;
  const g = countGroups();
  if (g < GROUP_MIN) spawnEnemyGroup();
}, 5000);

// ---------- запуск ----------
function lanIPs() {
  const out = [];
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const i of ifaces[name]) {
      if (i.family === 'IPv4' && !i.internal) out.push({ name, address: i.address });
    }
  }
  return out;
}

server.listen(PORT, '0.0.0.0', () => {
  console.log('Сервер запущен:');
  console.log('  Локально:  http://localhost:' + PORT);
  const ips = lanIPs();
  if (ips.length) {
    for (const info of ips) {
      const tag = info.name.toLowerCase().includes('radmin') ? 'Radmin VPN' : info.name;
      console.log('  ' + tag + ':  http://' + info.address + ':' + PORT);
    }
    console.log('');
    console.log('Раздайте друзьям адрес Radmin-интерфейса.');
  } else {
    console.log('  (сетевых интерфейсов не найдено)');
  }
});
