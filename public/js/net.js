export class Net {
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
