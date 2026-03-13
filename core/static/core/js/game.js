const DEFAULT_BOARD_WIDTH = 11;
const DEFAULT_BOARD_HEIGHT = 11;

let appState = {
  cards: [],
  roomCode: null,
  match: null,
  selectedHandIndex: null,
  selectedUnitId: null,
};

const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

function setAuthStatus(message, isError = false) {
  const status = $('#auth-status');
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
  const filter = familyFilter.value;
  const cards = appState.cards.filter((card) => !filter || card.family === filter);
  $('#catalog').innerHTML = cards.map((card) => `
    <article class="card">
      <img src="${card.image}" alt="${card.name}" />
      <h4>${card.name}</h4>
      <div class="meta">
        <span class="badge">${card.family}</span>
        <span class="badge">${card.stage}</span>
        <span class="badge">Niv ${card.level_min}-${card.level_max}</span>
        <span class="badge">PdV ${card.hp}</span>
        <span class="badge">PdC ${card.shell}</span>
        <span class="badge">PA ${card.action_points}</span>
        <span class="badge">PM ${card.movement_points}</span>
      </div>
      <p>${card.description}</p>
    </article>
  `).join('');
}

function resolveSides() {
  const match = appState.match;
  if (!match) return { me: null, enemy: null, mySide: null };
  const mySide = 'host';
  return {
    me: match.host,
    enemy: match.guest,
    mySide,
  };
}

function findUnitAt(units = [], x, y) {
  return units.find((u) => u.x === x && u.y === y);
}

function shortId(unitId) {
  return unitId?.slice(-4) || '----';
}

function isMyTurn(mySide) {
  return Boolean(appState.match && mySide && appState.match.turn.active_side === mySide);
}


