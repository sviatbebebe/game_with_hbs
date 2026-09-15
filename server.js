import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = process.env.PORT || 3000;
const TILE = 32;
const MAP_W = 60;
const MAP_H = 45;

// карта: 0 — пол, 1 — стена
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
  if (!filePath.startsWith(root)) {
    res.writeHead(403); res.end('forbidden'); return;
  }
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    const ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

const wss = new WebSocketServer({ server });

const players = new Map();
const enemies = new Map();
const projectiles = new Map();
let nextPlayerId = 1;
let nextEnemyId = 1;
let nextProjectileId = 1;

const PLAYER_RADIUS = 14;
const PLAYER_SPEED = 180;
const PLAYER_HP = 100;

const ENEMY_SPEED = 70;
const ENEMY_HP = 30;
const ENEMY_RADIUS = 14;
const ENEMY_DAMAGE = 10;
const ENEMY_ATTACK_CD = 1.0;

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

function spawnEnemy() {
  for (let i = 0; i < 100; i++) {
    const x = (5 + Math.random() * (MAP_W - 10)) * TILE;
    const y = (5 + Math.random() * (MAP_H - 10)) * TILE;
    if (isSolid(x, y)) continue;
    let tooClose = false;
    for (const p of players.values()) {
      if (Math.hypot(p.x - x, p.y - y) < 250) { tooClose = true; break; }
    }
    if (tooClose) continue;
    const id = nextEnemyId++;
    enemies.set(id, {
      id, x, y,
      hp: ENEMY_HP, maxHp: ENEMY_HP,
      radius: ENEMY_RADIUS,
      speed: ENEMY_SPEED,
      lastHit: 0,
    });
    return;
  }
}

function broadcast(msg) {
  const data = JSON.stringify(msg);
  for (const ws of wss.clients) {
    if (ws.readyState === 1) ws.send(data);
  }
}

wss.on('connection', (ws) => {
  const id = nextPlayerId++;
  const spawn = findSpawn();
  const player = {
    id,
    x: spawn.x, y: spawn.y,
    radius: PLAYER_RADIUS,
    hp: PLAYER_HP, maxHp: PLAYER_HP,
    dirX: 0, dirY: 0,
  };
  players.set(id, player);
  ws.playerId = id;

  ws.send(JSON.stringify({
    type: 'init',
    id,
    map: { tiles: map, tile: TILE, w: MAP_W, h: MAP_H },
    players: [...players.values()],
    enemies: [...enemies.values()],
    projectiles: [...projectiles.values()],
  }));

  broadcast({ type: 'join', player });

  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    const p = players.get(id);
    if (!p) return;
    if (msg.type === 'move') {
      p.dirX = Number(msg.dx) || 0;
      p.dirY = Number(msg.dy) || 0;
    } else if (msg.type === 'attack') {
      const a = Number(msg.angle) || 0;
      const pid = nextProjectileId++;
      projectiles.set(pid, {
        id: pid,
        x: p.x + Math.cos(a) * (p.radius + 4),
        y: p.y + Math.sin(a) * (p.radius + 4),
        vx: Math.cos(a) * PROJ_SPEED,
        vy: Math.sin(a) * PROJ_SPEED,
        ownerId: id,
        ttl: PROJ_TTL,
      });
    }
  });

  ws.on('close', () => {
    players.delete(id);
    broadcast({ type: 'leave', id });
  });
});

function movePlayer(p, dt) {
  const len = Math.hypot(p.dirX, p.dirY) || 1;
  const nx = (p.dirX / len) * PLAYER_SPEED * dt;
  const ny = (p.dirY / len) * PLAYER_SPEED * dt;
  const newX = p.x + nx;
  const newY = p.y + ny;
  if (!isSolid(newX, p.y)) p.x = newX;
  if (!isSolid(p.x, newY)) p.y = newY;
}

function updateEnemies(dt, now) {
  for (const e of enemies.values()) {
    let nearest = null, minD = Infinity;
    for (const p of players.values()) {
      const d = Math.hypot(p.x - e.x, p.y - e.y);
      if (d < minD) { minD = d; nearest = p; }
    }
    if (!nearest) continue;

    if (minD < e.radius + nearest.radius + 4) {
      if (now - e.lastHit > ENEMY_ATTACK_CD * 1000) {
        nearest.hp -= ENEMY_DAMAGE;
        e.lastHit = now;
        if (nearest.hp <= 0) {
          const sp = findSpawn();
          nearest.x = sp.x; nearest.y = sp.y;
          nearest.hp = nearest.maxHp;
        }
      }
      continue;
    }
    const dx = nearest.x - e.x, dy = nearest.y - e.y;
    const l = Math.hypot(dx, dy) || 1;
    const nx = e.x + (dx / l) * e.speed * dt;
    const ny = e.y + (dy / l) * e.speed * dt;
    if (!isSolid(nx, e.y)) e.x = nx;
    if (!isSolid(e.x, ny)) e.y = ny;
  }
}

function updateProjectiles(dt) {
  for (const [id, pr] of projectiles) {
    pr.x += pr.vx * dt;
    pr.y += pr.vy * dt;
    pr.ttl -= dt;
    if (pr.ttl <= 0 || isSolid(pr.x, pr.y)) { projectiles.delete(id); continue; }
    let hit = false;
    for (const e of enemies.values()) {
      if (Math.hypot(pr.x - e.x, pr.y - e.y) < e.radius + PROJ_RADIUS) {
        e.hp -= PROJ_DAMAGE;
        if (e.hp <= 0) enemies.delete(e.id);
        hit = true;
        break;
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
  if (players.size > 0 && enemies.size < 8) spawnEnemy();
}, 2500);

server.listen(PORT, () => {
  console.log(`Server listening on http://localhost:${PORT}`);
});