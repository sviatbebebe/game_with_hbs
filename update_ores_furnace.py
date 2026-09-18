#!/usr/bin/env python3
"""update_ores_furnace: руды, печки, карта x3."""
import argparse, shutil, sys
from pathlib import Path
FILES = {}
FILES['server.js'] = r'''import http from 'node:http';
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
'''
FILES['public/index.html'] = r'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>rpg-radmin</title>
<style>
  html, body { margin: 0; padding: 0; background: #111; color: #eee;
               overflow: hidden; height: 100%; font-family: monospace; }
  canvas { display: block; }
  #lobby {
    position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
    background: #111;
  }
  .card {
    width: 420px; max-width: 92vw; background: #1a1a1a; border: 1px solid #333;
    border-radius: 10px; padding: 20px;
  }
  .card h1 { margin: 0 0 12px; font-size: 18px; color: #eee; }
  .row { display: flex; gap: 8px; margin-bottom: 12px; }
  input[type="text"] {
    flex: 1; padding: 8px 10px; background: #222; color: #eee;
    border: 1px solid #333; border-radius: 6px; outline: none;
    font-family: inherit;
  }
  button {
    padding: 8px 12px; background: #2c3e50; color: #eee;
    border: 1px solid #34495e; border-radius: 6px; cursor: pointer;
    font-family: inherit;
  }
  button:hover { background: #34495e; }
  button.primary { background: #2ecc71; border-color: #27ae60; color: #111; font-weight: bold; }
  button.primary:hover { background: #27ae60; }
  button.ready-on { background: #27ae60; border-color: #1e8449; color: #fff; }
  #playersList { list-style: none; padding: 0; margin: 8px 0 16px; }
  #playersList li {
    padding: 6px 8px; border-bottom: 1px solid #222; display: flex;
    justify-content: space-between;
  }
  #playersList li .badge {
    font-size: 11px; padding: 1px 6px; border-radius: 4px; background: #333; color: #bbb;
  }
  #playersList li .badge.host { background: #f1c40f; color: #111; }
  #playersList li .badge.ready { background: #2ecc71; color: #111; }
  #hint { font-size: 12px; color: #777; margin-top: 10px; }

  #gameUI { display: none; }
  #hud {
    position: fixed; top: 10px; left: 10px; font-size: 14px; pointer-events: none;
    text-shadow: 0 1px 2px #000;
  }
  #controls {
    position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%);
    font-size: 12px; color: #888; pointer-events: none;
    background: rgba(0,0,0,0.5); padding: 4px 10px; border-radius: 6px;
    white-space: nowrap; max-width: 95vw; overflow: hidden; text-overflow: ellipsis;
  }
</style>
</head>
<body>

<div id="lobby">
  <div class="card">
    <h1>Лобби</h1>
    <div class="row">
      <input id="nameInput" type="text" placeholder="Ваше имя" maxlength="20">
      <button id="nameBtn">ОК</button>
    </div>
    <ul id="playersList"></ul>
    <div class="row">
      <button id="readyBtn">Готов</button>
      <button id="startBtn" class="primary" style="display:none">Начать игру</button>
    </div>
    <div id="hint">RadminVPN: друзья открывают ваш Radmin-IP в браузере.</div>
  </div>
</div>

<div id="gameUI">
  <canvas id="game"></canvas>
  <div id="hud"></div>
  <div id="controls">WASD — движение, ЛКМ — выстрел, ПКМ — руда/стена, F+ЛКМ — стена, G+ЛКМ — печь 2x2, E — съесть/печка, С — крафт, P — админка</div>
</div>

