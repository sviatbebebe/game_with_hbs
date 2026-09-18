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
const MAP_W = 200;
const MAP_H = 150;

// Типы поверхности
const T_GRASS = 0;
const T_STONE = 1;
const T_WATER = 2;
const T_FLOOR = 3;

// ---------- карта ----------
const map = [];
for (let y = 0; y < MAP_H; y++) {
  const row = [];
  for (let x = 0; x < MAP_W; x++) row.push(T_GRASS);
  map.push(row);
}
for (let x = 0; x < MAP_W; x++) { map[0][x] = T_STONE; map[MAP_H - 1][x] = T_STONE; }
for (let y = 0; y < MAP_H; y++) { map[y][0] = T_STONE; map[y][MAP_W - 1] = T_STONE; }

// пруды
for (let i = 0; i < 30; i++) {
  const cx = 5 + Math.floor(Math.random() * (MAP_W - 10));
  const cy = 5 + Math.floor(Math.random() * (MAP_H - 10));
  const r = 4 + Math.floor(Math.random() * 6);
  for (let y = cy - r; y <= cy + r; y++) {
    for (let x = cx - r; x <= cx + r; x++) {
      if (x < 1 || y < 1 || x >= MAP_W - 1 || y >= MAP_H - 1) continue;
      const d = Math.hypot(x - cx, y - cy);
      if (d < r - Math.random() * 1.5) map[y][x] = T_WATER;
    }
  }
}

// каменные площадки
for (let i = 0; i < 40; i++) {
  const cx = 5 + Math.floor(Math.random() * (MAP_W - 10));
  const cy = 5 + Math.floor(Math.random() * (MAP_H - 10));
  const r = 3 + Math.floor(Math.random() * 5);
  for (let y = cy - r; y <= cy + r; y++) {
    for (let x = cx - r; x <= cx + r; x++) {
      if (x < 1 || y < 1 || x >= MAP_W - 1 || y >= MAP_H - 1) continue;
      if (map[y][x] !== T_GRASS) continue;
      const d = Math.hypot(x - cx, y - cy);
      if (d < r - Math.random() * 1.2) map[y][x] = T_FLOOR;
    }
  }
}

// стены
for (let i = 0; i < 200; i++) {
  const cx = 2 + Math.floor(Math.random() * (MAP_W - 4));
  const cy = 2 + Math.floor(Math.random() * (MAP_H - 4));
  const size = 2 + Math.floor(Math.random() * 6);
  let x = cx, y = cy;
  for (let j = 0; j < size; j++) {
    if (x > 0 && y > 0 && x < MAP_W - 1 && y < MAP_H - 1) {
      if (map[y][x] === T_GRASS || map[y][x] === T_FLOOR) map[y][x] = T_STONE;
    }
    x += Math.floor(Math.random() * 3) - 1;
    y += Math.floor(Math.random() * 3) - 1;
  }
}

const wallHP = new Map();
const WALL_HP = 50;

