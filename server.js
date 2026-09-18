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
const MAP_W = 600;
const MAP_H = 450;

// Типы поверхности
const T_GRASS = 0;
const T_STONE = 1;
const T_WATER = 2;
const T_FLOOR = 3;
const T_IRON = 4;
const T_COPPER = 5;
const T_COAL = 6;
const T_TIN = 7;
const T_FURNACE = 8;

// Рудные жилы: респавн через 2 минуты
const ORE_RESPAWN_MS = 120000;
const ORE_HP = 75;
const WATER_SLOW = 1.5;

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
for (let i = 0; i < 250; i++) {
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
for (let i = 0; i < 350; i++) {
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

// стены и скалы — больше скал
for (let i = 0; i < 1500; i++) {
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

// крупные скальные массивы
for (let i = 0; i < 250; i++) {
  const cx = 5 + Math.floor(Math.random() * (MAP_W - 10));
  const cy = 5 + Math.floor(Math.random() * (MAP_H - 10));
  const r = 2 + Math.floor(Math.random() * 4);
  for (let y = cy - r; y <= cy + r; y++) {
    for (let x = cx - r; x <= cx + r; x++) {
      if (x < 1 || y < 1 || x >= MAP_W - 1 || y >= MAP_H - 1) continue;
      if (map[y][x] !== T_GRASS && map[y][x] !== T_FLOOR) continue;
      const d = Math.hypot(x - cx, y - cy);
      if (d < r - Math.random()) map[y][x] = T_STONE;
    }
  }
}

// рудные жилы: железо, медь, уголь, олово
function placeOreVeins(tile, clusters, minSize, maxSize) {
  for (let i = 0; i < clusters; i++) {
    const cx = 3 + Math.floor(Math.random() * (MAP_W - 6));
    const cy = 3 + Math.floor(Math.random() * (MAP_H - 6));
    if (map[cy][cx] !== T_GRASS && map[cy][cx] !== T_FLOOR && map[cy][cx] !== T_STONE) continue;
    const want = minSize + Math.floor(Math.random() * (maxSize - minSize + 1));
    let placed = 0;
    for (let k = 0; k < want * 6 && placed < want; k++) {
      const x = cx + Math.floor((Math.random() - 0.5) * 7);
      const y = cy + Math.floor((Math.random() - 0.5) * 7);
      if (x < 1 || y < 1 || x >= MAP_W - 1 || y >= MAP_H - 1) continue;
      if (map[y][x] !== T_GRASS && map[y][x] !== T_FLOOR && map[y][x] !== T_STONE) continue;
      map[y][x] = tile;
      placed++;
    }
  }
}
placeOreVeins(T_IRON, 180, 3, 7);
placeOreVeins(T_COPPER, 180, 3, 7);
placeOreVeins(T_COAL, 150, 3, 6);
placeOreVeins(T_TIN, 150, 3, 6);

const wallHP = new Map();
const WALL_HP = 50;
// очередь восстановления руд: {tx, ty, tile, at}
const oreRespawn = [];

function isOre(t) {
  return t === T_IRON || t === T_COPPER || t === T_COAL || t === T_TIN;
}

function isSolid(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return true;
  const t = map[ty][tx];
  // по воде ходить можно, остальное твёрдое: камень, руды, печка
  return t === T_STONE || isOre(t) || t === T_FURNACE;
}
function blocksProjectile(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return true;
  const t = map[ty][tx];
  return t === T_STONE || isOre(t) || t === T_FURNACE;
}
function tileAt(x, y) {
  const tx = Math.floor(x / TILE);
  const ty = Math.floor(y / TILE);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return T_STONE;
  return map[ty][tx];
}
function speedFactorAt(x, y) {
  // в воде скорость в WATER_SLOW раз меньше
  return tileAt(x, y) === T_WATER ? 1 / WATER_SLOW : 1;
}
function restoreOres(now) {
  for (let i = oreRespawn.length - 1; i >= 0; i--) {
    const r = oreRespawn[i];
    if (now >= r.at) {
      // восстанавливаем только если клетка свободна (пол)
      if (map[r.ty][r.tx] === T_FLOOR) {
        map[r.ty][r.tx] = r.tile;
        wallHP.delete(r.tx + ',' + r.ty);
        broadcast({ type: 'tileChange', tx: r.tx, ty: r.ty, tile: r.tile });
      }
      oreRespawn.splice(i, 1);
    }
  }
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

const ENEMY_LIMIT = 300;
const GROUP_MIN = 30, GROUP_MAX = 50;
const GROUP_SIZE_MIN = 3, GROUP_SIZE_MAX = 6;
const GROUP_SPAWN_DIST = 400;

const PROJ_SPEED = 500;
const PROJ_RADIUS = 5;
const PROJ_DAMAGE = 25;
const PROJ_TTL = 1.5;
const PROJ_MAX_DIST = 400;
// пули появляются ближе к игроку в 2 раза
const PROJ_SPAWN_DIV = 2;

// патроны и перезарядка игрока
const AMMO_MAX = 10;
const RELOAD_MS = 3000;
// интервалы выстрелов по модификаторам
const ATTACK_CD = { normal: 200, shotgun: 1000, rapid: 150 };
const SHOTGUN_PELLETS = 5;
const SHOTGUN_SPREAD = 0.14;
const ENEMY_SHOTGUN_PELLETS = 6;
const ENEMY_SHOTGUN_SPREAD = 0.12;
const playerAttackLast = new Map();

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
  iron_ore: { name: 'Железная руда', color: '#bdc3c7' },
  copper_ore: { name: 'Медная руда', color: '#b87333' },
  tin_ore: { name: 'Оловянная руда', color: '#aab7b8' },
  coal: { name: 'Уголь', color: '#2c3e50' },
  iron_ingot: { name: 'Железный слиток', color: '#ecf0f1' },
  copper_ingot: { name: 'Медный слиток', color: '#e67e22' },
  tin_ingot: { name: 'Оловянный слиток', color: '#d5dbdb' },
  furnace: { name: 'Печь', color: '#7e5109' },
};
const TILE_TO_ITEM = {
  [T_STONE]: 'stone',
  [T_FLOOR]: 'floor',
  [T_GRASS]: 'grass',
  [T_WATER]: 'water',
  [T_IRON]: 'iron_ore',
  [T_COPPER]: 'copper_ore',
  [T_COAL]: 'coal',
  [T_TIN]: 'tin_ore',
};

function addItem(player, itemId) {
  if (!player.inventory) player.inventory = {};
  player.inventory[itemId] = (player.inventory[itemId] || 0) + 1;
}

// ---------- крафт ----------
const RECIPES = {
  brick: { out: 'brick', need: { stone: 2 }, alt: { socks: 3 } },
  medkit: { out: 'medkit', need: { cheese: 2, kuraga: 1 } },
  furnace: { out: 'furnace', need: { brick: 10 } },
};
const EAT_HP = { medkit: 60, cheese: 12, kuraga: 8 };
const PLACE_RANGE = 130;
const FURNACE_RANGE = 160;
// плавка: время в мс, 1 уголь = 4 руды
const SMELT_TIME = { tin_ore: 3000, copper_ore: 4000, iron_ore: 5000 };
const SMELT_OUT = { tin_ore: 'tin_ingot', copper_ore: 'copper_ingot', iron_ore: 'iron_ingot' };
const COAL_CHARGES = 4;

const furnaces = new Map();
let nextFurnaceId = 1;
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
function furnaceCenter(f) {
  return { x: f.tx * TILE + TILE, y: f.ty * TILE + TILE };
}
function doPlaceFurnace(p, tx, ty) {
  if (!p.inventory || (p.inventory.furnace || 0) <= 0) return;
  if (tx < 1 || ty < 1 || tx + 1 >= MAP_W - 1 || ty + 1 >= MAP_H - 1) return;
  // площадка 2x2 должна быть свободной (трава/пол)
  for (let dy = 0; dy < 2; dy++) {
    for (let dx = 0; dx < 2; dx++) {
      const t = map[ty + dy][tx + dx];
      if (t !== T_GRASS && t !== T_FLOOR) return;
    }
  }
  const c = { x: tx * TILE + TILE, y: ty * TILE + TILE };
  if (Math.hypot(p.x - c.x, p.y - c.y) > PLACE_RANGE + TILE) return;
  for (const o of players.values()) if (Math.hypot(o.x - c.x, o.y - c.y) < 50) return;
  p.inventory.furnace--; if (p.inventory.furnace <= 0) delete p.inventory.furnace;
  const id = nextFurnaceId++;
  const f = {
    id, tx, ty,
    coal: 0, charges: 0,
    ores: { iron_ore: 0, copper_ore: 0, tin_ore: 0 },
    ingots: { iron_ingot: 0, copper_ingot: 0, tin_ingot: 0 },
    smelting: null,
  };
  furnaces.set(id, f);
  for (let dy = 0; dy < 2; dy++) {
    for (let dx = 0; dx < 2; dx++) {
      map[ty + dy][tx + dx] = T_FURNACE;
      broadcast({ type: 'tileChange', tx: tx + dx, ty: ty + dy, tile: T_FURNACE });
    }
  }
}
function doFurnacePut(p, furnaceId, item, count) {
  const f = furnaces.get(Number(furnaceId));
  if (!f) return;
  const c = furnaceCenter(f);
  if (Math.hypot(p.x - c.x, p.y - c.y) > FURNACE_RANGE) return;
  const id = String(item || '');
  const n = Math.max(1, Math.min(64, Math.floor(Number(count) || 1)));
  if ((p.inventory[id] || 0) < 1) return;
  const take = Math.min(n, p.inventory[id]);
  if (id === 'coal') {
    p.inventory[id] -= take; if (p.inventory[id] <= 0) delete p.inventory[id];
    f.coal += take;
  } else if (id === 'iron_ore' || id === 'copper_ore' || id === 'tin_ore') {
    p.inventory[id] -= take; if (p.inventory[id] <= 0) delete p.inventory[id];
    f.ores[id] += take;
  }
}
function doFurnaceTake(p, furnaceId) {
  const f = furnaces.get(Number(furnaceId));
  if (!f) return;
  const c = furnaceCenter(f);
  if (Math.hypot(p.x - c.x, p.y - c.y) > FURNACE_RANGE) return;
  if (!p.inventory) p.inventory = {};
  for (const k of Object.keys(f.ingots)) {
    const n = f.ingots[k] || 0;
    if (n > 0) {
      p.inventory[k] = (p.inventory[k] || 0) + n;
      f.ingots[k] = 0;
    }
  }
}
function pickNextOre(f) {
  // порядок: олово, медь, железо — быстрые первыми
  if (f.ores.tin_ore > 0) return 'tin_ore';
  if (f.ores.copper_ore > 0) return 'copper_ore';
  if (f.ores.iron_ore > 0) return 'iron_ore';
  return null;
}
function updateFurnaces(dtMs) {
  for (const f of furnaces.values()) {
    // идёт плавка — тикаем
    if (f.smelting) {
      f.smelting.remaining -= dtMs;
      if (f.smelting.remaining <= 0) {
        const out = SMELT_OUT[f.smelting.type];
        if (out) f.ingots[out] = (f.ingots[out] || 0) + 1;
        f.smelting = null;
      } else {
        continue;
      }
    }
    // простаивает — пробуем запустить новую
    if (!f.smelting) {
      if (f.charges <= 0) {
        if (f.coal > 0) {
          f.coal--;
          f.charges = COAL_CHARGES;
        } else {
          continue;
        }
      }
      const next = pickNextOre(f);
      if (!next) continue;
      f.ores[next]--;
      f.charges--;
      f.smelting = { type: next, remaining: SMELT_TIME[next], total: SMELT_TIME[next] };
    }
  }
}
function clearFurnacesToFloor() {
  for (const f of furnaces.values()) {
    for (let dy = 0; dy < 2; dy++) {
      for (let dx = 0; dx < 2; dx++) {
        const tx = f.tx + dx, ty = f.ty + dy;
        if (map[ty] && map[ty][tx] === T_FURNACE) {
          map[ty][tx] = T_FLOOR;
          broadcast({ type: 'tileChange', tx, ty, tile: T_FLOOR });
        }
      }
    }
  }
  furnaces.clear();
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
  if (enemies.size >= ENEMY_LIMIT) return false;
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
  oreRespawn.length = 0;
  // печки с прошлой игры убираем в пол
  clearFurnacesToFloor();
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
    p.shotMod = null;
    p.ammo = AMMO_MAX;
    p.maxAmmo = AMMO_MAX;
    p.reloadingUntil = 0;
    p.god = false;
    p.adminDamage = 1;
    p.adminSpeed = 1;
    playerAttackLast.delete(p.id);
  }
}

// ---------- прогрессия ----------
function getDamageMult(p) {
  return (1 + 0.10 * (p.upgrades ? p.upgrades.damage : 0)) * (p.adminDamage || 1);
}
function getSpeedMult(p) {
  return (1 + 0.05 * (p.upgrades ? p.upgrades.speed : 0)) * (p.adminSpeed || 1);
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
    furnaces: [...furnaces.values()],
  });
}