<script type="module" src="/js/main.js"></script>
<script type="module" src="/js/spend-ui.js"></script>
<script type="module" src="/js/craft-ui.js"></script>
<script type="module" src="/js/furnace-ui.js"></script>
<script type="module" src="/js/mod-ui.js"></script>
<script type="module" src="/js/admin-ui.js"></script>
</body>
</html>
'''
FILES['public/js/main.js'] = r'''import { Net } from './net.js';
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
'''
FILES['public/js/net.js'] = r'''export class Net {
  constructor() {
    this.id = null;
    this.hostId = null;
    this.gameState = 'lobby';
    this.players = new Map();
    this.enemies = new Map();
    this.projectiles = new Map();
    this.furnaces = new Map();
    this.map = null;
    this.items = {};
    this.ws = null;
    this.handlers = {};
    // время снапшотов для интерполяции
    this.lastStateAt = 0;
    this.stateInterval = 63;
  }

  connect(url) {
    return new Promise((resolve) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch { return; }
        this._handle(msg);
        if (msg.type === 'init') resolve();
      };
    });
  }

  on(type, fn) { (this.handlers[type] ||= []).push(fn); }
  emit(type, data) { (this.handlers[type] || []).forEach(fn => fn(data)); }

  _handle(msg) {
    if (msg.type === 'levelUp') { this.emit('levelUp', msg); return; }
    if (msg.type === 'init') {
      this.id = msg.id;
      this.hostId = msg.hostId;
      this.gameState = msg.gameState;
      this.map = msg.map;
      this.items = msg.items || {};
      this.players.clear(); msg.players.forEach(p => this.players.set(p.id, p));
      this.enemies.clear(); msg.enemies.forEach(e => this.enemies.set(e.id, e));
      this.projectiles.clear(); msg.projectiles.forEach(p => this.projectiles.set(p.id, p));
      this.furnaces.clear(); (msg.furnaces || []).forEach(f => this.furnaces.set(f.id, f));
      this.emit('init', msg);
    } else if (msg.type === 'lobby') {
      this.hostId = msg.hostId;
      this.gameState = 'lobby';
      const byId = new Map(msg.players.map(p => [p.id, p]));
      for (const [id, p] of [...this.players]) {
        const l = byId.get(id);
        if (l) { p.name = l.name; p.ready = l.ready; }
        else this.players.delete(id);
      }
      for (const l of msg.players) {
        if (!this.players.has(l.id)) {
          this.players.set(l.id, { id: l.id, name: l.name, ready: l.ready,
            x: 0, y: 0, radius: 14, hp: 100, maxHp: 100, inventory: {} });
        }
      }
      this.emit('lobby', msg);
    } else if (msg.type === 'started') {
      this.gameState = 'playing';
      this.emit('started');
    } else if (msg.type === 'join') {
      this.players.set(msg.player.id, msg.player);
    } else if (msg.type === 'leave') {
      this.players.delete(msg.id);
    } else if (msg.type === 'tileChange') {
      if (this.map && this.map.tiles[msg.ty]) {
        this.map.tiles[msg.ty][msg.tx] = msg.tile;
      }
      this.emit('tileChange', msg);
    } else if (msg.type === 'state') {
      this.gameState = 'playing';
      const now = performance.now();
      if (this.lastStateAt) { this.stateInterval = now - this.lastStateAt; }
      this.lastStateAt = now;
      const merge = (map, arr) => {
        const seen = new Set();
        arr.forEach(o => {
          seen.add(o.id);
          const ex = map.get(o.id);
          if (ex) { ex.px = ex.x; ex.py = ex.y; Object.assign(ex, o); }
          else map.set(o.id, Object.assign({ px: o.x, py: o.y }, o));
        });
        for (const k of [...map.keys()]) if (!seen.has(k)) map.delete(k);
      };
      merge(this.players, msg.players);
      merge(this.enemies, msg.enemies);
      merge(this.projectiles, msg.projectiles);
      // печки не интерполируем, просто заменяем
      if (msg.furnaces) {
        const seen = new Set();
        msg.furnaces.forEach(f => {
          seen.add(f.id);
          const ex = this.furnaces.get(f.id);
          if (ex) Object.assign(ex, f);
          else this.furnaces.set(f.id, f);
        });
        for (const k of [...this.furnaces.keys()]) if (!seen.has(k)) this.furnaces.delete(k);
      }
      this.emit('state', msg);
    }
  }

  getSelf() { return this.id != null ? this.players.get(this.id) : null; }

  _send(o) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(o)); }
  setName(name) { this._send({ type: 'setName', name }); }
  toggleReady() { this._send({ type: 'ready' }); }
  startGame() { this._send({ type: 'start' }); }
  backToLobby() { this._send({ type: 'backToLobby' }); }
  sendMove(dx, dy) { this._send({ type: 'move', dx, dy }); }
  sendAttack(angle) { this._send({ type: 'attack', angle }); }
  sendMelee(angle) { this._send({ type: 'melee', angle }); }
  sendSpendPoint(stat) { this._send({ type: 'spendPoint', stat }); }
  sendCraft(recipe) { this._send({ type: 'craft', recipe }); }
  sendEat(item) { if (item) this._send({ type: 'eat', item }); else this._send({ type: 'eat' }); }
  sendPlace(tx, ty) { this._send({ type: 'place', tx, ty }); }
  sendPlaceFurnace(tx, ty) { this._send({ type: 'placeFurnace', tx, ty }); }
  sendFurnacePut(furnaceId, item, count) { this._send({ type: 'furnacePut', furnaceId, item, count }); }
  sendFurnaceTake(furnaceId) { this._send({ type: 'furnaceTake', furnaceId }); }
  sendChooseMod(mod) { this._send({ type: 'chooseMod', mod }); }
  sendAdminSet(damage, speed) { this._send({ type: 'adminSet', damage, speed }); }
  sendAdminLevel(level) { this._send({ type: 'adminLevel', level }); }
  sendAdminGod(on) { this._send({ type: 'adminGod', on }); }
  sendAdminGive(item, count) { this._send({ type: 'adminGive', item, count }); }
  sendAdminSpawn(enemyType, count) { this._send({ type: 'adminSpawn', enemyType, count }); }
  getFurnaces() { return this.furnaces; }
}
'''
FILES['public/js/fx.js'] = r'''// Минимальные спецэффекты выстрелов: вспышка у дула и искры попаданий.
// Без аллокаций в горячем пути сверх меры, лимит частиц.
export class Fx {
  constructor() {
    this.parts = [];
    this.max = 400;
  }
  _push(p) {
    if (this.parts.length >= this.max) this.parts.shift();
    this.parts.push(p);
  }
  // вспышка выстрела: несколько искр вдоль угла + короткая вспышка
  muzzle(x, y, angle, color, big) {
    const n = big ? 7 : 4;
    for (let i = 0; i < n; i++) {
      const sp = 120 + Math.random() * (big ? 260 : 160);
      const a = angle + (Math.random() - 0.5) * 0.6;
      this._push({
        x, y,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
        life: 0, maxLife: 0.12 + Math.random() * 0.1,
        size: 2 + Math.random() * 2, color,
      });
    }
    this._push({ x, y, vx: 0, vy: 0, life: 0, maxLife: 0.08, size: big ? 12 : 8, color: '#fff', flash: true });
  }
  // попадание: радиальные искры
  impact(x, y, color) {
    for (let i = 0; i < 6; i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 60 + Math.random() * 160;
      this._push({
        x, y,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
        life: 0, maxLife: 0.2 + Math.random() * 0.15,
        size: 1.5 + Math.random() * 2, color,
      });
    }
  }
  update(dt) {
    const ps = this.parts;
    for (let i = ps.length - 1; i >= 0; i--) {
      const p = ps[i];
      p.life += dt;
      if (p.life >= p.maxLife) { ps.splice(i, 1); continue; }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.vx *= 0.9;
      p.vy *= 0.9;
    }
  }
  draw(ctx, ox, oy) {
    for (const p of this.parts) {
      const a = 1 - p.life / p.maxLife;
      ctx.globalAlpha = Math.max(0, a);
      ctx.fillStyle = p.color;
      const sx = p.x + ox, sy = p.y + oy;
      if (p.flash) {
        ctx.beginPath();
        ctx.arc(sx, sy, p.size * a, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillRect(sx - p.size / 2, sy - p.size / 2, p.size, p.size);
      }
    }
    ctx.globalAlpha = 1;
  }
}
'''
FILES['public/js/craft-ui.js'] = r'''// Окно крафта по центру экрана, клавиша С (KeyC)
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  // затемнение фона
  const overlay = document.createElement('div');
  overlay.id = 'craftOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '30';

  const win = document.createElement('div');
  win.style.width = '380px';
  win.style.maxWidth = '92vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #444';
  win.style.borderRadius = '10px';
  win.style.padding = '16px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';

  const title = document.createElement('div');
  title.style.display = 'flex';
  title.style.justifyContent = 'space-between';
  title.style.alignItems = 'center';
  title.style.marginBottom = '12px';
  const h = document.createElement('div');
  h.textContent = 'Крафт (С — закрыть)';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.style.background = '#333';
  closeBtn.style.color = '#eee';
  closeBtn.style.border = '1px solid #555';
  closeBtn.style.borderRadius = '6px';
  closeBtn.style.cursor = 'pointer';
  closeBtn.style.padding = '4px 10px';
  closeBtn.addEventListener('click', hide);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const invLine = document.createElement('div');
  invLine.id = 'craftInv';
  invLine.style.fontSize = '12px';
  invLine.style.color = '#aaa';
  invLine.style.marginBottom = '12px';
  win.appendChild(invLine);

  function mkRow(name, desc, onCraft) {
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.justifyContent = 'space-between';
    row.style.alignItems = 'center';
    row.style.gap = '8px';
    row.style.padding = '8px';
    row.style.marginBottom = '8px';
    row.style.background = '#222';
    row.style.border = '1px solid #333';
    row.style.borderRadius = '6px';
    const left = document.createElement('div');
    const t1 = document.createElement('div');
    t1.textContent = name;
    t1.style.fontSize = '14px';
    const t2 = document.createElement('div');
    t2.textContent = desc;
    t2.style.fontSize = '12px';
    t2.style.color = '#888';
    left.appendChild(t1);
    left.appendChild(t2);
    const b = document.createElement('button');
    b.textContent = 'Скрафтить';
    b.style.background = '#2ecc71';
    b.style.border = '1px solid #27ae60';
    b.style.color = '#111';
    b.style.fontWeight = 'bold';
    b.style.borderRadius = '6px';
    b.style.padding = '8px 12px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', onCraft);
    row.appendChild(left);
    row.appendChild(b);
    return row;
  }

  win.appendChild(mkRow('Кирпич', '2 камня или 3 носков', () => window.gameApi.sendCraft('brick')));
  win.appendChild(mkRow('Аптечка', '2 сыра + 1 курага', () => window.gameApi.sendCraft('medkit')));
  win.appendChild(mkRow('Печь', '10 кирпичей, ставится G+ЛКМ 2x2', () => window.gameApi.sendCraft('furnace')));

  const eatRow = document.createElement('div');
  eatRow.style.display = 'flex';
  eatRow.style.gap = '8px';
  eatRow.style.marginTop = '8px';
  function mkSmall(label, fn) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.flex = '1';
    b.style.background = '#2c3e50';
    b.style.color = '#eee';
    b.style.border = '1px solid #34495e';
    b.style.borderRadius = '6px';
    b.style.padding = '8px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', fn);
    return b;
  }
  eatRow.appendChild(mkSmall('Съесть (E)', () => window.gameApi.sendEat()));
  eatRow.appendChild(mkSmall('Кирпич-стена: F+ЛКМ', () => hide()));
  win.appendChild(eatRow);

  const hint = document.createElement('div');
  hint.style.fontSize = '11px';
  hint.style.color = '#666';
  hint.style.marginTop = '10px';
  hint.textContent = 'Печка: скрафти, встань рядом, G+ЛКМ — поставить. E рядом с печкой — открыть плавильню.';
  win.appendChild(hint);

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  function refreshInv() {
    const p = window.gameApi.getLocalPlayer();
    if (!p) { invLine.textContent = ''; return; }
    const inv = p.inventory || {};
    const parts = Object.entries(inv).map(([k, v]) => k + ': ' + v);
    invLine.textContent = parts.length ? 'Инвентарь: ' + parts.join(', ') : 'Инвентарь пуст';
  }

  function show() {
    overlay.style.display = 'flex';
    refreshInv();
  }
  function hide() {
    overlay.style.display = 'none';
  }
  function toggle() {
    if (overlay.style.display === 'none' || !overlay.style.display) show();
    else hide();
  }

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) hide();
  });
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyC' && !e.repeat) {
      // не открывать из лобби и из полей ввода
      if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
      toggle();
    }
    if (e.code === 'Escape') hide();
  });

  setInterval(() => {
    if (overlay.style.display === 'flex') refreshInv();
  }, 500);

  window.craftUi = { show, hide, toggle };
}

