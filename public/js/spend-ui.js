const STATS = [
  { key: 'maxHp', label: '+Здоровье(1)', digit: '1' },
  { key: 'damage', label: '+Урон(2)', digit: '2' },
  { key: 'speed', label: '+Скорость(3)', digit: '3' },
];

function boot() {
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  const panel = document.createElement('div');
  panel.id = 'spendPanel';
  panel.style.position = 'fixed';
  panel.style.right = '10px';
  panel.style.top = '10px';
  panel.style.display = 'none';
  panel.style.gap = '6px';
  for (const s of STATS) {
    const b = document.createElement('button');
    b.textContent = s.label;
    b.style.background = 'rgba(0,0,0,0.7)';
    b.style.color = '#fff';
    b.style.border = '1px solid #666';
    b.style.fontSize = '12px';
    b.style.fontFamily = 'monospace';
    b.style.padding = '6px 10px';
    b.style.cursor = 'pointer';
    b.addEventListener('click', () => {
      window.gameApi.sendSpendPoint(s.key);
    });
    panel.appendChild(b);
  }
  document.body.appendChild(panel);
  window.addEventListener('keydown', (e) => {
    if (e.repeat) {
      return;
    }
    for (const s of STATS) {
      if (e.key === s.digit) {
        window.gameApi.sendSpendPoint(s.key);
        break;
      }
    }
  });
  setInterval(() => {
    const p = window.gameApi.getLocalPlayer();
    const pts = p ? p.points || 0 : 0;
    panel.style.display = pts > 0 ? 'flex' : 'none';
  }, 500);
}

boot();
