const DEFAULT_BOARD_WIDTH = 11;
const DEFAULT_BOARD_HEIGHT = 11;

const appState = {
  cards: [],
  roomCode: null,
  match: null,
  selectedHandIndex: null,
  selectedUnitId: null,
};

const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

function setStatus(message, isError = false) {
  const status = $('#auth-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('status-error', isError);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `Error HTTP ${response.status}`);
  return data;
}

function localSeedCards() {
  const seedTag = document.getElementById('cards-seed');
  if (!seedTag) return [];
  try {
    const parsed = JSON.parse(seedTag.textContent || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function renderCatalog() {
  const catalogEl = $('#catalog');
  if (!catalogEl) return;
  const filter = familyFilter?.value || '';
  const cards = appState.cards.filter((card) => !filter || card.family === filter);
  catalogEl.innerHTML = cards.map((card) => `
    <article class="card">
      <img src="${card.image}" alt="${card.name}" />
      <h4>${card.name}</h4>
      <div class="meta">
        <span class="badge">${card.family}</span>
        <span class="badge">${card.stage}</span>
        <span class="badge">Niv ${card.level_min}-${card.level_max}</span>
      </div>
      <p>${card.description || ''}</p>
    </article>
  `).join('') || '<div class="small">No hay cartas disponibles.</div>';
}

function resolveSides() {
  if (!appState.match) return { me: null, enemy: null, mySide: null };
  return { me: appState.match.host, enemy: appState.match.guest, mySide: 'host' };
}

function findUnitAt(units = [], x, y) {
  return units.find((u) => u.x === x && u.y === y);
}

function isMyTurn(mySide) {
  return Boolean(appState.match && mySide && appState.match.turn?.active_side === mySide);
}

function deploymentCellsForSide(side, boardWidth, boardHeight) {
  if (!side) return new Set();
  const middleX = Math.floor(boardWidth / 2);
  if (side === 'host') {
    return new Set([`${middleX},0`, `${middleX - 1},1`, `${middleX},1`, `${middleX + 1},1`, `${middleX},2`]);
  }
  return new Set([
    `${middleX},${boardHeight - 1}`,
    `${middleX - 1},${boardHeight - 2}`,
    `${middleX},${boardHeight - 2}`,
    `${middleX + 1},${boardHeight - 2}`,
    `${middleX},${boardHeight - 3}`,
  ]);
}

function computeMoveTargets(selectedUnit, meUnits, enemyUnits) {
  if (!selectedUnit || selectedUnit.pm_current <= 0 || !selectedUnit.can_move) return new Set();
  const occupied = new Set([...meUnits, ...enemyUnits].map((u) => `${u.x},${u.y}`));
  const targets = new Set();
  for (let dx = -selectedUnit.pm_current; dx <= selectedUnit.pm_current; dx += 1) {
    for (let dy = -selectedUnit.pm_current; dy <= selectedUnit.pm_current; dy += 1) {
      const dist = Math.abs(dx) + Math.abs(dy);
      if (dist === 0 || dist > selectedUnit.pm_current) continue;
      const x = selectedUnit.x + dx;
      const y = selectedUnit.y + dy;
      if (occupied.has(`${x},${y}`)) continue;
      targets.add(`${x},${y}`);
    }
  }
  return targets;
}

function computeAttackTargets(selectedUnit, enemyUnits) {
  if (!selectedUnit || selectedUnit.pa_current <= 0 || !selectedUnit.can_act) return new Set();
  const baseRange = selectedUnit.card.stage === 'base' ? 1 : 2;
  const attackRange = Math.min(5, baseRange + Math.floor(selectedUnit.card.action_points / 2));
  return new Set(enemyUnits
    .filter((enemy) => Math.abs(enemy.x - selectedUnit.x) + Math.abs(enemy.y - selectedUnit.y) <= attackRange)
    .map((enemy) => enemy.id));
}

function renderStaticBoard() {
  const boardEl = $('#board');
  if (!boardEl) return;
  const cells = [];
  for (let y = 0; y < DEFAULT_BOARD_HEIGHT; y += 1) {
    for (let x = 0; x < DEFAULT_BOARD_WIDTH; x += 1) {
      const squareClass = (x + y) % 2 === 0 ? 'square-light' : 'square-dark';
      cells.push(`<div class="cell ${squareClass} empty preview-cell"><div class="small"></div></div>`);
    }
  }
  boardEl.style.gridTemplateColumns = `repeat(${DEFAULT_BOARD_WIDTH}, minmax(40px, 1fr))`;
  boardEl.innerHTML = cells.join('');
}

async function sendAction(actionPayload) {
  const data = await api(`/api/match/${appState.roomCode}/action/`, {
    method: 'POST',
    body: JSON.stringify(actionPayload),
  });
  appState.match = data.match;
  renderBoard();
}

async function onCellClick(x, y) {
  if (!appState.match || !appState.roomCode) return;
  const { me, enemy, mySide } = resolveSides();
  if (!me || !enemy || !isMyTurn(mySide)) return;

  const myUnit = findUnitAt(me.units || [], x, y);
  const enemyUnit = findUnitAt(enemy.units || [], x, y);
  const selectedHandCard = me.hand?.[appState.selectedHandIndex] || null;
  const selectedUnit = (me.units || []).find((u) => u.id === appState.selectedUnitId) || null;

  if (myUnit) {
    appState.selectedUnitId = myUnit.id;
    appState.selectedHandIndex = null;
    renderBoard();
    return;
  }
  if (selectedHandCard) {
    await sendAction({ action: 'summon', hand_index: appState.selectedHandIndex, x, y });
    appState.selectedHandIndex = null;
    return;
  }
  if (!selectedUnit) return;

  if (enemyUnit) {
    const attackTargets = computeAttackTargets(selectedUnit, enemy.units || []);
    if (!attackTargets.has(enemyUnit.id)) return;
    await sendAction({ action: 'attack', attacker_id: selectedUnit.id, target_id: enemyUnit.id });
    return;
  }

  const moveTargets = computeMoveTargets(selectedUnit, me.units || [], enemy.units || []);
  if (!moveTargets.has(`${x},${y}`)) return;
  await sendAction({ action: 'move', unit_id: selectedUnit.id, to_x: x, to_y: y });
}

function renderBoard() {
  if (!appState.match) {
    renderStaticBoard();
    $('#hand').innerHTML = '<div class="small">Tu mano aparecerá acá.</div>';
    $('#match-summary').innerHTML = '<div class="small">Iniciá una partida contra la IA para comenzar.</div>';
    $('#unit-list').innerHTML = '<div class="small">Sin unidades.</div>';
    return;
  }

  const { me, enemy, mySide } = resolveSides();
  const width = appState.match.board?.width || DEFAULT_BOARD_WIDTH;
  const height = appState.match.board?.height || DEFAULT_BOARD_HEIGHT;
  const selectedUnit = me?.units?.find((u) => u.id === appState.selectedUnitId) || null;
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  const moveTargets = computeMoveTargets(selectedUnit, me?.units || [], enemy?.units || []);
  const attackTargets = computeAttackTargets(selectedUnit, enemy?.units || []);
  const myDeployment = deploymentCellsForSide(mySide, width, height);
  const enemyDeployment = deploymentCellsForSide('guest', width, height);

  const cells = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const ownUnit = findUnitAt(me?.units, x, y);
      const enemyUnit = findUnitAt(enemy?.units, x, y);
      const unit = ownUnit || enemyUnit;
      const squareClass = (x + y) % 2 === 0 ? 'square-light' : 'square-dark';
      const key = `${x},${y}`;
      const canSummon = Boolean(selectedHandCard) && myDeployment.has(key) && !unit && isMyTurn(mySide);
      const canMove = moveTargets.has(key) && isMyTurn(mySide);
      const canAttack = enemyUnit && attackTargets.has(enemyUnit.id) && isMyTurn(mySide);
      const deployClass = myDeployment.has(key) ? 'deploy-ally' : (enemyDeployment.has(key) ? 'deploy-enemy' : '');
      const hintClass = canSummon ? 'hint-summon' : (canMove ? 'hint-move' : (canAttack ? 'hint-attack' : ''));

      cells.push(`
        <button class="cell ${squareClass} ${ownUnit ? 'ally' : enemyUnit ? 'enemy' : 'empty'} ${deployClass} ${hintClass}" data-x="${x}" data-y="${y}">
          ${unit
            ? `<div class="token"><strong>${unit.card.name}</strong><span>PdV ${unit.hp_current}</span><span>PA ${unit.pa_current} · PM ${unit.pm_current}</span></div>`
            : '<div class="small"></div>'}
        </button>
      `);
    }
  }

  const boardEl = $('#board');
  boardEl.style.gridTemplateColumns = `repeat(${width}, minmax(40px, 1fr))`;
  boardEl.innerHTML = cells.join('');

  boardEl.querySelectorAll('.cell').forEach((cell) => {
    cell.addEventListener('click', () => {
      onCellClick(Number(cell.dataset.x), Number(cell.dataset.y)).catch((err) => setStatus(err.message, true));
    });
  });

  $('#hand').innerHTML = (me?.hand || []).map((card, index) => `
    <button class="card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}" data-hand-index="${index}">
      <img src="${card.image}" alt="${card.name}" />
      <h4>#${index + 1} · ${card.name}</h4>
    </button>
  `).join('') || '<div class="small">No quedan cartas en mano.</div>';

  document.querySelectorAll('.hand-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!isMyTurn(mySide)) return;
      const index = Number(btn.dataset.handIndex);
      appState.selectedHandIndex = appState.selectedHandIndex === index ? null : index;
      appState.selectedUnitId = null;
      renderBoard();
    });
  });

  $('#match-summary').innerHTML = `
    <div><strong>Turno:</strong> ${appState.match.turn?.number || 1}</div>
    <div><strong>Activo:</strong> ${appState.match.turn?.active_side || '-'}</div>
    <div><strong>Tu vida:</strong> ${me?.life ?? '-'}</div>
    <div><strong>Vida IA:</strong> ${enemy?.life ?? '-'}</div>
    <div><strong>Energía:</strong> ${me?.energy ?? '-'}/${me?.max_energy ?? '-'}</div>
    <div><strong>Ganador:</strong> ${appState.match.winner || 'sin definir'}</div>
  `;

  const ownUnits = me?.units || [];
  const enemyUnits = enemy?.units || [];
  $('#unit-list').innerHTML = `
    <strong>Tus unidades</strong>
    ${ownUnits.map((u) => `<div>${u.card.name} (${u.x},${u.y}) PdV ${u.hp_current}</div>`).join('') || '<div>Sin unidades.</div>'}
    <hr />
    <strong>Unidades IA</strong>
    ${enemyUnits.map((u) => `<div>${u.card.name} (${u.x},${u.y}) PdV ${u.hp_current}</div>`).join('') || '<div>Sin unidades.</div>'}
  `;
}

