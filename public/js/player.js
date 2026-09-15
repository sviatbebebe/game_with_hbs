export class Player {
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
