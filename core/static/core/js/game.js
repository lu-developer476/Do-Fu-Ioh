const DEFAULT_BOARD_WIDTH = 11;
const DEFAULT_BOARD_HEIGHT = 11;
const CARD_IMAGE_PLACEHOLDER = '/static/core/images/card-placeholder.svg';

const appState = {
  cards: [],
  roomCode: null,
  match: null,
  selectedHandIndex: null,
  selectedUnitId: null,
  actionFeedback: {
    message: 'Seleccioná una carta o unidad para ver el feedback táctico acá.',
    tone: 'normal',
  },
};

const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

function setStatus(message, isError = false) {
  const status = $('#auth-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('status-error', isError);
}

function setActionFeedback(message, tone = 'normal') {
  appState.actionFeedback = { message, tone };
  const feedback = $('#action-feedback');
  if (!feedback) return;
  feedback.textContent = message;
  feedback.classList.remove('feedback-normal', 'feedback-error', 'feedback-success');
  feedback.classList.add(`feedback-${tone}`);
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie
    .split(';')
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function resolveCardImage(image) {
  const raw = String(image ?? '').trim();
  if (!raw) return CARD_IMAGE_PLACEHOLDER;
  if (raw.startsWith('data:') || raw.startsWith('blob:')) return raw;

  if (/^https?:\/\//i.test(raw)) {
    try {
      return new URL(raw).href;
    } catch {
      return CARD_IMAGE_PLACEHOLDER;
    }
  }

  if (/^[a-z]+:/i.test(raw)) return CARD_IMAGE_PLACEHOLDER;

  const normalized = raw
    .replace(/^\.\//, '')
    .replace(/^public\//, '/static/')
    .replace(/^static\//, '/static/');

  if (normalized.startsWith('/')) return normalized;
  return `/static/${normalized}`;
}

function buildCardImageMarkup(image, name, className = '') {
  const safeName = escapeHtml(name || 'Carta sin nombre');
  const resolvedSrc = escapeHtml(resolveCardImage(image));
  const classes = ['card-image'];
  if (className) classes.push(className);

  return `
    <span class="card-image-frame ${escapeHtml(className)}" data-card-image-frame>
      <img
        class="${classes.join(' ')}"
        src="${resolvedSrc}"
        alt="${safeName}"
        loading="lazy"
        decoding="async"
        data-card-image
        data-original-src="${resolvedSrc}"
      />
      <span class="card-image-fallback" aria-hidden="true">Sin imagen</span>
    </span>
  `;
}

function installCardImageFallbacks(scope = document) {
  scope.querySelectorAll('img[data-card-image]').forEach((img) => {
    if (img.dataset.fallbackBound === 'true') return;
    img.dataset.fallbackBound = 'true';

    img.addEventListener('error', () => {
      const frame = img.closest('[data-card-image-frame]');
      frame?.classList.add('is-fallback');
      img.classList.add('is-fallback');

      if (img.dataset.fallbackApplied === 'true') return;

      img.dataset.fallbackApplied = 'true';
      img.src = CARD_IMAGE_PLACEHOLDER;
    });

    img.addEventListener('load', () => {
      if (img.currentSrc && !img.currentSrc.endsWith(CARD_IMAGE_PLACEHOLDER)) {
        const frame = img.closest('[data-card-image-frame]');
        frame?.classList.remove('is-fallback');
        img.classList.remove('is-fallback');
      }
    });
  });
}

async function api(url, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if ((options.method || 'GET').toUpperCase() !== 'GET') {
    const csrfToken = getCookie('csrftoken');
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
  }

  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers,
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
      ${buildCardImageMarkup(card.image, card.name, 'card-image-catalog')}
      <h4>${card.name}</h4>
      <div class="meta">
        <span class="badge">${card.family}</span>
        <span class="badge">${card.stage}</span>
        <span class="badge">Coste ${card.summon_cost}</span>
      </div>
      <p>${card.description || ''}</p>
    </article>
  `).join('') || '<div class="small">No hay cartas disponibles.</div>';
  installCardImageFallbacks(catalogEl);
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

function computeMoveTargets(selectedUnit, meUnits, enemyUnits, boardWidth = DEFAULT_BOARD_WIDTH, boardHeight = DEFAULT_BOARD_HEIGHT) {
  if (!selectedUnit || selectedUnit.pm_current <= 0 || !selectedUnit.can_move) return new Map();

  if (Array.isArray(selectedUnit.reachable_cells)) {
    return new Map(
      selectedUnit.reachable_cells.map((cell) => [`${cell.x},${cell.y}`, cell.distance])
    );
  }

  const occupied = new Set(
    [...meUnits, ...enemyUnits]
      .filter((u) => u.id !== selectedUnit.id)
      .map((u) => `${u.x},${u.y}`)
  );
  const originKey = `${selectedUnit.x},${selectedUnit.y}`;
  const distances = new Map([[originKey, 0]]);
  const queue = [[selectedUnit.x, selectedUnit.y]];

  while (queue.length) {
    const [currentX, currentY] = queue.shift();
    const currentKey = `${currentX},${currentY}`;
    const currentDistance = distances.get(currentKey) || 0;
    if (currentDistance >= selectedUnit.pm_current) continue;

    [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dx, dy]) => {
      const nextX = currentX + dx;
      const nextY = currentY + dy;
      const nextKey = `${nextX},${nextY}`;
      if (!isWithinBoard(nextX, nextY, boardWidth, boardHeight) || occupied.has(nextKey)) return;

      const nextDistance = currentDistance + 1;
      if (nextDistance > selectedUnit.pm_current) return;

      const previousDistance = distances.get(nextKey);
      if (previousDistance !== undefined && previousDistance <= nextDistance) return;

      distances.set(nextKey, nextDistance);
      queue.push([nextX, nextY]);
    });
  }

  distances.delete(originKey);
  return distances;
}

function computeAttackRange(selectedUnit) {
  if (!selectedUnit) return 0;
  const baseRange = selectedUnit.card.stage === 'base' ? 1 : 2;
  return Math.min(5, baseRange + Math.floor(selectedUnit.card.action_points / 2));
}

function computeAttackTargets(selectedUnit, enemyUnits) {
  if (!selectedUnit || selectedUnit.pa_current <= 0 || !selectedUnit.can_act) return new Set();

  if (Array.isArray(selectedUnit.attackable_unit_ids)) {
    return new Set(selectedUnit.attackable_unit_ids);
  }

  const attackRange = computeAttackRange(selectedUnit);
  return new Set(enemyUnits
    .filter((enemy) => Math.abs(enemy.x - selectedUnit.x) + Math.abs(enemy.y - selectedUnit.y) <= attackRange)
    .map((enemy) => enemy.id));
}

function buildCoordinateLabel(x, y) {
  return `${x}:${y}`;
}

function isWithinBoard(x, y, boardWidth = DEFAULT_BOARD_WIDTH, boardHeight = DEFAULT_BOARD_HEIGHT) {
  return x >= 0 && y >= 0 && x < boardWidth && y < boardHeight;
}

function describeBoardPosition(x, y, boardWidth = DEFAULT_BOARD_WIDTH, boardHeight = DEFAULT_BOARD_HEIGHT) {
  if (isWithinBoard(x, y, boardWidth, boardHeight)) return `la casilla ${buildCoordinateLabel(x, y)}`;
  return `la posición ${buildCoordinateLabel(x, y)} (fuera del tablero ${boardWidth}×${boardHeight})`;
}

function syncSelectedUnit(me) {
  const selectedUnitExists = Boolean(me?.units?.some((u) => u.id === appState.selectedUnitId));
  if (!selectedUnitExists) appState.selectedUnitId = null;
  return me?.units?.find((u) => u.id === appState.selectedUnitId) || null;
}

function getSelectionSummary({ selectedHandCard, selectedUnit, canPlay }) {
  if (selectedHandCard) {
    return canPlay
      ? `Carta seleccionada: ${selectedHandCard.name}. Elegí una casilla verde para invocar.`
      : `Carta seleccionada: ${selectedHandCard.name}. Esperá tu turno para invocar.`;
  }

  if (selectedUnit) {
    return canPlay
      ? `Unidad seleccionada: ${selectedUnit.card.name}. Azul = movimiento, rojo = ataque.`
      : `Unidad seleccionada: ${selectedUnit.card.name}. Esperá tu turno para actuar.`;
  }

  return canPlay
    ? 'Seleccioná una carta de tu mano o una de tus unidades para ver opciones tácticas.'
    : 'Esperá la respuesta de la IA. Podés inspeccionar el tablero y tu mano.';
}

function renderMatchLog(logEntries = []) {
  const logEl = $('#match-log');
  if (!logEl) return;

  if (!Array.isArray(logEntries) || !logEntries.length) {
    logEl.innerHTML = '<div class="small">Todavía no hay eventos registrados.</div>';
    return;
  }

  logEl.innerHTML = `
    <ol class="match-log-list">
      ${logEntries.map((entry, index) => `
        <li class="match-log-item">
          <span class="match-log-order">${String(index + 1).padStart(2, '0')}</span>
          <p>${entry}</p>
        </li>
      `).join('')}
    </ol>
  `;
  logEl.scrollTop = logEl.scrollHeight;
}

function renderStaticBoard() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone);
  const boardEl = $('#board');
  if (!boardEl) return;
  const cells = [];
  for (let y = 0; y < DEFAULT_BOARD_HEIGHT; y += 1) {
    for (let x = 0; x < DEFAULT_BOARD_WIDTH; x += 1) {
      const squareClass = (x + y) % 2 === 0 ? 'square-light' : 'square-dark';
      cells.push(`
        <div class="cell ${squareClass} empty preview-cell">
          <span class="cell-coord">${buildCoordinateLabel(x, y)}</span>
          <div class="cell-layer"></div>
        </div>
      `);
    }
  }
  boardEl.style.gridTemplateColumns = `repeat(${DEFAULT_BOARD_WIDTH}, minmax(40px, 1fr))`;
  boardEl.innerHTML = cells.join('');
}

async function sendAction(actionPayload, failureMessage = 'La acción no pudo resolverse.') {
  try {
    const data = await api(`/api/match/${appState.roomCode}/action/`, {
      method: 'POST',
      body: JSON.stringify(actionPayload),
    });
    appState.match = data.match;
    renderBoard();
  } catch (err) {
    const message = err.message || failureMessage;
    setActionFeedback(`${failureMessage} ${message}`.trim(), 'error');
    throw err;
  }
}

async function onCellClick(x, y) {
  if (!appState.match || !appState.roomCode) return;
  const boardWidth = appState.match.board?.width || DEFAULT_BOARD_WIDTH;
  const boardHeight = appState.match.board?.height || DEFAULT_BOARD_HEIGHT;
  if (!isWithinBoard(x, y, boardWidth, boardHeight)) {
    setActionFeedback(`Movimiento inválido: ${describeBoardPosition(x, y, boardWidth, boardHeight)} no existe. Elegí una casilla dentro del tablero.`, 'error');
    return;
  }

  const { me, enemy, mySide } = resolveSides();
  if (!me || !enemy) return;
  if (!isMyTurn(mySide)) {
    setActionFeedback('Todavía no es tu turno. Esperá a que la IA termine de jugar.', 'error');
    return;
  }

  const myUnit = findUnitAt(me.units || [], x, y);
  const enemyUnit = findUnitAt(enemy.units || [], x, y);
  const selectedHandCard = me.hand?.[appState.selectedHandIndex] || null;
  const selectedUnit = (me.units || []).find((u) => u.id === appState.selectedUnitId) || null;

  if (myUnit) {
    appState.selectedUnitId = myUnit.id;
    appState.selectedHandIndex = null;
    setActionFeedback(`Unidad seleccionada: ${myUnit.card.name}. Azul = movimiento, rojo = ataque.`, 'normal');
    renderBoard();
    return;
  }
  if (selectedHandCard) {
    const deploymentCells = deploymentCellsForSide(mySide, boardWidth, boardHeight);
    const summonKey = `${x},${y}`;
    if (!deploymentCells.has(summonKey) || myUnit || enemyUnit) {
      setActionFeedback(`Invocación inválida en ${describeBoardPosition(x, y, boardWidth, boardHeight)} para ${selectedHandCard.name}. Elegí una casilla verde libre de tu zona.`, 'error');
      return;
    }
    await sendAction(
      { action: 'summon', hand_index: appState.selectedHandIndex, x, y },
      `No se pudo invocar ${selectedHandCard.name} en ${describeBoardPosition(x, y, boardWidth, boardHeight)}.`
    );
    appState.selectedHandIndex = null;
    setActionFeedback(`${selectedHandCard.name} fue invocada correctamente.`, 'success');
    return;
  }
  if (!selectedUnit) {
    setActionFeedback('Casilla inválida: primero seleccioná una carta o una unidad propia.', 'error');
    return;
  }

  if (enemyUnit) {
    const attackTargets = computeAttackTargets(selectedUnit, enemy.units || []);
    if (!attackTargets.has(enemyUnit.id)) {
      setActionFeedback(`Objetivo inválido: ${enemyUnit.card.name} en ${describeBoardPosition(x, y, boardWidth, boardHeight)} está fuera del alcance de ${selectedUnit.card.name}. Elegí un objetivo resaltado en rojo.`, 'error');
      return;
    }
    await sendAction(
      { action: 'attack', attacker_id: selectedUnit.id, target_id: enemyUnit.id },
      `No se pudo concretar el ataque de ${selectedUnit.card.name} sobre ${enemyUnit.card.name}.`
    );
    setActionFeedback(`${selectedUnit.card.name} atacó a ${enemyUnit.card.name}.`, 'success');
    return;
  }

  const moveTargets = computeMoveTargets(selectedUnit, me.units || [], enemy.units || [], boardWidth, boardHeight);
  if (!moveTargets.has(`${x},${y}`)) {
    setActionFeedback(`Movimiento inválido: ${describeBoardPosition(x, y, boardWidth, boardHeight)} no está disponible para ${selectedUnit.card.name}. Elegí una casilla azul permitida.`, 'error');
    return;
  }
  await sendAction(
    { action: 'move', unit_id: selectedUnit.id, to_x: x, to_y: y },
    `No se pudo mover ${selectedUnit.card.name} hacia ${describeBoardPosition(x, y, boardWidth, boardHeight)}.`
  );
  setActionFeedback(`${selectedUnit.card.name} se movió a ${buildCoordinateLabel(x, y)}.`, 'success');
}

function renderBoard() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone);
  if (!appState.match) {
    renderStaticBoard();
    $('#hand').innerHTML = '<div class="small">Tu mano aparecerá acá.</div>';
    $('#match-summary').innerHTML = '<div class="small">Iniciá una partida contra la IA para comenzar.</div>';
    $('#unit-list').innerHTML = '<div class="small">Sin unidades.</div>';
    renderMatchLog();
    return;
  }

  const { me, enemy, mySide } = resolveSides();
  const width = appState.match.board?.width || DEFAULT_BOARD_WIDTH;
  const height = appState.match.board?.height || DEFAULT_BOARD_HEIGHT;
  const canPlay = isMyTurn(mySide);
  const selectedUnit = syncSelectedUnit(me);
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  const moveTargets = computeMoveTargets(selectedUnit, me?.units || [], enemy?.units || [], width, height);
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
      const canSummon = Boolean(selectedHandCard) && myDeployment.has(key) && !unit && canPlay;
      const canMove = moveTargets.has(key) && canPlay;
      const canAttack = enemyUnit && attackTargets.has(enemyUnit.id) && canPlay;
      const deployClass = myDeployment.has(key) ? 'deploy-ally' : (enemyDeployment.has(key) ? 'deploy-enemy' : '');
      const hintClass = canSummon ? 'hint-summon' : (canMove ? 'hint-move' : (canAttack ? 'hint-attack' : ''));
      const selectedClass = ownUnit && selectedUnit?.id === ownUnit.id ? 'selected' : '';
      const interactiveClass = canSummon || canMove || canAttack || ownUnit ? 'is-actionable' : '';
      const coordinate = buildCoordinateLabel(x, y);

      cells.push(`
        <button class="cell ${squareClass} ${ownUnit ? 'ally has-unit' : enemyUnit ? 'enemy has-unit' : 'empty'} ${deployClass} ${hintClass} ${selectedClass} ${interactiveClass}" data-x="${x}" data-y="${y}" aria-label="Casilla ${coordinate}">
          <span class="cell-coord">${coordinate}</span>
          <div class="cell-layer">
            ${unit
              ? `
                <div class="token ${ownUnit ? 'token-ally' : 'token-enemy'} ${selectedClass ? 'token-selected' : ''}">
                  <div class="token-portrait-wrap">
                    ${buildCardImageMarkup(unit.card.image, unit.card.name, 'card-image-token')}
                  </div>
                  <strong class="token-name">${unit.card.name}</strong>
                  <div class="token-stats">
                    <span>PdV ${unit.hp_current}</span>
                    <span>Esc ${unit.shell_current}</span>
                    <span>PA ${unit.pa_current}</span>
                    <span>PM ${unit.pm_current}</span>
                  </div>
                </div>
              `
              : '<div class="cell-empty-state"></div>'}
          </div>
        </button>
      `);
    }
  }

  const boardEl = $('#board');
  boardEl.style.gridTemplateColumns = `repeat(${width}, minmax(40px, 1fr))`;
  boardEl.innerHTML = cells.join('');
  installCardImageFallbacks(boardEl);

  boardEl.querySelectorAll('.cell').forEach((cell) => {
    cell.addEventListener('click', () => {
      onCellClick(Number(cell.dataset.x), Number(cell.dataset.y)).catch((err) => setStatus(err.message, true));
    });
  });

  const handEl = $('#hand');
  handEl.innerHTML = (me?.hand || []).map((card, index) => `
    <button class="card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}" data-hand-index="${index}">
      ${buildCardImageMarkup(card.image, card.name, 'card-image-hand')}
      <h4>#${index + 1} · ${card.name}</h4>
      <div class="meta"><span class="badge">Coste ${card.summon_cost}</span><span class="badge">${card.stage}</span></div>
    </button>
  `).join('') || '<div class="small">No quedan cartas en mano.</div>';
  installCardImageFallbacks(handEl);

  document.querySelectorAll('.hand-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!canPlay) {
        setActionFeedback('Todavía no es tu turno. Esperá a que la IA termine de jugar.', 'error');
        return;
      }
      const index = Number(btn.dataset.handIndex);
      const isSameCard = appState.selectedHandIndex === index;
      appState.selectedHandIndex = isSameCard ? null : index;
      appState.selectedUnitId = null;
      if (isSameCard) {
        setActionFeedback('Carta deseleccionada. Elegí otra carta o una unidad propia.', 'normal');
      } else {
        setActionFeedback(`Carta seleccionada: ${me.hand[index].name}. Elegí una casilla verde para invocar.`, 'normal');
      }
      renderBoard();
    });
  });

  $('#match-summary').innerHTML = `
    <div><strong>Turno:</strong> ${appState.match.turn?.number || 1}</div>
    <div><strong>Activo:</strong> ${appState.match.turn?.active_side || '-'}</div>
    <div><strong>Energía:</strong> ${me?.energy ?? '-'}/${me?.max_energy ?? '-'}</div>
    <div><strong>IA:</strong> ${enemy?.energy ?? '-'}/${enemy?.max_energy ?? '-'}</div>
    <div><strong>Mano / mazo:</strong> ${me?.hand_count ?? '-'} / ${me?.library_count ?? '-'}</div>
    <div><strong>Ganador:</strong> ${appState.match.winner || 'sin definir'}</div>
    <div class="selection-summary"><strong>Selección:</strong> ${getSelectionSummary({ selectedHandCard, selectedUnit, canPlay })}</div>
  `;

  const ownUnits = me?.units || [];
  const enemyUnits = enemy?.units || [];
  renderMatchLog(appState.match.log || []);
  $('#unit-list').innerHTML = `
    <strong>Tus unidades</strong>
    ${ownUnits.map((u) => `<div>${u.card.name} (${buildCoordinateLabel(u.x, u.y)}) · PdV ${u.hp_current} · Esc ${u.shell_current}</div>`).join('') || '<div>Sin unidades.</div>'}
    <hr />
    <strong>Unidades IA</strong>
    ${enemyUnits.map((u) => `<div>${u.card.name} (${buildCoordinateLabel(u.x, u.y)}) · PdV ${u.hp_current} · Esc ${u.shell_current}</div>`).join('') || '<div>Sin unidades.</div>'}
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
  setActionFeedback('Partida lista. Seleccioná una carta o unidad para empezar tu turno.', 'normal');
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
  appState.selectedHandIndex = null;
  appState.selectedUnitId = null;
  setActionFeedback('Turno terminado. La IA está pensando su respuesta.', 'success');
  renderBoard();
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
      setActionFeedback('No se pudo cargar la partida. Probá reiniciar con "Jugar vs IA".', 'error');
      renderBoard();
    })
    .finally(() => {
      if (!appState.match) {
        setStatus('Sin login: hacé clic en "Jugar vs IA" para iniciar.');
      }
    });
}

document.addEventListener('DOMContentLoaded', boot, { once: true });
