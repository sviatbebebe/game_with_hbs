export class Net {
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