boot();
'''
FILES['public/js/furnace-ui.js'] = r'''// Интерфейс печки: E рядом с печкой открывает окно.
// Слоты: топливо (уголь), руды (железо/медь/олово), выход (слитки).
// Олово 3с, медь 4с, железо 5с, 1 уголь = 4 руды.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'furnaceOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '31';

  const win = document.createElement('div');
  win.style.width = '400px';
  win.style.maxWidth = '94vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #a05a00';
  win.style.borderRadius = '10px';
  win.style.padding = '16px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';

  const title = document.createElement('div');
  title.style.display = 'flex';
  title.style.justifyContent = 'space-between';
  title.style.alignItems = 'center';
  title.style.marginBottom = '10px';
  const h = document.createElement('div');
  h.id = 'furnaceTitle';
  h.textContent = 'Печь';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.style.background = '#333';
  closeBtn.style.color = '#eee';
  closeBtn.style.border = '1px solid #555';
  closeBtn.style.borderRadius = '6px';
  closeBtn.style.cursor = 'pointer';
  closeBtn.style.padding = '4px 10px';
  closeBtn.addEventListener('click', close);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const status = document.createElement('div');
  status.id = 'furnaceStatus';
  status.style.fontSize = '13px';
  status.style.marginBottom = '10px';
  status.style.whiteSpace = 'pre-line';
  win.appendChild(status);

  const barWrap = document.createElement('div');
  barWrap.style.height = '10px';
  barWrap.style.background = '#000';
  barWrap.style.border = '1px solid #444';
  barWrap.style.borderRadius = '4px';
  barWrap.style.marginBottom = '12px';
  const bar = document.createElement('div');
  bar.style.height = '100%';
  bar.style.width = '0%';
  bar.style.background = '#f39c12';
  barWrap.appendChild(bar);
  win.appendChild(barWrap);

  function mkBtn(label, fn) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.background = '#2c3e50';
    b.style.color = '#eee';
    b.style.border = '1px solid #34495e';
    b.style.borderRadius = '6px';
    b.style.padding = '7px 8px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.style.fontSize = '12px';
    b.addEventListener('click', fn);
    return b;
  }

  const grid = document.createElement('div');
  grid.style.display = 'flex';
  grid.style.flexDirection = 'column';
  grid.style.gap = '6px';

  const row1 = document.createElement('div');
  row1.style.display = 'flex';
  row1.style.gap = '6px';
  row1.appendChild(mkBtn('+1 уголь', () => put('coal', 1)));
  row1.appendChild(mkBtn('Весь уголь', () => putAll('coal')));
  grid.appendChild(row1);

  const row2 = document.createElement('div');
  row2.style.display = 'flex';
  row2.style.gap = '6px';
  row2.appendChild(mkBtn('+1 железо', () => put('iron_ore', 1)));
  row2.appendChild(mkBtn('+1 медь', () => put('copper_ore', 1)));
  row2.appendChild(mkBtn('+1 олово', () => put('tin_ore', 1)));
  grid.appendChild(row2);

  const row3 = document.createElement('div');
  row3.style.display = 'flex';
  row3.style.gap = '6px';
  row3.appendChild(mkBtn('Вся руда', putAllOres));
  const takeBtn = mkBtn('Забрать слитки', take);
  takeBtn.style.background = '#27ae60';
  takeBtn.style.borderColor = '#1e8449';
  takeBtn.style.color = '#fff';
  takeBtn.style.fontWeight = 'bold';
  row3.appendChild(takeBtn);
  grid.appendChild(row3);

  win.appendChild(grid);

  const hint = document.createElement('div');
  hint.style.fontSize = '11px';
  hint.style.color = '#888';
  hint.style.marginTop = '10px';
  hint.textContent = 'Олово 3с, медь 4с, железо 5с. 1 уголь = 4 руды. E или Esc — закрыть.';
  win.appendChild(hint);

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  let currentId = null;

  function getFurnace() {
    if (currentId == null) return null;
    const list = window.gameApi.getFurnaces();
    return list.find((f) => f.id === currentId) || null;
  }
  function put(item, count) {
    if (currentId == null) return;
    window.gameApi.sendFurnacePut(currentId, item, count);
  }
  function putAll(item) {
    const p = window.gameApi.getLocalPlayer();
    if (!p || !p.inventory) return;
    const n = p.inventory[item] || 0;
    if (n > 0) put(item, n);
  }
  function putAllOres() {
    const p = window.gameApi.getLocalPlayer();
    if (!p || !p.inventory) return;
    for (const k of ['iron_ore', 'copper_ore', 'tin_ore']) {
      const n = p.inventory[k] || 0;
      if (n > 0) window.gameApi.sendFurnacePut(currentId, k, n);
    }
  }
  function take() {
    if (currentId == null) return;
    window.gameApi.sendFurnaceTake(currentId);
  }
  function open(id) {
    currentId = id;
    overlay.style.display = 'flex';
    refresh();
  }
  function close() {
    overlay.style.display = 'none';
    currentId = null;
    window._furnaceClosedAt = Date.now();
  }
  function refresh() {
    const f = getFurnace();
    if (!f) {
      // печка пропала (выход в лобби)
      if (overlay.style.display === 'flex' && currentId != null) {
        status.textContent = 'Печь недоступна.';
      }
      return;
    }
    document.getElementById('furnaceTitle').textContent = 'Печь #' + f.id + ' (2x2)';
    const sm = f.smelting
      ? 'Плавится: ' + f.smelting.type + ' (' + Math.ceil(f.smelting.remaining / 1000) + 'с)'
      : 'Простаивает';
    status.textContent =
      'Уголь в печи: ' + (f.coal || 0) + '  |  Заряды: ' + (f.charges || 0) + '\n' +
      'Руда — железо: ' + (f.ores.iron_ore || 0) + ', медь: ' + (f.ores.copper_ore || 0) + ', олово: ' + (f.ores.tin_ore || 0) + '\n' +
      'Слитки — железо: ' + (f.ingots.iron_ingot || 0) + ', медь: ' + (f.ingots.copper_ingot || 0) + ', олово: ' + (f.ingots.tin_ingot || 0) + '\n' +
      sm;
    if (f.smelting && f.smelting.total) {
      const r = 1 - f.smelting.remaining / f.smelting.total;
      bar.style.width = (Math.max(0, Math.min(1, r)) * 100) + '%';
    } else {
      bar.style.width = '0%';
    }
  }

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });
  window.addEventListener('keydown', (e) => {
    if ((e.code === 'Escape' || e.code === 'KeyE') && overlay.style.display === 'flex' && !e.repeat) {
      // E закрывает только если окно уже открыто, чтобы не мешать поеданию
      if (e.code === 'Escape') close();
      else {
        // E при открытом окне — закрыть, а не открывать новое
        e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
        e.preventDefault();
        close();
      }
    }
  }, true);

  setInterval(() => {
    if (overlay.style.display === 'flex') refresh();
  }, 250);

  function isOpen() {
    return overlay.style.display === 'flex';
  }

  window.furnaceUi = { open, close, isOpen };
}

