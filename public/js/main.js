import { Input }  from './input.js';
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
