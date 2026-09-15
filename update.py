#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_to_radmin_ws.py

Обновляет проект до версии с Radmin-IP + WebSocket (Node.js сервер).
Удаляет старые файлы (index.html, style.css, js/) и создаёт новые:
    package.json
    server.js
    public/index.html
    public/style.css
    public/js/{main,input,camera,world,player,net}.js

Запуск: python update_to_radmin_ws.py
(запускать в корне проекта, где лежал старый index.html)
"""

from pathlib import Path
import shutil
import sys

FILES = {}

# ----------------------------------------------------------------- package.json
FILES["package.json"] = """{
  "name": "rpg-radmin",
  "version": "1.0.0",
  "type": "module",
  "scripts": { "start": "node server.js" },
  "dependencies": { "ws": "^8.18.0" }
}
"""

# ------------------------------------------------------------------- server.js
FILES["server.js"] = """import { WebSocketServer } from 'ws';
import http from 'http';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 3000;
const PUBLIC = path.join(__dirname, 'public');
const MIME = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.png':'image/png' };

// ---------- статика ----------
const httpServer = http.createServer((req, res) => {
  let urlPath = req.url.split('?')[0];
  if (urlPath === '/') urlPath = '/index.html';
  const filePath = path.join(PUBLIC, urlPath);
  if (!filePath.startsWith(PUBLIC)) { res.writeHead(403); res.end(); return; }
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(filePath)] || 'application/octet-stream' });
    res.end(data);
  });
});

// ---------- WebSocket ----------
const wss = new WebSocketServer({ server: httpServer });
const players = new Map();
let nextId = 1;

const TILE = 32;
const SPAWNS = [
  { x: TILE*4, y: TILE*4 },
  { x: TILE*6, y: TILE*4 },
  { x: TILE*4, y: TILE*6 },
  { x: TILE*6, y: TILE*6 },
];

function broadcast(obj, exceptId = null) {
  const data = JSON.stringify(obj);
  for (const ws of wss.clients) {
    if (ws.readyState !== 1 || ws.playerId === exceptId) continue;
    ws.send(data);
  }
}

wss.on('connection', ws => {
  const id = nextId++;
  ws.playerId = id;

  ws.on('message', raw => {
    let msg; try { msg = JSON.parse(raw); } catch { return; }

    if (msg.type === 'join') {
      const sp = SPAWNS[(id - 1) % SPAWNS.length];
      const player = {
        id,
        name: String(msg.name || 'Player').slice(0, 12),
        x: sp.x, y: sp.y,
        hue: (id * 137) % 360,
      };
      players.set(id, player);
      console.log(`+ ${player.name} (id=${id}) — всего ${players.size}`);

      ws.send(JSON.stringify({ type: 'init', id, players: [...players.values()] }));
      broadcast({ type: 'join', player }, id);
    }
    else if (msg.type === 'state') {
      const p = players.get(id);
      if (p) { p.x = msg.x; p.y = msg.y; }
    }
  });

  ws.on('close', () => {
    const p = players.get(id);
    if (!p) return;
    players.delete(id);
    broadcast({ type: 'leave', id });
    console.log(`- ${p.name} вышел — всего ${players.size}`);
  });
});

// рассылка 20 раз в секунду
setInterval(() => {
  if (!players.size) return;
  broadcast({ type: 'state', players: [...players.values()] });
}, 50);

// ---------- запуск ----------
httpServer.listen(PORT, '0.0.0.0', () => {
  const ips = [];
  for (const iface of Object.values(os.networkInterfaces())) {
    for (const info of iface) {
      if (info.family === 'IPv4' && !info.internal) ips.push(info.address);
    }
  }
  console.log('=== Server running ===');
  console.log(`  local:  http://localhost:${PORT}`);
  for (const ip of ips) {
    const tag = ip.startsWith('26.') ? ' ← Radmin (этот дай другу)' : '';
    console.log(`  LAN:    http://${ip}:${PORT}${tag}`);
  }
});
"""

# ------------------------------------------------------------ public/index.html
FILES["public/index.html"] = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Co-op RPG</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <canvas id="game" width="960" height="640"></canvas>

  <div id="menu">
    <h1>Co-op RPG</h1>
    <input id="name" placeholder="Твоё имя" maxlength="12" value="Player">

    <label for="hostIp" class="label">IP хоста (Radmin)</label>
    <input id="hostIp" placeholder="оставь пустым, если ты хост">

    <button id="playBtn">Подключиться</button>
    <p id="status"></p>
    <p id="selfHint" class="hint"></p>
  </div>

  <script type="module" src="js/main.js"></script>
</body>
</html>
"""