boot();
'''
FILES['public/js/mod-ui.js'] = r'''// Выбор модификатора выстрела на 10 уровне.
// Дробь x5: 5 пуль, интервал 1с. Скорострел: быстрый огонь с зажатой ЛКМ.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'modOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.6)';
  overlay.style.zIndex = '32';

  const win = document.createElement('div');
  win.style.width = '420px';
  win.style.maxWidth = '94vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #f1c40f';
  win.style.borderRadius = '10px';
  win.style.padding = '18px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';
  win.style.textAlign = 'center';

  const h = document.createElement('div');
  h.textContent = '10 уровень! Выбери модификатор выстрела';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  h.style.marginBottom = '6px';
  win.appendChild(h);

  const sub = document.createElement('div');
  sub.textContent = 'Выбор навсегда для этой игры. Магазин: 10 патронов, перезарядка 3с.';
  sub.style.fontSize = '12px';
  sub.style.color = '#888';
  sub.style.marginBottom = '14px';
  win.appendChild(sub);

  const row = document.createElement('div');
  row.style.display = 'flex';
  row.style.gap = '10px';

  function card(title, desc, mod, color) {
    const c = document.createElement('div');
    c.style.flex = '1';
    c.style.background = '#222';
    c.style.border = '1px solid #444';
    c.style.borderRadius = '8px';
    c.style.padding = '12px';
    const t = document.createElement('div');
    t.textContent = title;
    t.style.fontSize = '15px';
    t.style.fontWeight = 'bold';
    t.style.color = color;
    t.style.marginBottom = '6px';
    const d = document.createElement('div');
    d.textContent = desc;
    d.style.fontSize = '12px';
    d.style.color = '#aaa';
    d.style.marginBottom = '10px';
    d.style.whiteSpace = 'pre-line';
    const b = document.createElement('button');
    b.textContent = 'Выбрать';
    b.style.background = color;
    b.style.color = '#111';
    b.style.fontWeight = 'bold';
    b.style.border = 'none';
    b.style.borderRadius = '6px';
    b.style.padding = '8px 14px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', () => {
      window.gameApi.sendChooseMod(mod);
      hide();
    });
    c.appendChild(t);
    c.appendChild(d);
    c.appendChild(b);
    return c;
  }

  row.appendChild(card('Дробь x5', '5 пуль за выстрел\nинтервал 1 секунда', 'shotgun', '#f39c12'));
  row.appendChild(card('Скорострел', 'быстрый огонь\nстрельба с зажатой ЛКМ', 'rapid', '#2ecc71'));
  win.appendChild(row);
  overlay.appendChild(win);
  document.body.appendChild(overlay);

  let dismissed = false;
  function show() {
    if (dismissed) return;
    overlay.style.display = 'flex';
  }
  function hide() {
    overlay.style.display = 'none';
    dismissed = true;
  }

  setInterval(() => {
    const p = window.gameApi.getLocalPlayer();
    if (!p) return;
    if ((p.level || 1) >= 10 && !p.shotMod && !dismissed) {
      if (overlay.style.display !== 'flex') show();
    } else if (p.shotMod && overlay.style.display === 'flex') {
      hide();
    }
  }, 500);

  window.modUi = { show, hide };
}