function isSolid(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return true;
  const t = map[ty][tx];
  return t === T_STONE || t === T_WATER;
}
function blocksProjectile(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return true;
  return map[ty][tx] === T_STONE;
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

// --- типы врагов ---
const ENEMY_TYPES = {
  melee: {
    hp: 300, speed: 220, radius: 16,
    damage: 15, attackCD: 800, attackRange: 0, // contact
    color: '#c0392b', shape: 'square',
    loot: 'cheese',
  },
  ranged: {
    hp: 80, speed: 180, radius: 14,
    damage: 8, attackCD: 1500, attackRange: 320,
    projectileSpeed: 350,
    color: '#8e44ad', shape: 'circle',
    loot: 'kuraga',
  },
  wanderer: {
    hp: 120, speed: 60, chaseSpeed: 260, radius: 15,
    damage: 12, attackCD: 900, attackRange: 0,
    color: '#d35400', shape: 'pentagon',
    loot: 'socks',
  },
};

const ENEMY_AGGRO = 350;
const ENEMY_AGGRO_MEMORY = 6000;
const ENEMY_HOME_LEASH = 80;

const GROUP_MIN = 8, GROUP_MAX = 15;
const GROUP_SIZE_MIN = 3, GROUP_SIZE_MAX = 6;
const GROUP_SPAWN_DIST = 400;

const PROJ_SPEED = 500;
const PROJ_RADIUS = 5;
const PROJ_DAMAGE = 25;
const PROJ_TTL = 1.5;
const PROJ_MAX_DIST = 400;

const MELEE_RANGE = 60;
const MELEE_DAMAGE = 25;
const MELEE_CD = 300;
const playerMeleeLast = new Map();

const LOOT_CHANCE = 0.35;

// ---------- прогрессия ----------
const XP_SHARE_RADIUS = 400;
const XP_BASE = 100;
const XP_EXP = 1.5;
function xpForLevel(level) {
  return Math.floor(XP_BASE * Math.pow(level, XP_EXP));
}
function xpForEnemy(e) {
  return Math.floor(e.maxHp / 10);
}

// ---------- предметы ----------
const ITEMS = {
  cheese:  { name: 'Сыр',    color: '#f1c40f' },
  kuraga:  { name: 'Курага', color: '#e67e22' },
  socks:   { name: 'Носки',  color: '#3498db' },
  stone:   { name: 'Камень', color: '#7f8c8d' },
  floor:   { name: 'Плита',  color: '#95a5a6' },
  grass:   { name: 'Трава',  color: '#27ae60' },
  water:   { name: 'Вода',   color: '#2980b9' },
  brick:   { name: 'Кирпич', color: '#b08d57' },
  medkit:  { name: 'Аптечка', color: '#e74c3c' },
};
const TILE_TO_ITEM = {
  [T_STONE]: 'stone',
  [T_FLOOR]: 'floor',
  [T_GRASS]: 'grass',
  [T_WATER]: 'water',
};

function addItem(player, itemId) {
  if (!player.inventory) player.inventory = {};
  player.inventory[itemId] = (player.inventory[itemId] || 0) + 1;
}

// ---------- крафт ----------
const RECIPES = {
  brick: { out: 'brick', need: { stone: 2 }, alt: { socks: 3 } },
  medkit: { out: 'medkit', need: { cheese: 2, kuraga: 1 } },
};
const EAT_HP = { medkit: 60, cheese: 12, kuraga: 8 };
const PLACE_RANGE = 130;
function hasItems(p, need) {
  if (!p.inventory) return false;
  for (const k of Object.keys(need)) if ((p.inventory[k] || 0) < need[k]) return false;
  return true;
}
function takeItems(p, need) {
  if (!hasItems(p, need)) return false;
  for (const k of Object.keys(need)) { p.inventory[k] -= need[k]; if (p.inventory[k] <= 0) delete p.inventory[k]; }
  return true;
}
function doCraft(p, recipe) {
  const r = RECIPES[recipe]; if (!r) return;
  if (!p.inventory) p.inventory = {};
  if (hasItems(p, r.need)) takeItems(p, r.need);
  else if (r.alt && hasItems(p, r.alt)) takeItems(p, r.alt);
  else return;
  addItem(p, r.out);
}
function doEat(p, item) {
  const ids = (item && EAT_HP[item]) ? [item] : ['medkit', 'cheese', 'kuraga'];
  if (p.hp >= p.maxHp) return;
  for (const id of ids) {
    if ((p.inventory[id] || 0) > 0) {
      p.inventory[id]--; if (p.inventory[id] <= 0) delete p.inventory[id];
      p.hp = Math.min(p.maxHp, p.hp + EAT_HP[id]);
      return;
    }
  }
}
function doPlace(p, tx, ty) {
  if (!p.inventory || (p.inventory.brick || 0) <= 0) return;
  if (tx < 1 || ty < 1 || tx >= MAP_W - 1 || ty >= MAP_H - 1) return;
  const t = map[ty][tx];
  if (t !== T_GRASS && t !== T_FLOOR) return;
  const cx = tx * TILE + TILE / 2, cy = ty * TILE + TILE / 2;
  if (Math.hypot(p.x - cx, p.y - cy) > PLACE_RANGE) return;
  for (const o of players.values()) if (Math.hypot(o.x - cx, o.y - cy) < 20) return;
  p.inventory.brick--; if (p.inventory.brick <= 0) delete p.inventory.brick;
  map[ty][tx] = T_STONE;
  wallHP.delete(tx + ',' + ty);
  broadcast({ type: 'tileChange', tx, ty, tile: T_STONE });
}

// ---------- спавн ----------
function findSpawn() {
  for (let i = 0; i < 500; i++) {
    const tx = 2 + Math.floor(Math.random() * (MAP_W - 4));
    const ty = 2 + Math.floor(Math.random() * (MAP_H - 4));
    if (map[ty][tx] === T_GRASS || map[ty][tx] === T_FLOOR) {
      return { x: tx * TILE + TILE / 2, y: ty * TILE + TILE / 2 };
    }
  }
  return { x: TILE * 2, y: TILE * 2 };
}

function pickEnemyType() {
  const r = Math.random();
  if (r < 0.35) return 'melee';
  if (r < 0.60) return 'ranged';
  return 'wanderer';
}

function makeEnemy(type, x, y) {
  const cfg = ENEMY_TYPES[type];
  const id = nextEnemyId++;
  return {
    id, type, x, y,
    hp: cfg.hp, maxHp: cfg.hp,
    radius: cfg.radius,
    lastHit: 0,
    homeX: x, homeY: y,
    aggroUntil: 0,
    wanderAngle: Math.random() * Math.PI * 2,
    wanderUntil: 0,
  };
}

function spawnEnemyGroup() {
  for (let attempt = 0; attempt < 400; attempt++) {
    const tx = 3 + Math.floor(Math.random() * (MAP_W - 6));
    const ty = 3 + Math.floor(Math.random() * (MAP_H - 6));
    if (map[ty][tx] !== T_GRASS && map[ty][tx] !== T_FLOOR) continue;
    const cx = tx * TILE + TILE / 2;
    const cy = ty * TILE + TILE / 2;

    let tooClose = false;
    for (const p of players.values()) {
      if (Math.hypot(p.x - cx, p.y - cy) < GROUP_SPAWN_DIST) { tooClose = true; break; }
    }
    if (tooClose) continue;

    const size = GROUP_SIZE_MIN + Math.floor(Math.random() * (GROUP_SIZE_MAX - GROUP_SIZE_MIN + 1));
    let placed = 0;
    for (let i = 0; i < size * 4 && placed < size; i++) {
      const ang = Math.random() * Math.PI * 2;
      const rad = 20 + Math.random() * 100;
      const ex = cx + Math.cos(ang) * rad;
      const ey = cy + Math.sin(ang) * rad;
      if (isSolid(ex, ey)) continue;
      const type = pickEnemyType();
      const e = makeEnemy(type, ex, ey);
      enemies.set(e.id, e);
      placed++;
    }
    if (placed > 0) return true;
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

function resetGame() {
  enemies.clear();
  projectiles.clear();
  readySet.clear();
  for (const p of players.values()) {
    const s = findSpawn();
    p.x = s.x; p.y = s.y;
    p.maxHp = PLAYER_HP;
    p.hp = p.maxHp;
    p.dirX = 0; p.dirY = 0;
    p.inventory = {};
    p.level = 1;
    p.xp = 0;
    p.xpNext = xpForLevel(1);
    p.points = 0;
    p.upgrades = { maxHp: 0, damage: 0, speed: 0 };
  }
}

// ---------- прогрессия ----------
function getDamageMult(p) {
  return 1 + 0.10 * (p.upgrades ? p.upgrades.damage : 0);
}
function getSpeedMult(p) {
  return 1 + 0.05 * (p.upgrades ? p.upgrades.speed : 0);
}
function grantLevelUps(p) {
  while (p.xp >= p.xpNext) {
    p.level++;
    p.points++;
    p.xpNext = xpForLevel(p.level);
    broadcast({ type: 'levelUp', id: p.id, level: p.level, points: p.points, xpNext: p.xpNext });
  }
}
function distributeXp(deathX, deathY, xpTotal, killerId) {
  const eligible = [...players.values()].filter((pl) => Math.hypot(pl.x - deathX, pl.y - deathY) <= XP_SHARE_RADIUS);
  const list = eligible.length ? eligible : (players.get(killerId) ? [players.get(killerId)] : []);
  if (!list.length) return;
  const share = Math.floor(xpTotal / list.length);
  const remainder = xpTotal - share * list.length;
  let extraId = list[0].id;
  for (const pl of list) {
    if (pl.id === killerId) { extraId = killerId; break; }
  }
  for (const pl of list) {
    let gain = share;
    if (pl.id === extraId) gain += remainder;
    pl.xp += gain;
    grantLevelUps(pl);
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

// ---------- удар по стене ----------
function meleeStrike(p, angle) {
  const now = Date.now();
  const last = playerMeleeLast.get(p.id) || 0;
  if (now - last < MELEE_CD) return;
  playerMeleeLast.set(p.id, now);

  const step = 8;
  for (let d = 0; d <= MELEE_RANGE; d += step) {
    const wx = p.x + Math.cos(angle) * d;
    const wy = p.y + Math.sin(angle) * d;
    const tx = Math.floor(wx / TILE);
    const ty = Math.floor(wy / TILE);
    if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return;
    if (map[ty][tx] !== T_STONE) continue;

    const key = tx + ',' + ty;
    const cur = wallHP.has(key) ? wallHP.get(key) : WALL_HP;
    const next = cur - MELEE_DAMAGE;
    if (next <= 0) {
      map[ty][tx] = T_FLOOR;
      wallHP.delete(key);
      addItem(p, TILE_TO_ITEM[T_STONE]);
      broadcast({ type: 'tileChange', tx, ty, tile: T_FLOOR });
    } else {
      wallHP.set(key, next);
      broadcast({ type: 'tileChange', tx, ty, tile: T_STONE, hp: next });
    }
    return;
  }
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
    inventory: {},
    level: 1, xp: 0, xpNext: xpForLevel(1), points: 0,
    upgrades: { maxHp: 0, damage: 0, speed: 0 },
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
    items: ITEMS,
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
      const sx = p.x + Math.cos(a) * (p.radius + 4);
      const sy = p.y + Math.sin(a) * (p.radius + 4);
      projectiles.set(pid, {
        id: pid, x: sx, y: sy,
        startX: sx, startY: sy,
        vx: Math.cos(a) * PROJ_SPEED,
        vy: Math.sin(a) * PROJ_SPEED,
        ownerType: 'player',
        ownerId: id, ttl: PROJ_TTL,
        maxDist: PROJ_MAX_DIST,
        damage: Math.round(PROJ_DAMAGE * getDamageMult(p)),
      });
    } else if (msg.type === 'melee') {
      if (gameState !== 'playing') return;
      meleeStrike(p, Number(msg.angle) || 0);
    } else if (msg.type === 'spendPoint') {
      const stat = String(msg.stat || '');
      if (stat !== 'maxHp' && stat !== 'damage' && stat !== 'speed') return;
      if (!(p.points > 0)) return;
      if (!p.upgrades) p.upgrades = { maxHp: 0, damage: 0, speed: 0 };
      p.points--;
      if (stat === 'maxHp') {
        p.upgrades.maxHp++;
        p.maxHp += 20;
        p.hp = Math.min(p.maxHp, p.hp + 20);
      } else {
        p.upgrades[stat]++;
      }
    } else if (msg.type === 'craft') {
      if (gameState !== 'playing') return;
      doCraft(p, String(msg.recipe || ''));
    } else if (msg.type === 'eat') {
      if (gameState !== 'playing') return;
      doEat(p, msg.item ? String(msg.item) : null);
    } else if (msg.type === 'place') {
      if (gameState !== 'playing') return;
      doPlace(p, Math.floor(Number(msg.tx)), Math.floor(Number(msg.ty)));
    }
  });

  ws.on('close', () => {
    players.delete(id);
    readySet.delete(id);
    playerMeleeLast.delete(id);
    if (id === hostId) hostId = players.size ? [...players.keys()][0] : null;
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
  const nx = (p.dirX / len) * PLAYER_SPEED * getSpeedMult(p) * dt;
  const ny = (p.dirY / len) * PLAYER_SPEED * getSpeedMult(p) * dt;
  const newX = p.x + nx, newY = p.y + ny;
  if (!isSolid(newX, p.y)) p.x = newX;
  if (!isSolid(p.x, newY)) p.y = newY;
}

function updateEnemies(dt, now) {
  for (const e of enemies.values()) {
    const cfg = ENEMY_TYPES[e.type];
    const aggroMemory = now < (e.aggroUntil || 0);

    let target = null, minD = Infinity;
    for (const p of players.values()) {
      const d = Math.hypot(p.x - e.x, p.y - e.y);
      if ((aggroMemory || d < ENEMY_AGGRO) && d < minD) {
        minD = d; target = p;
      }
    }

    if (!target) {
      if (e.type === 'wanderer') {
        if (now > (e.wanderUntil || 0)) {
          e.wanderAngle = Math.random() * Math.PI * 2;
          e.wanderUntil = now + 1500 + Math.random() * 2500;
        }
        const sp = cfg.speed;
        const nx = e.x + Math.cos(e.wanderAngle) * sp * dt;
        const ny = e.y + Math.sin(e.wanderAngle) * sp * dt;
        if (!isSolid(nx, e.y)) e.x = nx; else e.wanderAngle = Math.random() * Math.PI * 2;
        if (!isSolid(e.x, ny)) e.y = ny; else e.wanderAngle = Math.random() * Math.PI * 2;
      } else {
        const dx = e.homeX - e.x, dy = e.homeY - e.y;
        const dl = Math.hypot(dx, dy);
        if (dl > ENEMY_HOME_LEASH) {
          const nx = e.x + (dx / dl) * 40 * dt;
          const ny = e.y + (dy / dl) * 40 * dt;
          if (!isSolid(nx, e.y)) e.x = nx;
          if (!isSolid(e.x, ny)) e.y = ny;
        }
      }
      continue;
    }

    if (e.type === 'ranged') {
      if (minD < cfg.attackRange) {
        if (now - e.lastHit > cfg.attackCD) {
          e.lastHit = now;
          const a = Math.atan2(target.y - e.y, target.x - e.x);
          const pid = nextProjectileId++;
          projectiles.set(pid, {
            id: pid,
            x: e.x + Math.cos(a) * (e.radius + 4),
            y: e.y + Math.sin(a) * (e.radius + 4),
            startX: e.x, startY: e.y,
            vx: Math.cos(a) * cfg.projectileSpeed,
            vy: Math.sin(a) * cfg.projectileSpeed,
            ownerType: 'enemy', ownerId: e.id,
            ttl: 2, maxDist: cfg.attackRange + 60,
            damage: cfg.damage,
          });
        }
        continue;
      }
      const dx = target.x - e.x, dy = target.y - e.y;
      const l = Math.hypot(dx, dy) || 1;
      const nx = e.x + (dx / l) * cfg.speed * dt;
      const ny = e.y + (dy / l) * cfg.speed * dt;
      if (!isSolid(nx, e.y)) e.x = nx;
      if (!isSolid(e.x, ny)) e.y = ny;
      continue;
    }

    // melee / wanderer — контактный бой
    if (minD < e.radius + target.radius + 8) {
      if (now - e.lastHit > cfg.attackCD) {
        e.lastHit = now;
        target.hp -= cfg.damage;
        if (target.hp <= 0) {
          const s = findSpawn();
          target.x = s.x; target.y = s.y;
          target.hp = target.maxHp;
        }
      }
      continue;
    }
    const sp = (e.type === 'wanderer') ? cfg.chaseSpeed : cfg.speed;
    const dx = target.x - e.x, dy = target.y - e.y;
    const l = Math.hypot(dx, dy) || 1;
    const nx = e.x + (dx / l) * sp * dt;
    const ny = e.y + (dy / l) * sp * dt;
    if (!isSolid(nx, e.y)) e.x = nx;
    if (!isSolid(e.x, ny)) e.y = ny;
  }
}

function updateProjectiles(dt, now) {
  for (const [id, pr] of projectiles) {
    pr.x += pr.vx * dt;
    pr.y += pr.vy * dt;
    pr.ttl -= dt;

    const traveled = Math.hypot(pr.x - pr.startX, pr.y - pr.startY);
    if (pr.ttl <= 0 || traveled >= pr.maxDist || blocksProjectile(pr.x, pr.y)) {
      projectiles.delete(id);
      continue;
    }

    if (pr.ownerType === 'enemy') {
      let hit = false;
      for (const p of players.values()) {
        if (Math.hypot(pr.x - p.x, pr.y - p.y) < p.radius + PROJ_RADIUS) {
          p.hp -= pr.damage || 8;
          if (p.hp <= 0) {
            const s = findSpawn();
            p.x = s.x; p.y = s.y;
            p.hp = p.maxHp;
          }
          hit = true;
          break;
        }
      }
      if (hit) projectiles.delete(id);
    } else {
      let hit = false;
      for (const e of enemies.values()) {
        if (Math.hypot(pr.x - e.x, pr.y - e.y) < e.radius + PROJ_RADIUS) {
          e.hp -= pr.damage || PROJ_DAMAGE;
          e.aggroUntil = now + ENEMY_AGGRO_MEMORY;
          if (e.hp <= 0) {
            const cfg = ENEMY_TYPES[e.type];
            const killer = players.get(pr.ownerId);
            if (killer && Math.random() < LOOT_CHANCE) {
              addItem(killer, cfg.loot);
            }
            distributeXp(e.x, e.y, xpForEnemy(e), pr.ownerId);
            enemies.delete(e.id);
          }
          hit = true;
          break;
        }
      }
      if (hit) projectiles.delete(id);
    }
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
  updateProjectiles(dt, now);

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
  if (g < GROUP_MIN) {
    spawnEnemyGroup();
    if (g + 1 < GROUP_MIN) spawnEnemyGroup();
  }
}, 2500);

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
