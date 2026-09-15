#!/usr/bin/env python3
"""
replace_files.py — заменяет файлы игры на новые версии.

Запуск из корня проекта (там, где server.js и package.json):
    python replace_files.py            # применить
    python replace_files.py --revert   # откатить из .bak
    python replace_files.py --dry-run  # только показать, что будет записано

Старые файлы сохраняются рядом как <имя>.bak (один раз).
"""

import argparse
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Содержимое новых файлов
# ---------------------------------------------------------------------------

FILES = {}

FILES["server.js"] = r'''const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

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

const wss = new WebSocket.Server({ server });

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
'''

FILES["public/index.html"] = r'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>game_with_hbs</title>
<style>
  html, body { margin: 0; padding: 0; background: #111; overflow: hidden; height: 100%; }
  canvas { display: block; }
  #hud {
    position: fixed; top: 10px; left: 10px; color: #eee;
    font-family: monospace; font-size: 14px; pointer-events: none;
    text-shadow: 0 1px 2px #000;
  }
  #hint {
    position: fixed; bottom: 10px; left: 10px; color: #888;
    font-family: monospace; font-size: 12px; pointer-events: none;
  }
</style>
</head>
<body>
<canvas id="game"></canvas>
<div id="hud"></div>
<div id="hint">WASD — движение, ЛКМ — атака в сторону курсора</div>
<script type="module" src="/js/main.js"></script>
</body>
</html>
'''

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

FILES["public/js/net.js"] = r'''export class Net {
  constructor() {
    this.id = null;
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
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
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
      this.map = msg.map;
      this.players.clear();
      msg.players.forEach(p => this.players.set(p.id, p));
      this.enemies.clear();
      msg.enemies.forEach(e => this.enemies.set(e.id, e));
      this.projectiles.clear();
      msg.projectiles.forEach(p => this.projectiles.set(p.id, p));
      this.emit('init', msg);
    } else if (msg.type === 'join') {
      this.players.set(msg.player.id, msg.player);
    } else if (msg.type === 'leave') {
      this.players.delete(msg.id);
    } else if (msg.type === 'state') {
      const seen = new Set();
      msg.players.forEach(p => {
        seen.add(p.id);
        const existing = this.players.get(p.id);
        if (existing) Object.assign(existing, p);
        else this.players.set(p.id, p);
      });
      for (const pid of [...this.players.keys()]) {
        if (!seen.has(pid)) this.players.delete(pid);
      }
      this.enemies.clear();
      msg.enemies.forEach(e => this.enemies.set(e.id, e));
      this.projectiles.clear();
      msg.projectiles.forEach(p => this.projectiles.set(p.id, p));
      this.emit('state', msg);
    }
  }

  getSelf() {
    return this.id != null ? this.players.get(this.id) : null;
  }
  sendMove(dx, dy) {
    if (this.ws?.readyState === 1) {
      this.ws.send(JSON.stringify({ type: 'move', dx, dy }));
    }
  }
  sendAttack(angle) {
    if (this.ws?.readyState === 1) {
      this.ws.send(JSON.stringify({ type: 'attack', angle }));
    }
  }
}
'''

FILES["public/js/main.js"] = r'''import { Net } from './net.js';
import { Input } from './input.js';

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
  if (!myPlayer) return;
  const wx = e.clientX + camera.x;
  const wy = e.clientY + camera.y;
  const angle = Math.atan2(wy - myPlayer.y, wx - myPlayer.x);
  net.sendAttack(angle);
});

const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
net.connect(`${wsProto}//${location.host}`).then(() => {
  mapData = net.map;
});

setInterval(() => {
  const { dx, dy } = input.getMove();
  net.sendMove(dx, dy);
}, 50);