boot();
'''
FILES['public/js/admin-ui.js'] = r'''// Панель админа (только хост, сервер проверяет).
// Клавиша P — открыть/закрыть. Урон, скорость, уровень, бессмертие, предметы, спавн.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'adminOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '33';

  const win = document.createElement('div');
  win.style.width = '400px';
  win.style.maxWidth = '94vw';
  win.style.maxHeight = '90vh';
  win.style.overflowY = 'auto';
  win.style.background = '#140f0f';
  win.style.border = '1px solid #e74c3c';
  win.style.borderRadius = '10px';
  win.style.padding = '16px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';

  const title = document.createElement('div');
  title.style.display = 'flex';
  title.style.justifyContent = 'space-between';
  title.style.alignItems = 'center';
  title.style.marginBottom = '10px';
  const h = document.createElement('div');
  h.textContent = 'Панель админа (P)';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  h.style.color = '#e74c3c';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.style.background = '#333';
  closeBtn.style.color = '#eee';
  closeBtn.style.border = '1px solid #555';
  closeBtn.style.borderRadius = '6px';
  closeBtn.style.cursor = 'pointer';
  closeBtn.style.padding = '4px 10px';
  closeBtn.addEventListener('click', hide);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const note = document.createElement('div');
  note.id = 'adminNote';
  note.style.fontSize = '12px';
  note.style.color = '#888';
  note.style.marginBottom = '10px';
  win.appendChild(note);

  function field(label, inputEl) {
    const wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.gap = '8px';
    wrap.style.alignItems = 'center';
    wrap.style.marginBottom = '8px';
    const l = document.createElement('div');
    l.textContent = label;
    l.style.flex = '0 0 130px';
    l.style.fontSize = '12px';
    inputEl.style.flex = '1';
    inputEl.style.background = '#222';
    inputEl.style.color = '#eee';
    inputEl.style.border = '1px solid #444';
    inputEl.style.borderRadius = '6px';
    inputEl.style.padding = '6px 8px';
    inputEl.style.fontFamily = 'monospace';
    wrap.appendChild(l);
    wrap.appendChild(inputEl);
    return wrap;
  }
  function mkBtn(label, fn, accent) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.background = accent ? '#e74c3c' : '#2c3e50';
    b.style.color = '#fff';
    b.style.border = '1px solid ' + (accent ? '#c0392b' : '#34495e');
    b.style.borderRadius = '6px';
    b.style.padding = '7px 10px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.style.fontSize = '12px';
    b.style.marginBottom = '8px';
    b.style.width = '100%';
    b.addEventListener('click', fn);
    return b;
  }

  const dmgInput = document.createElement('input');
  dmgInput.type = 'number'; dmgInput.min = '1'; dmgInput.max = '20'; dmgInput.step = '0.5'; dmgInput.value = '1';
  win.appendChild(field('Урон x (1-20)', dmgInput));
  const spdInput = document.createElement('input');
  spdInput.type = 'number'; spdInput.min = '1'; spdInput.max = '10'; spdInput.step = '0.5'; spdInput.value = '1';
  win.appendChild(field('Скорость x (1-10)', spdInput));
  win.appendChild(mkBtn('Применить урон/скорость', () => {
    window.gameApi.sendAdminSet(dmgInput.value, spdInput.value);
  }));

  const lvInput = document.createElement('input');
  lvInput.type = 'number'; lvInput.min = '1'; lvInput.max = '50'; lvInput.value = '10';
  win.appendChild(field('Уровень (1-50)', lvInput));
  win.appendChild(mkBtn('Выдать уровень', () => {
    window.gameApi.sendAdminLevel(lvInput.value);
  }));

  const godLabel = document.createElement('label');
  godLabel.style.display = 'flex';
  godLabel.style.gap = '8px';
  godLabel.style.alignItems = 'center';
  godLabel.style.fontSize = '13px';
  godLabel.style.marginBottom = '8px';
  const godBox = document.createElement('input');
  godBox.type = 'checkbox';
  godBox.addEventListener('change', () => window.gameApi.sendAdminGod(godBox.checked));
  godLabel.appendChild(godBox);
  const gt = document.createElement('span');
  gt.textContent = 'Бессмертие';
  godLabel.appendChild(gt);
  win.appendChild(godLabel);

  const itemSel = document.createElement('select');
  const countInput = document.createElement('input');
  countInput.type = 'number'; countInput.min = '1'; countInput.max = '99'; countInput.value = '10';
  countInput.style.maxWidth = '70px';
  const itemRow = document.createElement('div');
  itemRow.style.display = 'flex';
  itemRow.style.gap = '8px';
  itemRow.style.marginBottom = '8px';
  itemSel.style.flex = '1';
  itemSel.style.background = '#222';
  itemSel.style.color = '#eee';
  itemSel.style.border = '1px solid #444';
  itemSel.style.borderRadius = '6px';
  itemSel.style.padding = '6px 8px';
  itemSel.style.fontFamily = 'monospace';
  itemRow.appendChild(itemSel);
  itemRow.appendChild(countInput);
  win.appendChild(itemRow);
  win.appendChild(mkBtn('Выдать предмет', () => {
    window.gameApi.sendAdminGive(itemSel.value, countInput.value);
  }));

  const mobSel = document.createElement('select');
  mobSel.style.width = '100%';
  mobSel.style.background = '#222';
  mobSel.style.color = '#eee';
  mobSel.style.border = '1px solid #444';
  mobSel.style.borderRadius = '6px';
  mobSel.style.padding = '6px 8px';
  mobSel.style.fontFamily = 'monospace';
  mobSel.style.marginBottom = '8px';
  const mobCount = document.createElement('input');
  mobCount.type = 'number'; mobCount.min = '1'; mobCount.max = '50'; mobCount.value = '5';
  const mobRow = document.createElement('div');
  mobRow.style.display = 'flex';
  mobRow.style.gap = '8px';
  mobRow.style.marginBottom = '0';
  mobSel.style.flex = '1';
  mobCount.style.maxWidth = '70px';
  mobCount.style.background = '#222';
  mobCount.style.color = '#eee';
  mobCount.style.border = '1px solid #444';
  mobCount.style.borderRadius = '6px';
  mobCount.style.padding = '6px 8px';
  mobCount.style.fontFamily = 'monospace';
  mobRow.appendChild(mobSel);
  mobRow.appendChild(mobCount);
  win.appendChild(mobRow);
  for (const t of ['melee', 'ranged', 'wanderer']) {
    const o = document.createElement('option');
    o.value = t; o.textContent = t;
    mobSel.appendChild(o);
  }
  win.appendChild(mkBtn('Заспавнить врагов рядом', () => {
    window.gameApi.sendAdminSpawn(mobSel.value, mobCount.value);
  }, true));

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  // список предметов подтягиваем из init
  let itemsLoaded = false;
  function loadItems() {
    if (itemsLoaded) return;
    const net = window.gameApi.getNet ? window.gameApi.getNet() : null;
    const items = net && net.items ? net.items : null;
    if (!items || !Object.keys(items).length) return;
    itemsLoaded = true;
    for (const [id, meta] of Object.entries(items)) {
      const o = document.createElement('option');
      o.value = id;
      o.textContent = (meta.name || id) + ' (' + id + ')';
      itemSel.appendChild(o);
    }
  }

  function refresh() {
    const host = window.gameApi.isHost ? window.gameApi.isHost() : false;
    const p = window.gameApi.getLocalPlayer();
    note.textContent = host ? 'Ты хост. Команды применятся.' : 'Ты НЕ хост — сервер отклонит команды.';
    if (p) {
      if (document.activeElement !== dmgInput) dmgInput.value = p.adminDamage || 1;
      if (document.activeElement !== spdInput) spdInput.value = p.adminSpeed || 1;
      godBox.checked = !!p.god;
    }
    loadItems();
  }
  function show() { overlay.style.display = 'flex'; refresh(); }
  function hide() { overlay.style.display = 'none'; }
  function toggle() {
    if (overlay.style.display === 'flex') hide();
    else show();
  }

  overlay.addEventListener('click', (e) => { if (e.target === overlay) hide(); });
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyP' && !e.repeat) {
      if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
      if (document.activeElement && document.activeElement.tagName === 'SELECT') return;
      toggle();
    }
    if (e.code === 'Escape' && overlay.style.display === 'flex') hide();
  });

  setInterval(() => { if (overlay.style.display === 'flex') refresh(); }, 1000);

  window.adminUi = { show, hide, toggle };
}

boot();
'''
FILES['REAMDE.md'] = r'''# Co-op RPG (Radmin + WebSocket)

Кооперативная 2D-RPG на чистом JavaScript + Node.js. Хост поднимает сервер, друзья подключаются через Radmin VPN. Никаких облаков, никаких npm-фреймворков на клиенте, никакой сборки.

---

## 1. Что это

- **Клиент** — статика: `index.html` + ES-модули без бандлера, рендер на `<canvas>` 2D.
- **Сервер** — один файл `server.js`: раздаёт статику по HTTP, держит WebSocket, хранит состояние игры (карта, игроки, враги, снаряды, инвентарь).
- **Связь** — `ws://<ip>:3000`, JSON-сообщения.
- **Сеть** — Radmin VPN даёт игрокам виртуальный LAN. Хост раздаёт свой Radmin-IP, друзья стучатся туда.

**Что уже реализовано:**

- Лобби: имена, статус «Готов», хост-стартер.
- Большая процедурная карта 600×450 тайлов.
- Восемь поверхностей: трава, камень (стена), вода, каменный пол, железо, медь, уголь, олово + печка 2x2.
- Разрушаемые стены и рудные жилы — удар ПКМ, жила восстанавливается через 2 минуты.
- Три типа врагов: ближник (квадрат), дальник (круг, бьёт дробью 6 пуль), блуждающий (пятиугольник).
- Враги спавнятся группами, лимит 300, ускоренный спавн каждую секунду.
- Выстрел по курсору (ЛКМ): пули ближе в 2 раза, продолговатые, вспышки и искры.
- Магазин 10 патронов, перезарядка 3с. На 10 уровне — мод: дробь x5 (интервал 1с) или скорострел (зажатая ЛКМ).
- Инвентарь вверху экрана, лут с врагов (35%) и с блоков (100%).
- Ходьба по воде с замедлением в 1.5 раза.
- Миникарта в левом нижнем углу.
- Крафт-окно по центру на С, печка из 10 кирпичей, плавка руд на слитки.
- Панель админа (P, только хост): урон, скорость, уровень, бессмертие, предметы, спавн.

Проект **намеренно минималистичный**. Не притаскивать сюда фреймворки, сборщики, TypeScript, React, Phaser и т.п. без явного запроса.

---

## 2. Структура репозитория

```
.
├── package.json          # один скрипт start, одна зависимость ws
├── server.js             # HTTP-статика + WebSocket + вся игровая логика
├── public/
│   ├── index.html        # единственная HTML-страница (лобби + canvas)
│   └── js/
│       ├── main.js       # точка входа: лобби, игровой цикл, рендер, инвентарь, миникарта
│       ├── input.js      # клавиатура и мышь
│       ├── net.js        # WebSocket-клиент, состояние игры
│       ├── fx.js         # частицы: вспышки выстрелов, искры попаданий
│       ├── craft-ui.js   # окно крафта по центру (С)
│       ├── furnace-ui.js # окно печки (E рядом с печкой)
│       ├── mod-ui.js     # выбор мода выстрела на 10 уровне
│       ├── admin-ui.js   # панель админа (P, только хост)
│       └── spend-ui.js   # панель прокачки (1/2/3)
└── README.md
```

**Правило:** клиентский код живёт **только** в `public/`. Серверный — **только** в корне (`server.js`). Не смешивать.

**Замечание про файлы, которых больше нет.** В ранней версии были `public/js/camera.js`, `world.js`, `player.js`, `public/style.css`. Сейчас:

- камера и игрок живут прямо в `main.js` (не раздулось, дробить рано);
- мир генерируется **на сервере** и приходит в `init` — `world.js` не нужен;
- стили инлайновые в `index.html` — `style.css` не нужен.

Если эти файлы остались — их можно удалить.

---

## 3. Как запустить

### Хост

```bash
npm install
npm start
```

В консоли появится:

```
Сервер запущен:
  Локально:  http://localhost:3000
  Radmin VPN:  http://26.x.x.x:3000
  Ethernet:    http://192.168.x.x:3000

Раздайте друзьям адрес Radmin-интерфейса.
```

Открыть `http://localhost:3000` → ввести имя → дождаться друзей → нажать «Начать игру».

### Друг

Открыть `http://26.x.x.x:3000` (Radmin-IP хоста) → ввести имя → «Готов». Хост нажимает «Начать игру».

### Требования

- Node.js 18+ (используются ES-модули, `import`)
- Radmin VPN (или любая LAN), все в одной сети
- Node.js разрешён в брандмауэре Windows для **частных сетей** на порт 3000

---

## 4. Сетевой протокол

Единственный транспорт — WebSocket, формат — JSON. Все типы сообщений перечислены ниже. **При добавлении новых типов — обновлять этот раздел.**

### Клиент → сервер

| `type`          | Поля    | Когда                                        |
|-----------------|---------|----------------------------------------------|
| `setName`       | `name`  | при смене имени в лобби                      |
| `ready`         | —       | клик по «Готов» (toggle)                     |
| `start`         | —       | клик «Начать игру» (только у хоста)          |
| `backToLobby`   | —       | возврат из игры в лобби (только у хоста)     |
| `move`          | `dx`, `dy` | 20 раз в секунду, вектор направления      |
| `attack`        | `angle` | ЛКМ — выстрел (магазин 10, перезарядка 3с, КД 0.2/1/0.15с) |
| `melee`         | `angle` | ПКМ — удар по стене/руде перед игроком            |
| `chooseMod`     | `mod` | выбор мода выстрела (`shotgun`/`rapid`), с 10 уровня, один раз |
| `spendPoint`    | `stat`  | трата очка навыков (`maxHp`/`damage`/`speed`), когда есть `points` |
| `craft`         | `recipe` | крафт (`brick`/`medkit`/`furnace`), ингредиенты списываются, иначе игнор |
| `eat`           | `item?` | съесть еду (+HP); без `item` — лучшая доступная (medkit>cheese>kuraga) |
| `place`         | `tx`, `ty` | построить стену из кирпича (50HP), иначе игнор + `tileChange` |
| `placeFurnace`  | `tx`, `ty` | поставить печку 2x2 из инвентаря (`furnace`), левый верхний угол, иначе игнор |
| `furnacePut`    | `furnaceId`, `item`, `count` | положить в печку уголь/руду (`coal`/`iron_ore`/`copper_ore`/`tin_ore`) |
| `furnaceTake`   | `furnaceId` | забрать все готовые слитки из печки |
| `adminSet`      | `damage`, `speed` | только хост: множители урона (1-20) и скорости (1-10) себе |
| `adminLevel`    | `level` | только хост: выдать себе уровень (1-50) |
| `adminGod`      | `on` | только хост: бессмертие вкл/выкл |
| `adminGive`     | `item`, `count` | только хост: выдать себе предмет (1-99) |
| `adminSpawn`    | `enemyType`, `count` | только хост: заспавнить врагов рядом (1-50) |

### Сервер → клиент

| `type`         | Поля                                          | Когда                                  |
|----------------|-----------------------------------------------|----------------------------------------|
| `init`         | `id`, `gameState`, `hostId`, `map`, `players`, `enemies`, `projectiles`, `furnaces`, `items` | в ответ на подключение WS |
| `lobby`        | `hostId`, `players[]` (только `id`, `name`, `ready`) | при изменении лобби              |
| `started`      | —                                             | когда хост стартовал игру              |
| `join`         | `player`                                      | всем, когда кто-то зашёл в игру        |
| `leave`        | `id`                                          | всем, когда кто-то отключился          |
| `state`        | `players[]`, `enemies[]`, `projectiles[]`, `furnaces[]` | 20 раз/с, broadcast всем (игроки несут `level/xp/xpNext/points/upgrades/shotMod/ammo/god`) |
| `tileChange`   | `tx`, `ty`, `tile`, `hp?`                     | при ударе по стене/руде, разрушении, респавне руды, стройке |
| `levelUp`      | `id`, `level`, `points`, `xpNext`             | каждому апу после `grantLevelUps`      |

### Формат игрока

```json
{
  "id": 3,
  "name": "Вася",
  "x": 128, "y": 96,
  "radius": 14,
  "hp": 100, "maxHp": 100,
  "dirX": 0, "dirY": 0,
  "inventory": { "cheese": 2, "stone": 5 },
  "level": 2, "xp": 45, "xpNext": 282, "points": 1,
  "upgrades": { "maxHp": 1, "damage": 0, "speed": 0 },
  "shotMod": null, "ammo": 10, "maxAmmo": 10, "reloadingUntil": 0,
  "god": false, "adminDamage": 1, "adminSpeed": 1
}
```

- `id` — серверный, монотонно растёт с 1.
- `name` — обрезается до 20 символов на сервере.
- `dirX`, `dirY` — вектор направления движения `{-1, 0, 1}`. Позицию считает **сервер**.
- `inventory` — объект `{ itemId: count }`.
- `level/xp/xpNext/points/upgrades` — прогрессия v1: опыт делится среди игроков в радиусе 400 от смерти врага (`floor(maxHp/10)` за врага), кривая `xpNext = floor(100 * level^1.5)`, +1 очко за уровень, смерть сохраняет прогресс. Трата: `maxHp` +20 maxHP и +20 heal, `damage` +10% мультипликатор, `speed` +5% мультипликатор.
- `shotMod/ammo/maxAmmo/reloadingUntil` — бой: магазин 10 патронов, перезарядка 3с, КД обычный 0.2с / дробь 1с / скорострел 0.15с. С 10 уровня `chooseMod`: `shotgun` (5 пуль) или `rapid` (зажатая ЛКМ), один раз за игру.
- `god/adminDamage/adminSpeed` — админка хоста: бессмертие, множители урона (x1-20) и скорости (x1-10).

### Формат врага

```json
{
  "id": 7,
  "type": "melee",
  "x": 200, "y": 150,
  "hp": 300, "maxHp": 300,
  "radius": 16
}
```

- `type` — `"melee"`, `"ranged"` или `"wanderer"`.
- Позиции и HP хранятся на сервере, клиент рисует ровно то, что пришло.
- `ranged` бьёт дробью: 6 пуль веером за атаку.

### Формат печки

```json
{
  "id": 1,
  "tx": 10, "ty": 12,
  "coal": 2, "charges": 3,
  "ores": { "iron_ore": 5, "copper_ore": 0, "tin_ore": 1 },
  "ingots": { "iron_ingot": 1, "copper_ingot": 0, "tin_ingot": 0 },
  "smelting": { "type": "iron_ore", "remaining": 3200, "total": 5000 }
}
```

- `tx/ty` — левый верхний угол 2x2, тайлы `T_FURNACE` твёрдые и блокируют снаряды.
- `coal` — запас угля, `charges` — оставшиеся плавки от угля (1 уголь = 4 руды).
- Плавка: олово 3с, медь 4с, железо 5с. Порядок — олово, медь, железо.
- `smelting: null` — простаивает.

### Формат снаряда

```json
{
  "id": 42,
  "x": 200, "y": 150,
  "vx": 500, "vy": 0,
  "ownerType": "player",
  "ownerId": 3,
  "ttl": 1.5,
  "maxDist": 400,
  "damage": 25
}
```