# ------------------------------------------------------------ public/style.css
FILES["public/style.css"] = """* { box-sizing: border-box; }
body {
  margin: 0; background: #0a0a0a; color: #ddd;
  font: 14px/1.4 system-ui, sans-serif;
  display: flex; align-items: center; justify-content: center;
  height: 100vh;
}
canvas { image-rendering: pixelated; border: 2px solid #333; }

#menu {
  position: fixed; inset: 0;
  background: rgba(10,10,10,0.96);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 10px; padding: 20px; text-align: center;
}
#menu[hidden] { display: none; }
#menu h1 { margin: 0 0 12px; font-weight: 300; letter-spacing: 4px; }
#menu input, #menu button {
  font: inherit; padding: 10px 14px;
  background: #1a1a1a; color: #eee;
  border: 1px solid #444; border-radius: 4px;
  width: 260px;
}
#menu button { cursor: pointer; background: #2a3a2a; }
#menu button:hover { background: #354a35; }
#menu button:disabled { opacity: 0.5; cursor: default; }
.label { font-size: 12px; color: #888; margin-top: 6px; }
.hint  { font-size: 12px; color: #666; max-width: 320px; }
#status { color: #8ac; min-height: 20px; }
"""

# ---------------------------------------------------------- public/js/input.js
FILES["public/js/input.js"] = """export class Input {
  constructor() {
    this.keys = new Set();
    window.addEventListener('keydown', e => this.keys.add(e.code));
    window.addEventListener('keyup',   e => this.keys.delete(e.code));
  }
  isDown(code) { return this.keys.has(code); }
}
"""

# --------------------------------------------------------- public/js/camera.js
FILES["public/js/camera.js"] = """export class Camera {
  constructor(w, h) { this.w = w; this.h = h; this.x = 0; this.y = 0; }
  follow(t) { this.x = t.x - this.w / 2; this.y = t.y - this.h / 2; }
  toScreen(x, y) { return { x: x - this.x, y: y - this.y }; }
}
"""

# ---------------------------------------------------------- public/js/world.js
FILES["public/js/world.js"] = """const SEED = 12345;
function rng(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class World {
  constructor() {
    this.tileSize = 32;
    this.cols = 60;
    this.rows = 45;
    const r = rng(SEED);
    this.tiles = [];
    for (let y = 0; y < this.rows; y++) {
      const row = [];
      for (let x = 0; x < this.cols; x++) {
        const border = x === 0 || y === 0 || x === this.cols - 1 || y === this.rows - 1;
        const safe = x < 12 && y < 12;
        row.push(border || (!safe && r() < 0.06) ? 1 : 0);
      }
      this.tiles.push(row);
    }
  }
  isSolid(px, py) {
    const t = this.tileSize;
    const tx = Math.floor(px / t), ty = Math.floor(py / t);
    if (tx < 0 || ty < 0 || tx >= this.cols || ty >= this.rows) return true;
    return this.tiles[ty][tx] === 1;
  }
  isBlocked(x, y, r) {
    return this.isSolid(x - r, y - r) || this.isSolid(x + r, y - r)
        || this.isSolid(x - r, y + r) || this.isSolid(x + r, y + r);
  }
  render(ctx, cam) {
    const t = this.tileSize;
    const x0 = Math.max(0, Math.floor(cam.x / t));
    const y0 = Math.max(0, Math.floor(cam.y / t));
    const x1 = Math.min(this.cols, Math.ceil((cam.x + cam.w) / t));
    const y1 = Math.min(this.rows, Math.ceil((cam.y + cam.h) / t));
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const s = cam.toScreen(x * t, y * t);
        ctx.fillStyle = this.tiles[y][x] === 1 ? '#3a3a44' : '#24331f';
        ctx.fillRect(s.x, s.y, t, t);
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.strokeRect(s.x + 0.5, s.y + 0.5, t, t);
      }
    }
  }
}
"""

