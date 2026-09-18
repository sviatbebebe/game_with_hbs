// Выбор модификатора выстрела на 10 уровне.
// Дробь x5: 5 пуль, интервал 1с. Скорострел: быстрый огонь с зажатой ЛКМ.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'modOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.6)';
  overlay.style.zIndex = '32';

  const win = document.createElement('div');
  win.style.width = '420px';
  win.style.maxWidth = '94vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #f1c40f';
  win.style.borderRadius = '10px';
  win.style.padding = '18px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';
  win.style.textAlign = 'center';

  const h = document.createElement('div');
  h.textContent = '10 уровень! Выбери модификатор выстрела';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  h.style.marginBottom = '6px';
  win.appendChild(h);

  const sub = document.createElement('div');
  sub.textContent = 'Выбор навсегда для этой игры. Магазин: 10 патронов, перезарядка 3с.';
  sub.style.fontSize = '12px';
  sub.style.color = '#888';
  sub.style.marginBottom = '14px';
  win.appendChild(sub);

  const row = document.createElement('div');
  row.style.display = 'flex';
  row.style.gap = '10px';

  function card(title, desc, mod, color) {
    const c = document.createElement('div');
    c.style.flex = '1';
    c.style.background = '#222';
    c.style.border = '1px solid #444';
    c.style.borderRadius = '8px';
    c.style.padding = '12px';
    const t = document.createElement('div');
    t.textContent = title;
    t.style.fontSize = '15px';
    t.style.fontWeight = 'bold';
    t.style.color = color;
    t.style.marginBottom = '6px';
    const d = document.createElement('div');
    d.textContent = desc;
    d.style.fontSize = '12px';
    d.style.color = '#aaa';
    d.style.marginBottom = '10px';
    d.style.whiteSpace = 'pre-line';
    const b = document.createElement('button');
    b.textContent = 'Выбрать';
    b.style.background = color;
    b.style.color = '#111';
    b.style.fontWeight = 'bold';
    b.style.border = 'none';
    b.style.borderRadius = '6px';
    b.style.padding = '8px 14px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', () => {
      window.gameApi.sendChooseMod(mod);
      hide();
    });
    c.appendChild(t);
    c.appendChild(d);
    c.appendChild(b);
    return c;
  }

  row.appendChild(card('Дробь x5', '5 пуль за выстрел\nинтервал 1 секунда', 'shotgun', '#f39c12'));
  row.appendChild(card('Скорострел', 'быстрый огонь\nстрельба с зажатой ЛКМ', 'rapid', '#2ecc71'));
  win.appendChild(row);
  overlay.appendChild(win);
  document.body.appendChild(overlay);

  let dismissed = false;
  function show() {
    if (dismissed) return;
    overlay.style.display = 'flex';
  }
  function hide() {
    overlay.style.display = 'none';
    dismissed = true;
  }

  setInterval(() => {
    const p = window.gameApi.getLocalPlayer();
    if (!p) return;
    if ((p.level || 1) >= 10 && !p.shotMod && !dismissed) {
      if (overlay.style.display !== 'flex') show();
    } else if (p.shotMod && overlay.style.display === 'flex') {
      hide();
    }
  }, 500);

  window.modUi = { show, hide };
}

boot();
