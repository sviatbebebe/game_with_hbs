// Окно крафта по центру экрана, клавиша С (KeyC)
function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  // затемнение фона
  const overlay = document.createElement('div');
  overlay.id = 'craftOverlay';
  overlay.style.position = 'fixed';
  overlay.style.inset = '0';
  overlay.style.display = 'none';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.style.background = 'rgba(0,0,0,0.55)';
  overlay.style.zIndex = '30';

  const win = document.createElement('div');
  win.style.width = '380px';
  win.style.maxWidth = '92vw';
  win.style.background = '#1a1a1a';
  win.style.border = '1px solid #444';
  win.style.borderRadius = '10px';
  win.style.padding = '16px';
  win.style.fontFamily = 'monospace';
  win.style.color = '#eee';

  const title = document.createElement('div');
  title.style.display = 'flex';
  title.style.justifyContent = 'space-between';
  title.style.alignItems = 'center';
  title.style.marginBottom = '12px';
  const h = document.createElement('div');
  h.textContent = 'Крафт (С — закрыть)';
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
  closeBtn.addEventListener('click', hide);
  title.appendChild(h);
  title.appendChild(closeBtn);
  win.appendChild(title);

  const invLine = document.createElement('div');
  invLine.id = 'craftInv';
  invLine.style.fontSize = '12px';
  invLine.style.color = '#aaa';
  invLine.style.marginBottom = '12px';
  win.appendChild(invLine);

  function mkRow(name, desc, onCraft) {
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.justifyContent = 'space-between';
    row.style.alignItems = 'center';
    row.style.gap = '8px';
    row.style.padding = '8px';
    row.style.marginBottom = '8px';
    row.style.background = '#222';
    row.style.border = '1px solid #333';
    row.style.borderRadius = '6px';
    const left = document.createElement('div');
    const t1 = document.createElement('div');
    t1.textContent = name;
    t1.style.fontSize = '14px';
    const t2 = document.createElement('div');
    t2.textContent = desc;
    t2.style.fontSize = '12px';
    t2.style.color = '#888';
    left.appendChild(t1);
    left.appendChild(t2);
    const b = document.createElement('button');
    b.textContent = 'Скрафтить';
    b.style.background = '#2ecc71';
    b.style.border = '1px solid #27ae60';
    b.style.color = '#111';
    b.style.fontWeight = 'bold';
    b.style.borderRadius = '6px';
    b.style.padding = '8px 12px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', onCraft);
    row.appendChild(left);
    row.appendChild(b);
    return row;
  }

  win.appendChild(mkRow('Кирпич', '2 камня или 3 носков', () => window.gameApi.sendCraft('brick')));
  win.appendChild(mkRow('Аптечка', '2 сыра + 1 курага', () => window.gameApi.sendCraft('medkit')));
  win.appendChild(mkRow('Печь', '10 кирпичей, ставится G+ЛКМ 2x2', () => window.gameApi.sendCraft('furnace')));

  const eatRow = document.createElement('div');
  eatRow.style.display = 'flex';
  eatRow.style.gap = '8px';
  eatRow.style.marginTop = '8px';
  function mkSmall(label, fn) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.flex = '1';
    b.style.background = '#2c3e50';
    b.style.color = '#eee';
    b.style.border = '1px solid #34495e';
    b.style.borderRadius = '6px';
    b.style.padding = '8px';
    b.style.cursor = 'pointer';
    b.style.fontFamily = 'monospace';
    b.addEventListener('click', fn);
    return b;
  }
  eatRow.appendChild(mkSmall('Съесть (E)', () => window.gameApi.sendEat()));
  eatRow.appendChild(mkSmall('Кирпич-стена: F+ЛКМ', () => hide()));
  win.appendChild(eatRow);

  const hint = document.createElement('div');
  hint.style.fontSize = '11px';
  hint.style.color = '#666';
  hint.style.marginTop = '10px';
  hint.textContent = 'Печка: скрафти, встань рядом, G+ЛКМ — поставить. E рядом с печкой — открыть плавильню.';
  win.appendChild(hint);

  overlay.appendChild(win);
  document.body.appendChild(overlay);

  function refreshInv() {
    const p = window.gameApi.getLocalPlayer();
    if (!p) { invLine.textContent = ''; return; }
    const inv = p.inventory || {};
    const parts = Object.entries(inv).map(([k, v]) => k + ': ' + v);
    invLine.textContent = parts.length ? 'Инвентарь: ' + parts.join(', ') : 'Инвентарь пуст';
  }

  function show() {
    overlay.style.display = 'flex';
    refreshInv();
  }
  function hide() {
    overlay.style.display = 'none';
  }
  function toggle() {
    if (overlay.style.display === 'none' || !overlay.style.display) show();
    else hide();
  }

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) hide();
  });
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyC' && !e.repeat) {
      // не открывать из лобби и из полей ввода
      if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
      toggle();
    }
    if (e.code === 'Escape') hide();
  });

  setInterval(() => {
    if (overlay.style.display === 'flex') refreshInv();
  }, 500);

  window.craftUi = { show, hide, toggle };
}

boot();