async function loadCards() {
  let cards = [];
  try {
    const data = await api('/api/cards/');
    cards = data.cards || [];
  } catch {
    cards = localSeedCards();
  }
  if (!cards.length) cards = localSeedCards();
  appState.cards = cards;
  if (familyFilter) {
    const families = [...new Set(cards.map((card) => card.family))];
    familyFilter.innerHTML = '<option value="">Todas las familias</option>' + families.map((f) => `<option value="${f}">${f}</option>`).join('');
  }
  renderCatalog();
}

async function loadActiveMatch() {
  const data = await api('/api/match/active/');
  appState.roomCode = data.room_code;
  appState.match = data.match;
  appState.selectedHandIndex = null;
  appState.selectedUnitId = null;
  renderBoard();
}

async function createAIMatch() {
  const data = await api('/api/match/create-vs-ai/', { method: 'POST', body: '{}' });
  appState.roomCode = data.room_code;
  appState.match = data.match;
  appState.selectedHandIndex = null;
  appState.selectedUnitId = null;
  renderBoard();
  setStatus('Partida nueva creada en esta sesión.');
}

async function refreshMatch() {
  if (!appState.roomCode) {
    await loadActiveMatch();
    if (!appState.roomCode) throw new Error('No hay partida activa en esta sesión.');
    return;
  }
  const data = await api(`/api/match/${appState.roomCode}/`);
  appState.match = data.match;
  renderBoard();
}

async function endTurn() {
  if (!appState.roomCode) throw new Error('No hay partida activa.');
  await sendAction({ action: 'end_turn' });
}

function bindAsyncButton(selector, handler) {
  const button = $(selector);
  if (!button) return;
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await handler();
    } catch (err) {
      setStatus(err.message || 'Error inesperado', true);
    } finally {
      button.disabled = false;
    }
  });
}

function boot() {
  renderStaticBoard();
  bindAsyncButton('#create-ai-match', createAIMatch);
  bindAsyncButton('#refresh-state', refreshMatch);
  bindAsyncButton('#end-turn-btn', endTurn);
  familyFilter?.addEventListener('change', renderCatalog);

  loadCards()
    .then(loadActiveMatch)
    .catch((err) => {
      setStatus(err.message || 'No se pudo iniciar el juego.', true);
      renderBoard();
    })
    .finally(() => {
      if (!appState.match) {
        setStatus('Sin login: hacé clic en "Jugar vs IA" para iniciar.');
      }
    });
}

document.addEventListener('DOMContentLoaded', boot, { once: true });
