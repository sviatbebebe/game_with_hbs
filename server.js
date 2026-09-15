import { WebSocketServer } from 'ws';
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
