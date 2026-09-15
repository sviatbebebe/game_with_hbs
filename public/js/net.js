export class Net {
  constructor() {
    this.id = null;
    this.hostId = null;
    this.gameState = 'lobby';
    this.players = new Map();
    this.enemies = new Map();
    this.projectiles = new Map();
    this.map = null;
    this.items = {};
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
      this.items = msg.items || {};
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
  sendMelee(angle) { this._send({ type: 'melee', angle }); }
}
