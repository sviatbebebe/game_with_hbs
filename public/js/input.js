export class Input {
  constructor() {
    this.keys = new Set();
    window.addEventListener('keydown', e => this.keys.add(e.code));
    window.addEventListener('keyup',   e => this.keys.delete(e.code));
  }
  isDown(code) { return this.keys.has(code); }
}
