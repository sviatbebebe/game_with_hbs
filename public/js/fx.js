// Минимальные спецэффекты выстрелов: вспышка у дула и искры попаданий.
// Без аллокаций в горячем пути сверх меры, лимит частиц.
export class Fx {
  constructor() {
    this.parts = [];
    this.max = 400;
  }
  _push(p) {
    if (this.parts.length >= this.max) this.parts.shift();
    this.parts.push(p);
  }
  // вспышка выстрела: несколько искр вдоль угла + короткая вспышка
  muzzle(x, y, angle, color, big) {
    const n = big ? 7 : 4;
    for (let i = 0; i < n; i++) {
      const sp = 120 + Math.random() * (big ? 260 : 160);
      const a = angle + (Math.random() - 0.5) * 0.6;
      this._push({
        x, y,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
        life: 0, maxLife: 0.12 + Math.random() * 0.1,
        size: 2 + Math.random() * 2, color,
      });
    }
    this._push({ x, y, vx: 0, vy: 0, life: 0, maxLife: 0.08, size: big ? 12 : 8, color: '#fff', flash: true });
  }
  // попадание: радиальные искры
  impact(x, y, color) {
    for (let i = 0; i < 6; i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 60 + Math.random() * 160;
      this._push({
        x, y,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
        life: 0, maxLife: 0.2 + Math.random() * 0.15,
        size: 1.5 + Math.random() * 2, color,
      });
    }
  }
  update(dt) {
    const ps = this.parts;
    for (let i = ps.length - 1; i >= 0; i--) {
      const p = ps[i];
      p.life += dt;
      if (p.life >= p.maxLife) { ps.splice(i, 1); continue; }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.vx *= 0.9;
      p.vy *= 0.9;
    }
  }
  draw(ctx, ox, oy) {
    for (const p of this.parts) {
      const a = 1 - p.life / p.maxLife;
      ctx.globalAlpha = Math.max(0, a);
      ctx.fillStyle = p.color;
      const sx = p.x + ox, sy = p.y + oy;
      if (p.flash) {
        ctx.beginPath();
        ctx.arc(sx, sy, p.size * a, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillRect(sx - p.size / 2, sy - p.size / 2, p.size, p.size);
      }
    }
    ctx.globalAlpha = 1;
  }
}