function draw() {
  requestAnimationFrame(draw);

  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  myPlayer = net.getSelf();
  if (!myPlayer || !mapData) return;

  const targetCamX = myPlayer.x - canvas.width / 2;
  const targetCamY = myPlayer.y - canvas.height / 2;
  if (!camInit) {
    camera.x = targetCamX; camera.y = targetCamY; camInit = true;
  } else {
    camera.x += (targetCamX - camera.x) * CAM_LERP;
    camera.y += (targetCamY - camera.y) * CAM_LERP;
  }

  const ox = -camera.x;
  const oy = -camera.y;

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
        ctx.strokeStyle = '#262626';
        ctx.lineWidth = 1;
        ctx.strokeRect(tx * TILE + ox + 0.5, ty * TILE + oy + 0.5, TILE - 1, TILE - 1);
      }
    }
  }

  for (const e of net.enemies.values()) {
    const sx = e.x + ox, sy = e.y + oy;
    ctx.fillStyle = '#c0392b';
    ctx.beginPath();
    ctx.arc(sx, sy, e.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#e74c3c';
    ctx.lineWidth = 2;
    ctx.stroke();

    const hpW = 30;
    const hpX = sx - hpW / 2;
    const hpY = sy - e.radius - 8;
    ctx.fillStyle = '#222';
    ctx.fillRect(hpX, hpY, hpW, 4);
    ctx.fillStyle = '#e74c3c';
    ctx.fillRect(hpX, hpY, hpW * (e.hp / e.maxHp), 4);
  }

  for (const p of net.players.values()) {
    if (p.id === myPlayer.id) continue;
    const sx = p.x + ox, sy = p.y + oy;
    ctx.fillStyle = '#3498db';
    ctx.beginPath();
    ctx.arc(sx, sy, p.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#5dade2';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  {
    const sx = myPlayer.x + ox;
    const sy = myPlayer.y + oy;
    ctx.fillStyle = '#2ecc71';
    ctx.beginPath();
    ctx.arc(sx, sy, myPlayer.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#58d68d';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  for (const pr of net.projectiles.values()) {
    const sx = pr.x + ox, sy = pr.y + oy;
    ctx.fillStyle = '#f1c40f';
    ctx.beginPath();
    ctx.arc(sx, sy, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  if (input.mouse.x || input.mouse.y) {
    ctx.strokeStyle = 'rgba(241,196,15,0.85)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(input.mouse.x, input.mouse.y, 8, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(input.mouse.x - 12, input.mouse.y);
    ctx.lineTo(input.mouse.x + 12, input.mouse.y);
    ctx.moveTo(input.mouse.x, input.mouse.y - 12);
    ctx.lineTo(input.mouse.x, input.mouse.y + 12);
    ctx.stroke();
  }

  hud.textContent = `HP: ${Math.max(0, Math.round(myPlayer.hp))}/${myPlayer.maxHp}   Врагов: ${net.enemies.size}`;
}
draw();
'''

# ---------------------------------------------------------------------------


def write_file(path: Path, content: str, dry: bool) -> str:
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
    else:
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return "создано"


def revert() -> int:
    any_restored = False
    for name in FILES:
        p = Path(name)
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            shutil.copy2(bak, p)
            bak.unlink()
            print(f"  ↺ {p}")
            any_restored = True
        else:
            print(f"  – {p}: .bak нет")
    if not any_restored:
        print("Нечего восстанавливать.")
        return 1
    print("Готово.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, что будет сделано")
    ap.add_argument("--revert", action="store_true",
                    help="восстановить файлы из .bak")
    args = ap.parse_args()

    if args.revert:
        print("== revert ==")
        return revert()

    print(f"== replace_files ==  ({'dry-run' if args.dry_run else 'apply'})\n")

    for name, content in FILES.items():
        p = Path(name)
        result = write_file(p, content, args.dry_run)
        print(f"  {p}: {result}")

    print()
    if args.dry_run:
        print("dry-run завершён, ничего не записано.")
        return 0

    print("Готово. Дальше:")
    print("  npm install")
    print("  npm start")
    print("Открой http://localhost:3000 в браузере с очисткой кеша (Ctrl+Shift+R).")
    return 0


if __name__ == "__main__":
    sys.exit(main())