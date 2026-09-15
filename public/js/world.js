const SEED = 12345;
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