function deploymentCellsForSide(side, boardWidth, boardHeight) {
  if (!side) return new Set();
  const middleX = Math.floor(boardWidth / 2);
  if (side === 'host') {
    return new Set([
      `${middleX},0`,
      `${middleX - 1},1`,
      `${middleX},1`,
      `${middleX + 1},1`,
      `${middleX},2`,
    ]);
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

function isUnitSummonedThisTurn(unit) {
  return appState.match && unit.summoned_turn === appState.match.turn.number;
}

function renderStaticBoard() {
  const cells = [];
  for (let y = 0; y < DEFAULT_BOARD_HEIGHT; y += 1) {
    for (let x = 0; x < DEFAULT_BOARD_WIDTH; x += 1) {
      const squareClass = (x + y) % 2 === 0 ? 'square-light' : 'square-dark';
      cells.push(`
        <div class="cell ${squareClass} empty preview-cell">
          <div class="small"></div>
        </div>
      `);
    }
  }

  const boardEl = $('#board');
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

  const myUnit = findUnitAt(me.units, x, y);
  const enemyUnit = findUnitAt(enemy.units, x, y);
  const selectedHandCard = me.hand[appState.selectedHandIndex];
  const selectedUnit = me.units.find((u) => u.id === appState.selectedUnitId);

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

  if (!selectedUnit || isUnitSummonedThisTurn(selectedUnit)) return;

  if (enemyUnit) {
    const validAttackTargets = computeAttackTargets(selectedUnit, enemy.units);
    if (!validAttackTargets.has(enemyUnit.id)) return;
    await sendAction({ action: 'attack', attacker_id: selectedUnit.id, target_id: enemyUnit.id });
    return;
  }

  const validMoveTargets = computeMoveTargets(selectedUnit, me.units, enemy.units);
  if (!validMoveTargets.has(`${x},${y}`)) return;
  await sendAction({ action: 'move', unit_id: selectedUnit.id, to_x: x, to_y: y });
}

function renderBoard() {
  const match = appState.match;
  if (!match) {
    renderStaticBoard();
    $('#hand').innerHTML = '<div class="small">Tu mano aparecerá acá.</div>';
    $('#match-summary').innerHTML = '<div class="small">Iniciá una partida contra la IA para comenzar.</div>';
    $('#unit-list').innerHTML = '<div class="small">Sin unidades.</div>';
    return;
  }

  const { me, enemy, mySide } = resolveSides();
  const width = match.board.width;
  const height = match.board.height;
  const selectedUnit = me?.units?.find((u) => u.id === appState.selectedUnitId) || null;
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  const moveTargets = computeMoveTargets(selectedUnit, me?.units || [], enemy?.units || []);
  const attackTargets = computeAttackTargets(selectedUnit, enemy?.units || []);
  const myDeploymentCells = deploymentCellsForSide(mySide, width, height);
  const enemyDeploymentCells = deploymentCellsForSide(mySide === 'host' ? 'guest' : 'host', width, height);

  const cells = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const ownUnit = findUnitAt(me?.units, x, y);
      const enemyUnit = findUnitAt(enemy?.units, x, y);
      const unit = ownUnit || enemyUnit;
      const ownerClass = ownUnit ? 'ally' : (enemyUnit ? 'enemy' : 'empty');
      const squareClass = (x + y) % 2 === 0 ? 'square-light' : 'square-dark';
      const key = `${x},${y}`;
      const isMyDeployCell = myDeploymentCells.has(key);
      const isEnemyDeployCell = enemyDeploymentCells.has(key);
      const canSummon = Boolean(selectedHandCard) && isMyDeployCell && !unit && isMyTurn(mySide);
      const canMoveHere = moveTargets.has(key) && isMyTurn(mySide);
      const isSelected = ownUnit && selectedUnit && ownUnit.id === selectedUnit.id;
      const canAttackThis = enemyUnit && attackTargets.has(enemyUnit.id) && isMyTurn(mySide);
      const hintClass = canSummon ? 'hint-summon' : canMoveHere ? 'hint-move' : canAttackThis ? 'hint-attack' : '';
      const deployClass = isMyDeployCell ? 'deploy-ally' : isEnemyDeployCell ? 'deploy-enemy' : '';

      cells.push(`
        <button class="cell ${squareClass} ${ownerClass} ${deployClass} ${hintClass} ${isSelected ? 'selected' : ''}" data-x="${x}" data-y="${y}">
          ${unit
            ? `<div class="token"><strong>${unit.card.name}</strong><span>#${shortId(unit.id)}</span><span>PdV ${unit.hp_current} · PdC ${unit.shell_current}</span><span>PA ${unit.pa_current} · PM ${unit.pm_current}</span></div>`
            : '<div class="small"></div>'}
        </button>
      `);
    }
  }
  const boardEl = $('#board');
  boardEl.style.gridTemplateColumns = `repeat(${width}, minmax(40px, 1fr))`;
  boardEl.innerHTML = cells.join('');

  document.querySelectorAll('.cell').forEach((cell) => {
    cell.addEventListener('click', () => {
      const x = Number(cell.dataset.x);
      const y = Number(cell.dataset.y);
      onCellClick(x, y).catch((err) => setAuthStatus(err.message, true));
    });
  });

  $('#hand').innerHTML = (me?.hand || []).map((card, index) => {
    const selectedClass = appState.selectedHandIndex === index ? 'selected' : '';
    return `
      <button class="card hand-card ${selectedClass}" data-hand-index="${index}">
        <img src="${card.image}" alt="${card.name}" />
        <h4>#${index + 1} · ${card.name}</h4>
        <div class="meta">
          <span class="badge">Coste ${Math.max(1, card.level_min)}</span>
          <span class="badge">PA ${card.action_points}</span>
          <span class="badge">PM ${card.movement_points}</span>
        </div>
      </button>
    `;
  }).join('') || '<div class="small">No quedan cartas en mano.</div>';

  document.querySelectorAll('.hand-card').forEach((cardBtn) => {
    cardBtn.addEventListener('click', () => {
      if (!isMyTurn(mySide)) return;
      const index = Number(cardBtn.dataset.handIndex);
      appState.selectedHandIndex = appState.selectedHandIndex === index ? null : index;
      appState.selectedUnitId = null;
      renderBoard();
    });
  });

  const selectedText = selectedHandCard
    ? `Carta seleccionada: #${appState.selectedHandIndex + 1} ${selectedHandCard.name} (clic en casilla azul)`
    : selectedUnit
      ? `Unidad seleccionada: ${selectedUnit.card.name} (#${shortId(selectedUnit.id)})`
      : 'Sin selección activa';

  $('#match-summary').innerHTML = `
    <div><strong>Modo:</strong> Contra IA</div>
    <div><strong>Tu lado:</strong> ${mySide || '-'}</div>
    <div><strong>Turno activo:</strong> ${match.turn.active_side}</div>
    <div><strong>Número de turno:</strong> ${match.turn.number}</div>
    <div><strong>Tu vida:</strong> ${me?.life ?? '-'} · <strong>Energía:</strong> ${me?.energy ?? '-'}/${me?.max_energy ?? '-'}</div>
    <div><strong>Rival vida:</strong> ${enemy?.life ?? '-'}</div>
    <div><strong>Tu mazo:</strong> ${me?.library_count ?? 0} · <strong>Tu mano:</strong> ${me?.hand?.length ?? 0}/5</div>
    <div><strong>Mazo rival:</strong> ${enemy?.library_count ?? 0} · <strong>Mano rival:</strong> ${enemy?.hand_count ?? 0}</div>
    <div><strong>Ganador:</strong> ${match.winner || 'sin definir'}</div>
    <div><strong>Selección:</strong> ${selectedText}</div>
    <div><strong>Zona de invocación:</strong> 5 casillas azules.</div>
  `;

  const ownUnits = me?.units || [];
  const enemyUnits = enemy?.units || [];
  $('#unit-list').innerHTML = `
    <strong>Tus unidades</strong>
    ${ownUnits.map((u) => `<div>#${shortId(u.id)} · ${u.card.name} (${u.x},${u.y}) · PdV ${u.hp_current} · PA ${u.pa_current} · PM ${u.pm_current}</div>`).join('') || '<div>Sin unidades propias.</div>'}
    <hr />
    <strong>Unidades enemigas</strong>
    ${enemyUnits.map((u) => `<div>#${shortId(u.id)} · ${u.card.name} (${u.x},${u.y}) · PdV ${u.hp_current}</div>`).join('') || '<div>Sin unidades enemigas.</div>'}
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
  const families = [...new Set(cards.map((card) => card.family))];
  familyFilter.innerHTML = '<option value="">Todas las familias</option>' + families.map((f) => `<option value="${f}">${f}</option>`).join('');
  renderCatalog();
}

async function createAIMatch() {
  const data = await api('/api/match/create-vs-ai/', { method: 'POST', body: '{}' });
  appState.roomCode = data.room_code;
  appState.match = data.match;
  appState.selectedHandIndex = null;
  appState.selectedUnitId = null;
  renderBoard();
}

async function refreshMatch() {
  if (!appState.roomCode) throw new Error('Primero iniciá una partida vs IA.');
  const data = await api(`/api/match/${appState.roomCode}/`);
  appState.match = data.match;
  renderBoard();
}

async function endTurn() {
  if (!appState.roomCode) throw new Error('No hay partida activa.');
  await sendAction({ action: 'end_turn' });
  appState.selectedHandIndex = null;
  appState.selectedUnitId = null;
}

function bindAsyncButton(selector, handler) {
  const button = $(selector);
  if (!button) return;
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    const originalText = button.textContent;
    button.disabled = true;
    try {
      await handler();
    } catch (err) {
      setAuthStatus(err.message || 'Error inesperado', true);
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });
}

bindAsyncButton('#create-ai-match', createAIMatch);
bindAsyncButton('#refresh-state', refreshMatch);
bindAsyncButton('#end-turn-btn', endTurn);
if (familyFilter) {
  familyFilter.addEventListener('change', renderCatalog);
}

renderStaticBoard();

loadCards()
  .catch(() => setAuthStatus('No se pudo cargar el catálogo completo.', true))
  .finally(() => {
    setAuthStatus('Este modo no usa autenticación. Hacé clic en "Jugar vs IA" para iniciar una partida nueva.');
    renderBoard();
  });
