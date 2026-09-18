// Панель крафта: кнопки рецептов и еды
function boot() {
  // ждём готовность gameApi (main.js)
  if (!window.gameApi) {
    setTimeout(boot, 100);
    return;
  }
  // контейнер панели
  const panel = document.createElement('div');
  panel.id = 'craftPanel';
  panel.style.position = 'fixed';
  panel.style.right = '10px';
  panel.style.top = '170px';
  panel.style.display = 'flex';
  panel.style.flexDirection = 'column';
  panel.style.gap = '6px';
  // helper для тёмных кнопок
  function mkBtn(label, onClick) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.background = 'rgba(0,0,0,0.7)';
    b.style.color = '#fff';
    b.style.border = '1px solid #666';
    b.style.fontSize = '12px';
    b.style.fontFamily = 'monospace';
    b.style.padding = '6px 10px';
    b.style.cursor = 'pointer';
    b.addEventListener('click', onClick);
    return b;
  }
  // рецепт кирпича
  panel.appendChild(mkBtn('Кирпич (2 камня/3 носков)', () => {
    window.gameApi.sendCraft('brick');
  }));
  // рецепт аптечки
  panel.appendChild(mkBtn('Аптечка (2 сыра+курага)', () => {
    window.gameApi.sendCraft('medkit');
  }));
  // быстро съесть еду
  panel.appendChild(mkBtn('Съесть (E)', () => {
    window.gameApi.sendEat();
  }));
  document.body.appendChild(panel);
  // клавиша C — показать/скрыть панель
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyC' && !e.repeat) {
      panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
    }
  });
}

boot();
