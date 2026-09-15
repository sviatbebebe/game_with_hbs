#!/usr/bin/env python3
"""
update_lobby_radmin.py — обновление проекта:
  * возвращает лобби
  * игра по сети через RadminVPN
  * враги спавнятся группами в разных частях карты
  * у врагов есть радиус агрессии, вне него они патрулируют

Запуск из корня проекта:
    python update_lobby_radmin.py
    python update_lobby_radmin.py --dry-run
    python update_lobby_radmin.py --revert
"""

import argparse
import shutil
import sys
from pathlib import Path

FILES = {}

# ---------------------------------------------------------------- server.js
FILES["server.js"] = r'''import http from 'node:http';
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
'''

# ---------------------------------------------------------------- index.html
FILES["public/index.html"] = r'''<!DOCTYPE html>
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
    position: fixed; bottom: 10px; left: 10px; font-size: 12px; color: #888;
    pointer-events: none;
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
  <div id="controls">WASD — движение, ЛКМ — атака</div>
</div>

<script type="module" src="/js/main.js"></script>
</body>
</html>
'''

# ---------------------------------------------------------------- input.js
FILES["public/js/input.js"] = r'''export class Input {
  constructor() {
    this.keys = new Set();
    this.mouse = { x: 0, y: 0, down: false };
    window.addEventListener('keydown', (e) => this.keys.add(e.code));
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
  }
  isDown(code) { return this.keys.has(code); }
  getMove() {
    let dx = 0, dy = 0;
    if (this.isDown('KeyA') || this.isDown('ArrowLeft')) dx -= 1;
    if (this.isDown('KeyD') || this.isDown('ArrowRight')) dx += 1;
    if (this.isDown('KeyW') || this.isDown('ArrowUp')) dy -= 1;
    if (this.isDown('KeyS') || this.isDown('ArrowDown')) dy += 1;
    return { dx, dy };
  }
}
'''

# ---------------------------------------------------------------- net.js
FILES["public/js/net.js"] = r'''export class Net {
  constructor() {
    this.id = null;
    this.hostId = null;
    this.gameState = 'lobby';
    this.players = new Map();
    this.enemies = new Map();
    this.projectiles = new Map();
    this.map = null;
    this.ws = null;
    this.handlers = {};
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
    if (msg.type === 'init') {
      this.id = msg.id;
      this.hostId = msg.hostId;
      this.gameState = msg.gameState;
      this.map = msg.map;
      this.players.clear(); msg.players.forEach(p => this.players.set(p.id, p));
      this.enemies.clear(); msg.enemies.forEach(e => this.enemies.set(e.id, e));
      this.projectiles.clear(); msg.projectiles.forEach(p => this.projectiles.set(p.id, p));
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
            x: 0, y: 0, radius: 14, hp: 100, maxHp: 100 });
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
    } else if (msg.type === 'state') {
      this.gameState = 'playing';
      const seen = new Set();
      msg.players.forEach(p => {
        seen.add(p.id);
        const ex = this.players.get(p.id);
        if (ex) Object.assign(ex, p);
        else this.players.set(p.id, p);
      });
      for (const pid of [...this.players.keys()]) if (!seen.has(pid)) this.players.delete(pid);
      this.enemies.clear(); msg.enemies.forEach(e => this.enemies.set(e.id, e));
      this.projectiles.clear(); msg.projectiles.forEach(p => this.projectiles.set(p.id, p));
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
}
'''

# ---------------------------------------------------------------- main.js
FILES["public/js/main.js"] = r'''import { Net } from './net.js';
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
window.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  if (net.gameState !== 'playing' || !myPlayer) return;
  const wx = e.clientX + camera.x;
  const wy = e.clientY + camera.y;
  const angle = Math.atan2(wy - myPlayer.y, wx - myPlayer.x);
  net.sendAttack(angle);
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
  const x1 = Math.min(mapData.w, Math.ceil((camera.x + canvas.width) / TILE));
  const y1 = Math.min(mapData.h, Math.ceil((camera.y + canvas.height) / TILE));

  for (let ty = y0; ty < y1; ty++) {
    for (let tx = x0; tx < x1; tx++) {
      const isWall = tiles[ty][tx] === 1;
      ctx.fillStyle = isWall ? '#333' : '#1e1e1e';
      ctx.fillRect(tx * TILE + ox, ty * TILE + oy, TILE, TILE);
      if (!isWall) {
        ctx.strokeStyle = '#262626'; ctx.lineWidth = 1;
        ctx.strokeRect(tx * TILE + ox + 0.5, ty * TILE + oy + 0.5, TILE - 1, TILE - 1);
      }
    }
  }

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

  for (const p of net.players.values()) {
    if (p.id === myPlayer.id) continue;
    const sx = p.x + ox, sy = p.y + oy;
    ctx.fillStyle = '#3498db';
    ctx.beginPath(); ctx.arc(sx, sy, p.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#5dade2'; ctx.lineWidth = 2; ctx.stroke();
  }

  {
    const sx = myPlayer.x + ox, sy = myPlayer.y + oy;
    ctx.fillStyle = '#2ecc71';
    ctx.beginPath(); ctx.arc(sx, sy, myPlayer.radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#58d68d'; ctx.lineWidth = 2; ctx.stroke();
  }

  for (const pr of net.projectiles.values()) {
    const sx = pr.x + ox, sy = pr.y + oy;
    ctx.fillStyle = '#f1c40f';
    ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill();
  }

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
'''


def write_file(path: Path, content: str, dry: bool):
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old == content:
            return "уже актуально"
        if not dry:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(path, bak)
            path.write_text(content, encoding="utf-8")
        return "заменено (бэкап .bak)"
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return "создано"


def revert() -> int:
    restored = 0
    for name in FILES:
        p = Path(name)
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            shutil.copy2(bak, p)
            bak.unlink()
            print("  ↺", p)
            restored += 1
        else:
            print("  –", p, ": .bak нет")
    if restored == 0:
        print("Нечего восстанавливать.")
        return 1
    print("Готово.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        print("== revert ==")
        return revert()

    print("== update_lobby_radmin ==  (" +
          ("dry-run" if args.dry_run else "apply") + ")\n")

    for name, content in FILES.items():
        p = Path(name)
        result = write_file(p, content, args.dry_run)
        print("  " + str(p) + ": " + result)

    print()
    if args.dry_run:
        print("dry-run завершён, файлы не записаны.")
        return 0

    print("Готово. Дальше:")
    print("  npm start")
    print("Откройте http://localhost:3000 с Ctrl+Shift+R.")
    print("Radmin-адрес сервер печатает в консоли при старте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())