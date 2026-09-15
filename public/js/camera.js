export class Camera {
  constructor(w, h) { this.w = w; this.h = h; this.x = 0; this.y = 0; }
  follow(t) { this.x = t.x - this.w / 2; this.y = t.y - this.h / 2; }
  toScreen(x, y) { return { x: x - this.x, y: y - this.y }; }
}