# --------------------------------------------------------- public/js/player.js
FILES["public/js/player.js"] = """export class Player {
  constructor(x, y) { this.x = x; this.y = y; this.speed = 220; this.radius = 12; }

  update(dt, input, world) {
    let dx = 0, dy = 0;
    if (input.isDown('KeyW') || input.isDown('ArrowUp'))    dy -= 1;
    if (input.isDown('KeyS') || input.isDown('ArrowDown'))  dy += 1;
    if (input.isDown('KeyA') || input.isDown('ArrowLeft'))  dx -= 1;
    if (input.isDown('KeyD') || input.isDown('ArrowRight')) dx += 1;
    if (!dx && !dy) return;
    const len = Math.hypot(dx, dy); dx /= len; dy /= len;
    const sx = dx * this.speed * dt, sy = dy * this.speed * dt;
    if (!world.isBlocked(this.x + sx, this.y, this.radius)) this.x += sx;
    if (!world.isBlocked(this.x, this.y + sy, this.radius)) this.y += sy;
  }
}
"""

# ------------------------------------------------------------ public/js/net.js
FILES["public/js/net.js"] = """export class Net {
  constructor() {
    this.ws = null;
    this.id = null;
    this.players = new Map();     // id -> {id, name, hue, x, y, tx, ty}
    this.onInit = null;
    this.onDisconnect = null;
  }

  connect(url, name) {
    return new Promise((resolve, reject) => {
      try { this.ws = new WebSocket(url); }
      catch { return reject(new Error('Неверный адрес')); }

      const timeout = setTimeout(() => reject(new Error('Таймаут подключения')), 6000);

      this.ws.onopen = () => {
        this.ws.send(JSON.stringify({ type: 'join', name }));
      };
      this.ws.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('Не удалось подключиться'));
      };
      this.ws.onclose = () => {
        clearTimeout(timeout);
        this.onDisconnect?.();
      };
      this.ws.onmessage = e => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'init') {
          clearTimeout(timeout);
          this.id = msg.id;
          for (const p of msg.players) this.players.set(p.id, { ...p, tx: p.x, ty: p.y });
          this.onInit?.(msg);
          resolve();
        } else {
          this._handle(msg);
        }
      };
    });
  }

  _handle(msg) {
    if (msg.type === 'join') {
      this.players.set(msg.player.id, { ...msg.player, tx: msg.player.x, ty: msg.player.y });
    } else if (msg.type === 'leave') {
      this.players.delete(msg.id);
    } else if (msg.type === 'state') {
      for (const p of msg.players) {
        if (p.id === this.id) continue;
        const local = this.players.get(p.id);
        if (local) { local.tx = p.x; local.ty = p.y; }
      }
    }
  }

  sendState(x, y) {
    if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: 'state', x, y }));
  }
}
"""