// ---------- выстрел игрока: патроны, перезарядка, модификаторы ----------
function attackCooldown(p) {
  if (p.shotMod === 'shotgun') return ATTACK_CD.shotgun;
  if (p.shotMod === 'rapid') return ATTACK_CD.rapid;
  return ATTACK_CD.normal;
}
function doPlayerAttack(p, id, angle, now) {
  if (p.maxAmmo == null) { p.maxAmmo = AMMO_MAX; p.ammo = AMMO_MAX; }
  if (p.reloadingUntil && now < p.reloadingUntil) return;
  if (p.reloadingUntil && now >= p.reloadingUntil) {
    p.ammo = p.maxAmmo;
    p.reloadingUntil = 0;
  }
  if ((p.ammo || 0) <= 0) {
    p.reloadingUntil = now + RELOAD_MS;
    return;
  }
  const last = playerAttackLast.get(id) || 0;
  if (now - last < attackCooldown(p)) return;
  playerAttackLast.set(id, now);
  p.ammo--;
  if (p.ammo <= 0) p.reloadingUntil = now + RELOAD_MS;
  const off = (p.radius + 4) / PROJ_SPAWN_DIV;
  const dmg = Math.round(PROJ_DAMAGE * getDamageMult(p));
  const fire = (a) => {
    const pid = nextProjectileId++;
    const sx = p.x + Math.cos(a) * off;
    const sy = p.y + Math.sin(a) * off;
    projectiles.set(pid, {
      id: pid, x: sx, y: sy,
      startX: sx, startY: sy,
      vx: Math.cos(a) * PROJ_SPEED,
      vy: Math.sin(a) * PROJ_SPEED,
      ownerType: 'player',
      ownerId: id, ttl: PROJ_TTL,
      maxDist: PROJ_MAX_DIST,
      damage: dmg,
    });
  };
  if (p.shotMod === 'shotgun') {
    for (let i = 0; i < SHOTGUN_PELLETS; i++) {
      fire(angle + (i - (SHOTGUN_PELLETS - 1) / 2) * SHOTGUN_SPREAD);
    }
  } else {
    fire(angle);
  }
}