- `ownerType` — `"player"` или `"enemy"`.
- `maxDist` — предел полёта от `startX/startY` (клиент не считает, но сервер обрезает).

### Правила протокола

1. **Сервер — источник правды** для позиций, HP, врагов, снарядов, инвентаря и карты.
2. **Движение — server-authoritative.** Клиент шлёт только направление (`move` с `dx, dy`). Физику, скорость и коллизии считает сервер. Это защита от читерства и десинка; клиентская авторитарность была в ранней версии и **умышленно убрана**.
3. **Интерполяция на клиенте:** `net.js` мержит `state` по id с сохранением `px/py`, `main.js` рисует `interpPos()` — линейный переход `px/py → x/y` за измеренный `stateInterval`, телепорты (>150px, респаун) — снапом. Не менять на джиттер — это убьёт плавность.
4. **Не спамить.** 20 Гц — осознанный выбор. Чаще не надо, реже — рывки.
5. **Никаких бинарных форматов** без явной необходимости. JSON читаем и отлаживается в DevTools.

---

## 5. Архитектурные правила

### 5.1 Клиент

- **Никаких зависимостей.** Только ES-модули и встроенные API браузера.
- **Никакого бандлера.** `<script type="module">` работает как есть.
- **Никакого TypeScript.** Чистый JS.
- **Каждый модуль — один класс или одна функция**, экспортируется через `export`. Никаких `window.*`, никаких глобалов.
- **main.js — единственное место**, где создаются экземпляры и склеиваются модули. Остальные модули друг о друге не знают.

### 5.2 Сервер

- **Один файл.** Если `server.js` перевалит за ~600 строк — можно разбить на `server/` с модулями, но не раньше.
- **Никакого фреймворка** (Express, Fastify, Koa). Только `http` из stdlib.
- **Никакой БД.** Состояние игроков живёт в памяти. Упал сервер — мир пересоздался.
- **Логирование** — простой `console.log` с префиксами `+`/`-`.

### 5.3 Мир и генерация

- **Мир живёт на сервере.** Генерируется один раз при старте, приходит клиенту в `init`. Оба клиента видят одинаковую карту.
- **Мир меняется только через сервер.** Разрушенная стена → `tileChange` broadcast. Никаких «клиент сам разрушил у себя» — иначе рассинхрон.
- **Тайл 32×32**, карта **600×450** тайлов (было 200×150, увеличена в 3 раза по каждой стороне).
- **Типы поверхности** — константы в `server.js`:
  ```js
  const T_GRASS = 0;   // трава, ходим
  const T_STONE = 1;   // стена, ломается, блокирует движение и снаряды
  const T_WATER = 2;   // вода, ходим с замедлением x1.5, снаряды пролетают
  const T_FLOOR = 3;   // каменный пол, ходим
  const T_IRON = 4;    // железная жила, 75HP, лут — железная руда
  const T_COPPER = 5;  // медная жила, 75HP, лут — медная руда
  const T_COAL = 6;    // угольная жила, 75HP, лут — уголь
  const T_TIN = 7;     // оловянная жила, 75HP, лут — оловянная руда
  const T_FURNACE = 8; // печка 2x2, твёрдая, блокирует снаряды
  ```
- **Руды** восстанавливаются через 2 минуты (`ORE_RESPAWN_MS`) на том же месте, если клетка свободна.
- **Вода** не блокирует движение, но режет скорость в 1.5 раза (игроки и враги).
- **Печки** живут на сервере в `furnaces`, тайлы 2x2 — `T_FURNACE`. Сброс игры убирает печки в пол.

---

## 6. Соглашения по коду

### Имена

- Файлы модулей — `lowercase.js` (`net.js`, `input.js`).
- Классы — `PascalCase` (`Net`, `Input`).
- Методы и переменные — `camelCase` (`sendState`, `isSolid`).
- Приватные методы — префикс `_` (`_handle`, `_send`).
- Константы — `UPPER_SNAKE` (`PORT`, `TILE`, `ENEMY_AGGRO`, `PROJ_MAX_DIST`).

### Стиль

- 2 пробела, без табов.
- Точка с запятой — **есть**.
- Одинарные кавычки в JS.
- Фигурные скобки — K&R (открывающая на той же строке).
- Стрелочные функции для колбэков, обычные `function` для именованных.
- Не сокращать имена: `player`, не `pl`; `enemy`, не `e` (кроме коротких циклов `for (const e of enemies.values())` — допустимо).

### Комментарии

- **Русский язык.** Это осознанно — вся документация и переписка на русском.
- Секции в файлах разделяются `// ---------- название ----------`.
- Не комментировать очевидное. Комментировать **почему**, а не **что**.

### Порядок в файле

1. Импорты
2. Константы
3. Класс / главная функция
4. Экспорт (обычно `export class` в начале)

---

## 7. Что НЕЛЬЗЯ делать

Это самые важные правила. Нарушение ломает проект или выкидывает нас из архитектуры.

### Категорически нельзя

1. **Добавлять клиентские зависимости** (React, Vue, Phaser, Three.js, lodash, axios…). Проект построен на голом JS.
2. **Ставить сборщик** (Webpack, Vite, esbuild, Rollup). Мы запускаем файлы как есть.
3. **Писать на TypeScript** и компилировать.
4. **Заменять WebSocket на HTTP-поллинг.** `setInterval` + `fetch` убьёт производительность и смысл проекта.
5. **Заменять WS на Socket.IO.** Это тащит свою библиотеку и клиентскую, и серверную.
6. **Менять порт 3000** без обновления константы `PORT` и клиентского WS-адреса.
7. **Возвращать client-authoritative движение.** Сейчас позиции считает сервер из `dirX/dirY`. Переделывать — только по явному запросу.
8. **Коммитить `node_modules/`.** Есть `.gitignore` — не трогать.
9. **Синхронизировать карту клиентом.** Все `tileChange` идут через сервер.
10. **Писать имена и сообщения на английском.** Весь UI, комментарии и логи — на русском.
11. **Спавнить врагов на клиенте.** Только сервер, иначе рассинхрон.
12. **Считать урон на клиенте.** Урон считает сервер. Клиент только рисует то, что пришло в `state`.

### Нежелательно

- Раздувать `main.js` больше ~600 строк. Разбивать на модули.
- Делать классы с публичными полями вместо методов.
- Использовать `var`. Только `let`/`const`.
- Создавать глобальные переменные на `window`.
- Добавлять `console.log` в горячий путь (игровой цикл, `_handle` каждого сообщения).

---

## 8. Как расширять проект

Порядок сложности, согласованный с владельцем. Зелёным помечено то, что **уже сделано**.

1. ✅ **Враги** — сервер спавнит мобов, шлёт позиции. Урон считает сервер.
2. ✅ **Ресурсы** — стены ломаются, тип блока падает в инвентарь.
3. ✅ **Инвентарь** — у каждого игрока свой.
4. ⏳ **Крафт** — UI поверх канваса.
5. ⏳ **Строительство** — блоки ставятся через сервер.
6. ✅ **HP и бой** — базовая боевая система с тремя типами врагов.
7. ⏳ **Боссы, разное оружие, использование предметов из инвентаря.**

### Как добавить **новый тип врага**

1. Добавь запись в `ENEMY_TYPES` в `server.js`:
   ```js
   const ENEMY_TYPES = {
     // ...
     ghost: { hp: 60, speed: 200, radius: 12, damage: 6, attackCD: 700, loot: 'stone' },
   };
   ```
2. Обнови `pickEnemyType()` — веса выпадения.
3. В `main.js`, в `draw()` для врагов, добавь форму и цвет для нового `type`.
4. Обнови эту README (раздел 4).

### Как добавить **новый предмет**

1. Добавь в `ITEMS` в `server.js`:
   ```js
   const ITEMS = {
     // ...
     bone: { name: 'Кость', color: '#eeeeee' },
   };
   ```