# ----------------------------------------------------------- public/js/main.js
FILES["public/js/main.js"] = """import { Input }  from './input.js';
import { Camera } from './camera.js';
import { World }  from './world.js';
import { Player } from './player.js';
import { Net }    from './net.js';

const canvas = document.getElementById('game');
const ctx    = canvas.getContext('2d');

const input  = new Input();
const world  = new World();
const camera = new Camera(canvas.width, canvas.height);
const net    = new Net();

let player = null;
let playing = false;
let sendTimer = 0;

// ---------- меню ----------
const menu    = document.getElementById('menu');
const nameIn  = document.getElementById('name');
const hostIp  = document.getElementById('hostIp');
const playBtn = document.getElementById('playBtn');
const status  = document.getElementById('status');
const hint    = document.getElementById('selfHint');

// подсказки по ситуации
if (location.protocol === 'file:') {
  hostIp.placeholder = 'введи Radmin-IP хоста';
  hint.textContent = 'Файл открыт локально — нужен IP хоста.';
} else if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
  hint.textContent = 'Ты на localhost — оставь поле пустым (ты хост).';
} else {
  hostIp.value = location.hostname;   // друг открыл через Radmin-IP
  hint.textContent = 'Поле уже заполнено — просто нажми «Подключиться».';
}

playBtn.onclick = async () => {
  playBtn.disabled = true;
  status.textContent = 'Подключаемся…';

  const name = nameIn.value.trim() || 'Player';
  const ip   = hostIp.value.trim();

  let url;
  if (!ip) {
    // пусто → подключаемся к тому же хосту, откуда открыта страница
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    url = `${proto}://${location.host}`;
  } else {
    url = `ws://${ip}:3000`;
  }

  net.onDisconnect = () => {
    status.textContent = 'Соединение потеряно';
    playBtn.disabled = false;
    playing = false;
    menu.hidden = false;
  };

  net.onInit = () => {
    const me = net.players.get(net.id);
    player = new Player(me.x, me.y);
    camera.follow(player);
    playing = true;
    menu.hidden = true;
  };

  try {
    await net.connect(url, name);
  } catch (e) {
    status.textContent = 'Ошибка: ' + e.message;
    playBtn.disabled = false;
  }
};

// ---------- апдейт ----------
function update(dt) {
  if (!playing || !player) return;

  player.update(dt, input, world);
  camera.follow(player);

  sendTimer += dt;
  if (sendTimer >= 0.05) {
    sendTimer = 0;
    net.sendState(player.x, player.y);
  }

  for (const p of net.players.values()) {
    if (p.id === net.id) continue;
    p.x += (p.tx - p.x) * 0.25;
    p.y += (p.ty - p.y) * 0.25;
  }
}

// ---------- рендер ----------
function drawPlayer(x, y, name, hue, isSelf) {
  const s = camera.toScreen(x, y);

  ctx.fillStyle = `hsl(${hue} 65% ${isSelf ? 60 : 50}%)`;
  ctx.beginPath();
  ctx.arc(s.x, s.y, 12, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = isSelf ? '#fff' : 'rgba(0,0,0,0.6)';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.font = '12px system-ui';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(0,0,0,0.7)';
  ctx.fillText(name, s.x + 1, s.y - 17);
  ctx.fillStyle = '#fff';
  ctx.fillText(name, s.x, s.y - 18);
}

function render() {
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  world.render(ctx, camera);

  for (const p of net.players.values()) {
    if (p.id === net.id) continue;
    drawPlayer(p.x, p.y, p.name, p.hue, false);
  }

  if (player) {
    const me = net.players.get(net.id);
    drawPlayer(player.x, player.y, me.name, me.hue, true);
  }

  ctx.font = '14px monospace';
  ctx.textAlign = 'left';
  ctx.fillStyle = '#aaa';
  ctx.fillText(`игроков: ${net.players.size}`, 10, 22);
}

// ---------- цикл ----------
let last = performance.now();
function loop(now) {
  const dt = Math.min((now - last) / 1000, 0.05);
  last = now;
  update(dt);
  render();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
"""


def main() -> None:
    root = Path.cwd()
    print(f"Корень проекта: {root}\n")

    # ---------- 1. удаляем старые файлы ----------
    old_items = ["index.html", "style.css", "js"]
    for item in old_items:
        p = root / item
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
                print(f"  удалена папка  {item}/")
            else:
                p.unlink()
                print(f"  удалён файл    {item}")

    # ---------- 2. пишем новые файлы ----------
    print()
    for rel_path, content in FILES.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"  создан  {rel_path}")

    # ---------- 3. что дальше ----------
    print("\nГотово! Следующие шаги:")
    print("  1. npm install")
    print("  2. npm start")
    print("  3. Открой http://localhost:3000 (ты — хост)")
    print("  4. Друг открывает http://<твой-radmin-ip>:3000")
    print("  5. Если что-то не так — смотри раздел «Если не коннектится» в инструкции.")


if __name__ == "__main__":
    main()