// ---------- удар по стене и руде ----------
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
    const t = map[ty][tx];
    if (t !== T_STONE && !isOre(t)) continue;

    const key = tx + ',' + ty;
    const maxHp = isOre(t) ? ORE_HP : WALL_HP;
    const cur = wallHP.has(key) ? wallHP.get(key) : maxHp;
    const next = cur - MELEE_DAMAGE;
    if (next <= 0) {
      wallHP.delete(key);
      if (isOre(t)) {
        // руда падает в инвентарь, жила восстановится через 2 минуты
        addItem(p, TILE_TO_ITEM[t]);
        if (Math.random() < 0.35) addItem(p, TILE_TO_ITEM[t]);
        map[ty][tx] = T_FLOOR;
        oreRespawn.push({ tx, ty, tile: t, at: Date.now() + ORE_RESPAWN_MS });
        broadcast({ type: 'tileChange', tx, ty, tile: T_FLOOR });
      } else {
        map[ty][tx] = T_FLOOR;
        addItem(p, TILE_TO_ITEM[T_STONE]);
        broadcast({ type: 'tileChange', tx, ty, tile: T_FLOOR });
      }
    } else {
      wallHP.set(key, next);
      broadcast({ type: 'tileChange', tx, ty, tile: t, hp: next });
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
    shotMod: null,
    ammo: AMMO_MAX, maxAmmo: AMMO_MAX, reloadingUntil: 0,
    god: false, adminDamage: 1, adminSpeed: 1,
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
    furnaces: [...furnaces.values()],
    items: ITEMS,
  }));

  if (gameState === 'playing') {
    broadcast({ type: 'state',
      players: [...players.values()],
      enemies: [...enemies.values()],
      projectiles: [...projectiles.values()],
      furnaces: [...furnaces.values()],
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
      clearFurnacesToFloor();
      broadcastLobby();
    } else if (msg.type === 'move') {
      if (gameState !== 'playing') return;
      p.dirX = Number(msg.dx) || 0;
      p.dirY = Number(msg.dy) || 0;
    } else if (msg.type === 'attack') {
      if (gameState !== 'playing') return;
      doPlayerAttack(p, id, Number(msg.angle) || 0, Date.now());
    } else if (msg.type === 'melee') {
      if (gameState !== 'playing') return;
      meleeStrike(p, Number(msg.angle) || 0);
    } else if (msg.type === 'chooseMod') {
      if (gameState !== 'playing') return;
      if (p.level < 10 || p.shotMod) return;
      const m = String(msg.mod || '');
      if (m !== 'shotgun' && m !== 'rapid') return;
      p.shotMod = m;
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
    } else if (msg.type === 'placeFurnace') {
      if (gameState !== 'playing') return;
      doPlaceFurnace(p, Math.floor(Number(msg.tx)), Math.floor(Number(msg.ty)));
    } else if (msg.type === 'furnacePut') {
      if (gameState !== 'playing') return;
      doFurnacePut(p, msg.furnaceId, msg.item, msg.count);
    } else if (msg.type === 'furnaceTake') {
      if (gameState !== 'playing') return;
      doFurnaceTake(p, msg.furnaceId);
    } else if (msg.type === 'adminSet') {
      // только хост: множители урона и скорости себе
      if (id !== hostId || gameState !== 'playing') return;
      if (msg.damage != null && msg.damage !== '') {
        const v = Number(msg.damage);
        if (v > 0 && v <= 20) p.adminDamage = v;
      }
      if (msg.speed != null && msg.speed !== '') {
        const v = Number(msg.speed);
        if (v > 0 && v <= 10) p.adminSpeed = v;
      }
    } else if (msg.type === 'adminLevel') {
      if (id !== hostId) return;
      const lv = Math.max(1, Math.min(50, Math.floor(Number(msg.level) || 1)));
      if (lv > p.level) {
        p.points += lv - p.level;
        p.level = lv;
      } else {
        p.level = lv;
      }
      p.xp = 0;
      p.xpNext = xpForLevel(p.level);
      broadcast({ type: 'levelUp', id: p.id, level: p.level, points: p.points, xpNext: p.xpNext });
    } else if (msg.type === 'adminGod') {
      if (id !== hostId) return;
      p.god = !!msg.on;
      if (p.god) p.hp = p.maxHp;
    } else if (msg.type === 'adminGive') {
      if (id !== hostId || gameState !== 'playing') return;
      const item = String(msg.item || '');
      if (!ITEMS[item]) return;
      const n = Math.max(1, Math.min(99, Math.floor(Number(msg.count) || 1)));
      if (!p.inventory) p.inventory = {};
      p.inventory[item] = (p.inventory[item] || 0) + n;
    } else if (msg.type === 'adminSpawn') {
      if (id !== hostId || gameState !== 'playing') return;
      const type = String(msg.enemyType || 'melee');
      if (!ENEMY_TYPES[type]) return;
      const n = Math.max(1, Math.min(50, Math.floor(Number(msg.count) || 1)));
      for (let i = 0; i < n; i++) {
        if (enemies.size >= ENEMY_LIMIT + 100) break;
        const a = Math.random() * Math.PI * 2;
        const r = 80 + Math.random() * 120;
        const ex = p.x + Math.cos(a) * r;
        const ey = p.y + Math.sin(a) * r;
        if (isSolid(ex, ey)) continue;
        const e = makeEnemy(type, ex, ey);
        enemies.set(e.id, e);
      }
    }
  });

  ws.on('close', () => {
    players.delete(id);
    readySet.delete(id);
    playerMeleeLast.delete(id);
    playerAttackLast.delete(id);
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
  const slow = speedFactorAt(p.x, p.y);
  const sp = PLAYER_SPEED * getSpeedMult(p) * slow;
  const nx = (p.dirX / len) * sp * dt;
  const ny = (p.dirY / len) * sp * dt;
  const newX = p.x + nx, newY = p.y + ny;
  if (!isSolid(newX, p.y)) p.x = newX;
  if (!isSolid(p.x, newY)) p.y = newY;
}

function updateEnemies(dt, now) {
  for (const e of enemies.values()) {
    const cfg = ENEMY_TYPES[e.type];
    const aggroMemory = now < (e.aggroUntil || 0);
    const slow = speedFactorAt(e.x, e.y);

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
        const sp = cfg.speed * slow;
        const nx = e.x + Math.cos(e.wanderAngle) * sp * dt;
        const ny = e.y + Math.sin(e.wanderAngle) * sp * dt;
        if (!isSolid(nx, e.y)) e.x = nx; else e.wanderAngle = Math.random() * Math.PI * 2;
        if (!isSolid(e.x, ny)) e.y = ny; else e.wanderAngle = Math.random() * Math.PI * 2;
      } else {
        const dx = e.homeX - e.x, dy = e.homeY - e.y;
        const dl = Math.hypot(dx, dy);
        if (dl > ENEMY_HOME_LEASH) {
          const nx = e.x + (dx / dl) * 40 * slow * dt;
          const ny = e.y + (dy / dl) * 40 * slow * dt;
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
          // дальник бьёт дробью: 6 пуль веером
          for (let i = 0; i < ENEMY_SHOTGUN_PELLETS; i++) {
            const sa = a + (i - (ENEMY_SHOTGUN_PELLETS - 1) / 2) * ENEMY_SHOTGUN_SPREAD;
            const pid = nextProjectileId++;
            projectiles.set(pid, {
              id: pid,
              x: e.x + Math.cos(sa) * (e.radius + 4),
              y: e.y + Math.sin(sa) * (e.radius + 4),
              startX: e.x, startY: e.y,
              vx: Math.cos(sa) * cfg.projectileSpeed,
              vy: Math.sin(sa) * cfg.projectileSpeed,
              ownerType: 'enemy', ownerId: e.id,
              ttl: 2, maxDist: cfg.attackRange + 60,
              damage: cfg.damage,
            });
          }
        }
        continue;
      }
      const dx = target.x - e.x, dy = target.y - e.y;
      const l = Math.hypot(dx, dy) || 1;
      const nx = e.x + (dx / l) * cfg.speed * slow * dt;
      const ny = e.y + (dy / l) * cfg.speed * slow * dt;
      if (!isSolid(nx, e.y)) e.x = nx;
      if (!isSolid(e.x, ny)) e.y = ny;
      continue;
    }

    // melee / wanderer — контактный бой
    if (minD < e.radius + target.radius + 8) {
      if (now - e.lastHit > cfg.attackCD) {
        e.lastHit = now;
        if (!target.god) target.hp -= cfg.damage;
        if (target.hp <= 0 && !target.god) {
          const s = findSpawn();
          target.x = s.x; target.y = s.y;
          target.hp = target.maxHp;
        }
      }
      continue;
    }
    const sp = ((e.type === 'wanderer') ? cfg.chaseSpeed : cfg.speed) * slow;
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
          if (!p.god) p.hp -= pr.damage || 8;
          if (p.hp <= 0 && !p.god) {
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
  for (const p of players.values()) {
    movePlayer(p, dt);
    // конец перезарядки — вернуть полный магазин
    if (p.reloadingUntil && now >= p.reloadingUntil) {
      p.ammo = p.maxAmmo || AMMO_MAX;
      p.reloadingUntil = 0;
    }
  }
  updateEnemies(dt, now);
  updateProjectiles(dt, now);
  updateFurnaces(dt * 1000);
  restoreOres(now);

  broadcast({
    type: 'state',
    players: [...players.values()],
    enemies: [...enemies.values()],
    projectiles: [...projectiles.values()],
    furnaces: [...furnaces.values()],
  });
}, 50);

setInterval(() => {
  if (gameState !== 'playing' || players.size === 0) return;
  if (enemies.size >= ENEMY_LIMIT) return;
  const g = countGroups();
  if (g < GROUP_MIN) {
    // ускоренный спавн: до 3 групп за тик
    spawnEnemyGroup();
    spawnEnemyGroup();
    if (g + 2 < GROUP_MIN) spawnEnemyGroup();
  } else if (enemies.size < ENEMY_LIMIT - 10) {
    spawnEnemyGroup();
  }
}, 1000);

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