2. Укажи его в `loot` нужного врага.
3. Клиент автоматически нарисует его в инвентаре — цвет и имя приходят в `init`.

### Как добавить **изменение мира, которое сохраняется**

- Карта уже на сервере. Значит — только серверные изменения + `tileChange`.
- Не генерируй изменения на клиентах. Даже «локально, потом синхронизируемся» — нет.

---

## 9. Отладка

### Если не коннектится

1. Radmin VPN активен у всех, видите друг друга в списке.
2. Пинг через Radmin (правый клик → «Пинг») проходит.
3. Node.js разрешён в брандмауэре Windows для **частных сетей**.
4. Порт 3000 свободен: `netstat -ano | findstr :3000`.
5. F12 → Console: если `WebSocket connection failed` — не туда стучишься или фаервол.

### Если изменения не видны после обновления

`Ctrl+Shift+R` в браузере — сбрасывает кеш `main.js` / `net.js` / `input.js`.

### Полезные команды

```bash
# сменить порт
PORT=3001 npm start

# посмотреть, кто слушает 3000
netstat -ano | findstr :3000
```

### DevTools

- **Network → WS** — видно каждое сообщение (`state`, `tileChange`, `init`).
- **Console** — логи `Сервер запущен: …` печатает **сервер**, не браузер.
- **Application → Clear storage** — если браузер кеширует старый HTML.

---

## 10. Правила для AI, работающего с репозиторием

Если ты (AI) впервые открыл этот репозиторий — **прочитай этот раздел целиком**.

1. **Язык — русский.** Комментарии, README, UI, коммиты, ответы пользователю. Английский — только в идентификаторах кода.
2. **Никаких новых зависимостей без явного запроса.** Если решение требует npm-пакета — сначала спроси.
3. **Не менять архитектуру** (сервер/клиент, транспорт, формат сообщений, server-authoritative движение) без явного запроса.
4. **Правила стиля — см. раздел 6.** Если сомневаешься — смотри на существующий код и повторяй.
5. **Протокол — см. раздел 4.** Новые типы сообщений добавляй **в обе стороны** (клиент + сервер) и **обновляй таблицу**.
6. **Не трогать `package.json`** без причины. Единственная зависимость — `ws`.
7. **Перед добавлением файла** — проверь, что он не дублирует существующий модуль.
8. **Тестируй локально:** `npm install && npm start` — сервер должен подняться без ошибок. Открой `http://localhost:3000` — лобби должно появиться.
9. **Не рефакторить чужое без запроса.** Если видишь стилистическую проблему — упомяни, но не правь молча.
10. **Не писать тесты** (jest, mocha, vitest) — проект их не использует и не планирует в текущем виде.
11. **Не добавлять CI/CD** (GitHub Actions, GitLab CI) без запроса.
12. **Не менять кодировку файлов.** UTF-8 без BOM, LF-переводы строк.
13. **Сомневаешься — спроси.** Лучше уточнить, чем сломать установленный порядок.
14. **Каждая правка сопровождается Python-скриптом**, который её применяет. Формат: замена файлов целиком с бэкапом `.bak` и флагом `--revert`. Не патчить по кускам, если можно заменить файл полностью.
15. **Обновляй README** при изменении игровых параметров, протокола или правил.

### Красные флаги — если видишь такое в своём решении, остановись

- Ты ставишь `npm install <что-то новое>` — стоп, спроси.
- Ты добавляешь `<script src="https://cdn...">` в HTML — стоп, спроси.
- Ты создаёшь файл `webpack.config.js`, `vite.config.js`, `tsconfig.json` — стоп, это не наш стек.
- Ты пишешь `import React` — стоп.
- Ты пытаешься заменить `ws` на `socket.io` — стоп.
- Ты добавляешь `.ts`-файлы — стоп.
- Ты переписываешь `server.js` на Express — стоп.
- Ты возвращаешь клиенту расчёт позиции игрока — стоп, движение серверное.
- Ты считаешь урон или лут на клиенте — стоп, только сервер.

---

## 11. Лицензия и авторство

Учебно-развлекательный проект. Никакой лицензии, никаких гарантий. Код свободен для правок в рамках правил выше.

---

## 12. Быстрая шпаргалка

```bash
# поднять
npm install
npm start

# хост:  http://localhost:3000
# друг:  http://<radmin-ip>:3000

# порт по умолчанию:  3000
# транспорт:          WebSocket, JSON
# частота рассылки:   20 Гц
# карта:              600×450 тайлов, тайл 32px
# поверхности:        трава (0), камень/стена (1), вода (2, ходим x1.5 медленнее), пол (3),
#                     железо (4), медь (5), уголь (6), олово (7), печка (8)
# движение:           server-authoritative, клиент шлёт только dx/dy
# стены:              50 HP, удар ПКМ — 25, дальность 60 px, лут — Камень (100%)
# руды:               75 HP, удар ПКМ — 25, лут 1-2 руды, респавн через 2 мин
# типы врагов:
#   melee    (квадрат)     300 HP, 220 speed, урон 15, лут — Сыр (35%)
#   ranged   (круг)         80 HP, 180 speed, урон  8 x6 дробью, лут — Курага (35%)
#   wanderer (пятиугольник) 120 HP, 60→260 speed, урон 12, лут — Носки (35%)
# агро:               350 px, память после попадания — 6 с
# враги:              лимит 300, групп 30-50, спавн ускорен — каждые 1с до 3 групп
# прогрессия (v1):    XP за врага floor(maxHp/10), дележ в радиусе 400 (остаток убийце, fallback убийце)
# xpNext:             floor(100 * level^1.5), +1 очко/уровень, смерть сохраняет прогресс
# трата очков:        maxHp +20/+heal, урон +10%/очко, скорость +5%/очко (клавиши 1/2/3)
# крафт (С по центру): кирпич = 2 камня | 3 носков; аптечка = 2 сыра + курага; печь = 10 кирпичей
# еда:                аптечка +60, сыр +12, курага +8 (E — лучшая, рядом с печкой E открывает печку)
# стройка:            F+ЛКМ — стена 50HP в радиусе 130; G+ЛКМ — печка 2x2
# печка:              топливо уголь, 1 уголь = 4 руды; олово 3с, медь 4с, железо 5с → слитки
# миникарта:          слева внизу, враги красные, печки оранжевые, игроки синие/зелёный
# бой:                пули ближе x2, продолговатые, вспышки/искры; магазин 10, перезарядка 3с
# моды (10 ур.):      дробь x5 (КД 1с) или скорострел (зажатая ЛКМ, КД 0.15с); обычный КД 0.2с
# админка (P, хост):  урон x1-20, скорость x1-10, уровень 1-50, бессмертие, предметы, спавн
# снаряд игрока:      500 px/с, урон 25, дальность 400 px
```

**Помни: минимум зависимостей, максимум читаемости, всё на русском.**'''

def write_file(path, content, dry):
    if path.exists():
        old = path.read_text(encoding='utf-8')
        if old == content:
            return 'already ok'
        if not dry:
            bak = path.with_suffix(path.suffix + '.bak')
            if not bak.exists():
                shutil.copy2(path, bak)
            path.write_text(content, encoding='utf-8')
        return 'updated (.bak)'
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return 'created'

def revert():
    n = 0
    for name in FILES:
        p = Path(name)
        bak = p.with_suffix(p.suffix + '.bak')
        if bak.exists():
            shutil.copy2(bak, p)
            bak.unlink()
            print('  restore', p)
            n += 1
        else:
            print('  no bak', p)
    print('done' if n else 'nothing')
    return 0 if n else 1

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--revert', action='store_true')
    a = ap.parse_args()
    if a.revert:
        return revert()
    for name, content in FILES.items():
        print(name, write_file(Path(name), content, a.dry_run))
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
