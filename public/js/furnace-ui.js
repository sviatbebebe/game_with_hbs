// Интерфейс печки: E рядом с печкой открывает окно.
// Слоты: топливо (уголь), руды (железо/медь/олово), выход (слитки).
// Олово 3с, медь 4с, железо 5с, 1 уголь = 4 руды.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'furnaceOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '31';

  const win = document.createElement('div');
  win.style.width = '400px';
  win.style.maxWidth = '94vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #a05a00';
  win.style.borderRadius = '10px';
  win.style.padding = '16px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';

  const title = document.createElement('div');
  title.style.display = 'flex';
  title.style.justifyContent = 'space-between';
  title.style.alignItems = 'center';
  title.style.marginBottom = '10px';
  const h = document.createElement('div');
  h.id = 'furnaceTitle';
  h.textContent = 'Печь';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.style.background = '#333';
  closeBtn.style.color = '#eee';
  closeBtn.style.border = '1px solid #555';
  closeBtn.style.borderRadius = '6px';
  closeBtn.style.cursor = 'pointer';
  closeBtn.style.padding = '4px 10px';
  closeBtn.addEventListener('click', close);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const status = document.createElement('div');
  status.id = 'furnaceStatus';
  status.style.fontSize = '13px';
  status.style.marginBottom = '10px';
  status.style.whiteSpace = 'pre-line';
  win.appendChild(status);

  const barWrap = document.createElement('div');
  barWrap.style.height = '10px';
  barWrap.style.background = '#000';
  barWrap.style.border = '1px solid #444';
  barWrap.style.borderRadius = '4px';
  barWrap.style.marginBottom = '12px';
  const bar = document.createElement('div');
  bar.style.height = '100%';
  bar.style.width = '0%';
  bar.style.background = '#f39c12';
  barWrap.appendChild(bar);
  win.appendChild(barWrap);

  function mkBtn(label, fn) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.background = '#2c3e50';
    b.style.color = '#eee';
    b.style.border = '1px solid #34495e';
    b.style.borderRadius = '6px';
    b.style.padding = '7px 8px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.style.fontSize = '12px';
    b.addEventListener('click', fn);
    return b;
  }

  const grid = document.createElement('div');
  grid.style.display = 'flex';
  grid.style.flexDirection = 'column';
  grid.style.gap = '6px';

  const row1 = document.createElement('div');
  row1.style.display = 'flex';
  row1.style.gap = '6px';
  row1.appendChild(mkBtn('+1 уголь', () => put('coal', 1)));
  row1.appendChild(mkBtn('Весь уголь', () => putAll('coal')));
  grid.appendChild(row1);

  const row2 = document.createElement('div');
  row2.style.display = 'flex';
  row2.style.gap = '6px';
  row2.appendChild(mkBtn('+1 железо', () => put('iron_ore', 1)));
  row2.appendChild(mkBtn('+1 медь', () => put('copper_ore', 1)));
  row2.appendChild(mkBtn('+1 олово', () => put('tin_ore', 1)));
  grid.appendChild(row2);

  const row3 = document.createElement('div');
  row3.style.display = 'flex';
  row3.style.gap = '6px';
  row3.appendChild(mkBtn('Вся руда', putAllOres));
  const takeBtn = mkBtn('Забрать слитки', take);
  takeBtn.style.background = '#27ae60';
  takeBtn.style.borderColor = '#1e8449';
  takeBtn.style.color = '#fff';
  takeBtn.style.fontWeight = 'bold';
  row3.appendChild(takeBtn);
  grid.appendChild(row3);

  win.appendChild(grid);

  const hint = document.createElement('div');
  hint.style.fontSize = '11px';
  hint.style.color = '#888';
  hint.style.marginTop = '10px';
  hint.textContent = 'Олово 3с, медь 4с, железо 5с. 1 уголь = 4 руды. E или Esc — закрыть.';
  win.appendChild(hint);

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  let currentId = null;

  function getFurnace() {
    if (currentId == null) return null;
    const list = window.gameApi.getFurnaces();
    return list.find((f) => f.id === currentId) || null;
  }
  function put(item, count) {
    if (currentId == null) return;
    window.gameApi.sendFurnacePut(currentId, item, count);
  }
  function putAll(item) {
    const p = window.gameApi.getLocalPlayer();
    if (!p || !p.inventory) return;
    const n = p.inventory[item] || 0;
    if (n > 0) put(item, n);
  }
  function putAllOres() {
    const p = window.gameApi.getLocalPlayer();
    if (!p || !p.inventory) return;
    for (const k of ['iron_ore', 'copper_ore', 'tin_ore']) {
      const n = p.inventory[k] || 0;
      if (n > 0) window.gameApi.sendFurnacePut(currentId, k, n);
    }
  }
  function take() {
    if (currentId == null) return;
    window.gameApi.sendFurnaceTake(currentId);
  }
  function open(id) {
    currentId = id;
    overlay.style.display = 'flex';
    refresh();
  }
  function close() {
    overlay.style.display = 'none';
    currentId = null;
    window._furnaceClosedAt = Date.now();
  }
  function refresh() {
    const f = getFurnace();
    if (!f) {
      // печка пропала (выход в лобби)
      if (overlay.style.display === 'flex' && currentId != null) {
        status.textContent = 'Печь недоступна.';
      }
      return;
    }
    document.getElementById('furnaceTitle').textContent = 'Печь #' + f.id + ' (2x2)';
    const sm = f.smelting
      ? 'Плавится: ' + f.smelting.type + ' (' + Math.ceil(f.smelting.remaining / 1000) + 'с)'
      : 'Простаивает';
    status.textContent =
      'Уголь в печи: ' + (f.coal || 0) + '  |  Заряды: ' + (f.charges || 0) + '\n' +
      'Руда — железо: ' + (f.ores.iron_ore || 0) + ', медь: ' + (f.ores.copper_ore || 0) + ', олово: ' + (f.ores.tin_ore || 0) + '\n' +
      'Слитки — железо: ' + (f.ingots.iron_ingot || 0) + ', медь: ' + (f.ingots.copper_ingot || 0) + ', олово: ' + (f.ingots.tin_ingot || 0) + '\n' +
      sm;
    if (f.smelting && f.smelting.total) {
      const r = 1 - f.smelting.remaining / f.smelting.total;
      bar.style.width = (Math.max(0, Math.min(1, r)) * 100) + '%';
    } else {
      bar.style.width = '0%';
    }
  }

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });
  window.addEventListener('keydown', (e) => {
    if ((e.code === 'Escape' || e.code === 'KeyE') && overlay.style.display === 'flex' && !e.repeat) {
      // E закрывает только если окно уже открыто, чтобы не мешать поеданию
      if (e.code === 'Escape') close();
      else {
        // E при открытом окне — закрыть, а не открывать новое
        e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
        e.preventDefault();
        close();
      }
    }
  }, true);

  setInterval(() => {
    if (overlay.style.display === 'flex') refresh();
  }, 250);

  function isOpen() {
    return overlay.style.display === 'flex';
  }

  window.furnaceUi = { open, close, isOpen };
}

boot();
