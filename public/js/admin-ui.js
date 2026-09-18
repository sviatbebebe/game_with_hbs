// Панель админа (только хост, сервер проверяет).
// Клавиша P — открыть/закрыть. Урон, скорость, уровень, бессмертие, предметы, спавн.
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const overlay = document.createElement('div');
  overlay.id = 'adminOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '33';

  const win = document.createElement('div');
  win.style.width = '400px';
  win.style.maxWidth = '94vw';
  win.style.maxHeight = '90vh';
  win.style.overflowY = 'auto';
  win.style.background = '#140f0f';
  win.style.border = '1px solid #e74c3c';
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
  h.textContent = 'Панель админа (P)';
  h.style.fontSize = '16px';
  h.style.fontWeight = 'bold';
  h.style.color = '#e74c3c';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.style.background = '#333';
  closeBtn.style.color = '#eee';
  closeBtn.style.border = '1px solid #555';
  closeBtn.style.borderRadius = '6px';
  closeBtn.style.cursor = 'pointer';
  closeBtn.style.padding = '4px 10px';
  closeBtn.addEventListener('click', hide);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const note = document.createElement('div');
  note.id = 'adminNote';
  note.style.fontSize = '12px';
  note.style.color = '#888';
  note.style.marginBottom = '10px';
  win.appendChild(note);

  function field(label, inputEl) {
    const wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.gap = '8px';
    wrap.style.alignItems = 'center';
    wrap.style.marginBottom = '8px';
    const l = document.createElement('div');
    l.textContent = label;
    l.style.flex = '0 0 130px';
    l.style.fontSize = '12px';
    inputEl.style.flex = '1';
    inputEl.style.background = '#222';
    inputEl.style.color = '#eee';
    inputEl.style.border = '1px solid #444';
    inputEl.style.borderRadius = '6px';
    inputEl.style.padding = '6px 8px';
    inputEl.style.fontFamily = 'monospace';
    wrap.appendChild(l);
    wrap.appendChild(inputEl);
    return wrap;
  }
  function mkBtn(label, fn, accent) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.background = accent ? '#e74c3c' : '#2c3e50';
    b.style.color = '#fff';
    b.style.border = '1px solid ' + (accent ? '#c0392b' : '#34495e');
    b.style.borderRadius = '6px';
    b.style.padding = '7px 10px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.style.fontSize = '12px';
    b.style.marginBottom = '8px';
    b.style.width = '100%';
    b.addEventListener('click', fn);
    return b;
  }

  const dmgInput = document.createElement('input');
  dmgInput.type = 'number'; dmgInput.min = '1'; dmgInput.max = '20'; dmgInput.step = '0.5'; dmgInput.value = '1';
  win.appendChild(field('Урон x (1-20)', dmgInput));
  const spdInput = document.createElement('input');
  spdInput.type = 'number'; spdInput.min = '1'; spdInput.max = '10'; spdInput.step = '0.5'; spdInput.value = '1';
  win.appendChild(field('Скорость x (1-10)', spdInput));
  win.appendChild(mkBtn('Применить урон/скорость', () => {
    window.gameApi.sendAdminSet(dmgInput.value, spdInput.value);
  }));

  const lvInput = document.createElement('input');
  lvInput.type = 'number'; lvInput.min = '1'; lvInput.max = '50'; lvInput.value = '10';
  win.appendChild(field('Уровень (1-50)', lvInput));
  win.appendChild(mkBtn('Выдать уровень', () => {
    window.gameApi.sendAdminLevel(lvInput.value);
  }));

  const godLabel = document.createElement('label');
  godLabel.style.display = 'flex';
  godLabel.style.gap = '8px';
  godLabel.style.alignItems = 'center';
  godLabel.style.fontSize = '13px';
  godLabel.style.marginBottom = '8px';
  const godBox = document.createElement('input');
  godBox.type = 'checkbox';
  godBox.addEventListener('change', () => window.gameApi.sendAdminGod(godBox.checked));
  godLabel.appendChild(godBox);
  const gt = document.createElement('span');
  gt.textContent = 'Бессмертие';
  godLabel.appendChild(gt);
  win.appendChild(godLabel);

  const itemSel = document.createElement('select');
  const countInput = document.createElement('input');
  countInput.type = 'number'; countInput.min = '1'; countInput.max = '99'; countInput.value = '10';
  countInput.style.maxWidth = '70px';
  const itemRow = document.createElement('div');
  itemRow.style.display = 'flex';
  itemRow.style.gap = '8px';
  itemRow.style.marginBottom = '8px';
  itemSel.style.flex = '1';
  itemSel.style.background = '#222';
  itemSel.style.color = '#eee';
  itemSel.style.border = '1px solid #444';
  itemSel.style.borderRadius = '6px';
  itemSel.style.padding = '6px 8px';
  itemSel.style.fontFamily = 'monospace';
  itemRow.appendChild(itemSel);
  itemRow.appendChild(countInput);
  win.appendChild(itemRow);
  win.appendChild(mkBtn('Выдать предмет', () => {
    window.gameApi.sendAdminGive(itemSel.value, countInput.value);
  }));

  const mobSel = document.createElement('select');
  mobSel.style.width = '100%';
  mobSel.style.background = '#222';
  mobSel.style.color = '#eee';
  mobSel.style.border = '1px solid #444';
  mobSel.style.borderRadius = '6px';
  mobSel.style.padding = '6px 8px';
  mobSel.style.fontFamily = 'monospace';
  mobSel.style.marginBottom = '8px';
  const mobCount = document.createElement('input');
  mobCount.type = 'number'; mobCount.min = '1'; mobCount.max = '50'; mobCount.value = '5';
  const mobRow = document.createElement('div');
  mobRow.style.display = 'flex';
  mobRow.style.gap = '8px';
  mobRow.style.marginBottom = '0';
  mobSel.style.flex = '1';
  mobCount.style.maxWidth = '70px';
  mobCount.style.background = '#222';
  mobCount.style.color = '#eee';
  mobCount.style.border = '1px solid #444';
  mobCount.style.borderRadius = '6px';
  mobCount.style.padding = '6px 8px';
  mobCount.style.fontFamily = 'monospace';
  mobRow.appendChild(mobSel);
  mobRow.appendChild(mobCount);
  win.appendChild(mobRow);
  for (const t of ['melee', 'ranged', 'wanderer']) {
    const o = document.createElement('option');
    o.value = t; o.textContent = t;
    mobSel.appendChild(o);
  }
  win.appendChild(mkBtn('Заспавнить врагов рядом', () => {
    window.gameApi.sendAdminSpawn(mobSel.value, mobCount.value);
  }, true));

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  // список предметов подтягиваем из init
  let itemsLoaded = false;
  function loadItems() {
    if (itemsLoaded) return;
    const net = window.gameApi.getNet ? window.gameApi.getNet() : null;
    const items = net && net.items ? net.items : null;
    if (!items || !Object.keys(items).length) return;
    itemsLoaded = true;
    for (const [id, meta] of Object.entries(items)) {
      const o = document.createElement('option');
      o.value = id;
      o.textContent = (meta.name || id) + ' (' + id + ')';
      itemSel.appendChild(o);
    }
  }

  function refresh() {
    const host = window.gameApi.isHost ? window.gameApi.isHost() : false;
    const p = window.gameApi.getLocalPlayer();
    note.textContent = host ? 'Ты хост. Команды применятся.' : 'Ты НЕ хост — сервер отклонит команды.';
    if (p) {
      if (document.activeElement !== dmgInput) dmgInput.value = p.adminDamage || 1;
      if (document.activeElement !== spdInput) spdInput.value = p.adminSpeed || 1;
      godBox.checked = !!p.god;
    }
    loadItems();
  }
  function show() { overlay.style.display = 'flex'; refresh(); }
  function hide() { overlay.style.display = 'none'; }
  function toggle() {
    if (overlay.style.display === 'flex') hide();
    else show();
  }

  overlay.addEventListener('click', (e) => { if (e.target === overlay) hide(); });
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyP' && !e.repeat) {
      if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
      if (document.activeElement && document.activeElement.tagName === 'SELECT') return;
      toggle();
    }
    if (e.code === 'Escape' && overlay.style.display === 'flex') hide();
  });

  setInterval(() => { if (overlay.style.display === 'flex') refresh(); }, 1000);

  window.adminUi = { show, hide, toggle };
}

boot();
