const DEFAULT_BOARD_WIDTH = 11;
const DEFAULT_BOARD_HEIGHT = 11;
const CARD_IMAGE_PLACEHOLDER = '/static/core/img/placeholders/card-placeholder.svg';
const EMPTY_MESSAGES = {
  catalog: 'No hay cartas disponibles.',
  matchLog: 'Todavía no hay eventos registrados.',
  hand: 'No quedan cartas en mano.',
  handPreview: 'Tu mano aparecerá acá.',
  summary: 'Iniciá una partida contra la IA para comenzar.',
  units: 'Sin unidades.',
};

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

function getCsrfToken() {
  const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')?.trim();
  if (metaToken && metaToken !== 'NOTPROVIDED') return metaToken;
  return getCookie('csrftoken');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function clearElement(element) {
  if (element) element.replaceChildren();
}

function renderEmptyState(element, message, className = 'small') {
  if (!element) return;
  const empty = document.createElement('div');
  empty.className = className;
  empty.textContent = message;
  element.replaceChildren(empty);
}

function appendTextElement(parent, tagName, text, className = '') {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

function appendBadgeRow(parent, values = []) {
  const row = document.createElement('div');
  row.className = 'meta';
  values.forEach((value) => {
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = value;
    row.appendChild(badge);
  });
  parent.appendChild(row);
  return row;
}

function createCardImageElement(image, name, className = '') {
  const frame = document.createElement('span');
  frame.className = `card-image-frame${className ? ` ${className}` : ''}`;
  frame.dataset.cardImageFrame = '';

  const img = document.createElement('img');
  img.className = ['card-image', className].filter(Boolean).join(' ');
  img.src = resolveCardImage(image);
  img.alt = name || 'Carta sin nombre';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.dataset.cardImage = '';
  img.dataset.originalSrc = img.src;

  const fallback = document.createElement('span');
  fallback.className = 'card-image-fallback';
  fallback.setAttribute('aria-hidden', 'true');
  fallback.textContent = 'Sin imagen';

  frame.append(img, fallback);
  return frame;
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
    const csrfToken = getCsrfToken();
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

  clearElement(catalogEl);
  const filter = familyFilter?.value || '';
  const filteredCards = appState.cards.filter((card) => !filter || card.family === filter);

  if (!filteredCards.length) {
    renderEmptyState(catalogEl, EMPTY_MESSAGES.catalog);
    return;
  }

  filteredCards.forEach((card) => {
    const article = document.createElement('article');
    article.className = 'card';
    article.appendChild(createCardImageElement(card.image, card.name, 'card-image-catalog'));
    appendTextElement(article, 'h4', card.name);
    appendBadgeRow(article, [card.family, card.stage, `Coste ${card.summon_cost}`]);
    appendTextElement(article, 'p', card.description || '');
    catalogEl.appendChild(article);
  });

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
    return new Map(selectedUnit.reachable_cells.map((cell) => [`${cell.x},${cell.y}`, cell.distance]));
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

function summarizeCardStats(card = {}) {
  const hp = card.hp ?? card.health ?? '-';
  const actionPoints = card.action_points ?? card.pa ?? '-';
  const movePoints = card.move_points ?? card.pm ?? '-';
  return `PdV ${hp} · PA ${actionPoints} · PM ${movePoints}`;
}

function estimateSummonCost(card = {}) {
  return card.summon_cost ?? card.cost ?? card.energy_cost ?? '?';
}

function shortenUnitName(name = '') {
  const trimmed = String(name).trim();
  if (!trimmed) return 'Sin nombre';
  if (trimmed.length <= 16) return trimmed;
  const compact = trimmed.split(/\s+/).slice(0, 2).join(' ');
  return compact.length <= 16 ? compact : `${compact.slice(0, 13).trimEnd()}…`;
}

function createSummaryField(label, value, className = '') {
  const item = document.createElement('div');
  item.className = ['summary-field', className].filter(Boolean).join(' ');
  const strong = document.createElement('strong');
  strong.textContent = `${label}:`;
  item.appendChild(strong);
  item.append(` ${value}`);
  return item;
}

function createUnitListEntry(unit) {
  const item = document.createElement('div');
  item.className = 'unit-entry';
  item.textContent = `${unit.card.name} (${buildCoordinateLabel(unit.x, unit.y)}) · PdV ${unit.hp_current} · Esc ${unit.shell_current}`;
  return item;
}

function renderMatchLog(logEntries = []) {
  const logEl = $('#match-log');
  if (!logEl) return;

  clearElement(logEl);
  if (!Array.isArray(logEntries) || !logEntries.length) {
    renderEmptyState(logEl, EMPTY_MESSAGES.matchLog);
    return;
  }

  const list = document.createElement('ol');
  list.className = 'match-log-list';

  logEntries.forEach((entry, index) => {
    const item = document.createElement('li');
    item.className = 'match-log-item';
    appendTextElement(item, 'span', String(index + 1).padStart(2, '0'), 'match-log-order');
    appendTextElement(item, 'p', entry);
    list.appendChild(item);
  });

  logEl.appendChild(list);
  logEl.scrollTop = logEl.scrollHeight;
}

function createCellCoordinate(x, y) {
  const coord = document.createElement('span');
  coord.className = 'cell-coord';
  coord.textContent = buildCoordinateLabel(x, y);
  return coord;
}

function createPreviewCell(x, y) {
  const cell = document.createElement('div');
  cell.className = `cell ${(x + y) % 2 === 0 ? 'square-light' : 'square-dark'} empty preview-cell`;
  cell.appendChild(createCellCoordinate(x, y));
  const layer = document.createElement('div');
  layer.className = 'cell-layer';
  cell.appendChild(layer);
  return cell;
}

function createTokenStat(label, value, modifierClass = '') {
  const stat = document.createElement('span');
  stat.className = ['token-stat', modifierClass].filter(Boolean).join(' ');
  appendTextElement(stat, 'strong', label);
  appendTextElement(stat, 'span', value);
  return stat;
}

function createUnitToken(unit, isOwnUnit, isSelected) {
  const token = document.createElement('div');
  token.className = ['token', isOwnUnit ? 'token-ally' : 'token-enemy', isSelected ? 'token-selected' : ''].filter(Boolean).join(' ');

  const top = document.createElement('div');
  top.className = 'token-topline';
  appendTextElement(top, 'span', isOwnUnit ? 'Tuya' : 'IA', `token-owner ${isOwnUnit ? 'token-owner-ally' : 'token-owner-enemy'}`);
  appendTextElement(top, 'span', shortenUnitName(unit.card.name), 'token-name');

  const body = document.createElement('div');
  body.className = 'token-body';
  const portraitWrap = document.createElement('div');
  portraitWrap.className = 'token-portrait-wrap';
  portraitWrap.appendChild(createCardImageElement(unit.card.image, unit.card.name, 'card-image-token'));

  const metrics = document.createElement('div');
  metrics.className = 'token-metrics';
  metrics.append(
    createTokenStat('PdV', unit.hp_current, 'token-stat-hp'),
    createTokenStat('PA', unit.pa_current, 'token-stat-pa'),
    createTokenStat('PM', unit.pm_current, 'token-stat-pm')
  );

  body.append(portraitWrap, metrics);
  token.append(top, body);
  return token;
}

function createBoardCell({ x, y, ownUnit, enemyUnit, selectedUnit, selectedHandCard, canPlay, myDeployment, enemyDeployment, moveTargets, attackTargets }) {
  const unit = ownUnit || enemyUnit;
  const key = `${x},${y}`;
  const canSummon = Boolean(selectedHandCard) && myDeployment.has(key) && !unit && canPlay;
  const canMove = moveTargets.has(key) && canPlay;
  const canAttack = enemyUnit && attackTargets.has(enemyUnit.id) && canPlay;
  const deployClass = myDeployment.has(key) ? 'deploy-ally' : (enemyDeployment.has(key) ? 'deploy-enemy' : '');
  const hintClass = canSummon ? 'hint-summon' : (canMove ? 'hint-move' : (canAttack ? 'hint-attack' : ''));
  const isSelected = Boolean(ownUnit && selectedUnit?.id === ownUnit.id);
  const interactiveClass = canSummon || canMove || canAttack || ownUnit ? 'is-actionable' : '';
  const stateClass = ownUnit ? 'ally has-unit' : enemyUnit ? 'enemy has-unit' : 'empty';

  const cell = document.createElement('button');
  cell.type = 'button';
  cell.className = ['cell', (x + y) % 2 === 0 ? 'square-light' : 'square-dark', stateClass, deployClass, hintClass, isSelected ? 'selected' : '', interactiveClass].filter(Boolean).join(' ');
  cell.dataset.x = x;
  cell.dataset.y = y;
  cell.setAttribute('aria-label', `Casilla ${buildCoordinateLabel(x, y)}`);
  cell.appendChild(createCellCoordinate(x, y));

  const layer = document.createElement('div');
  layer.className = 'cell-layer';
  layer.appendChild(unit ? createUnitToken(unit, Boolean(ownUnit), isSelected) : (() => {
    const empty = document.createElement('div');
    empty.className = 'cell-empty-state';
    return empty;
  })());

  cell.appendChild(layer);
  return cell;
}

function renderStaticBoard() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone);
  const boardEl = $('#board');
  if (!boardEl) return;

  clearElement(boardEl);
  for (let y = 0; y < DEFAULT_BOARD_HEIGHT; y += 1) {
    for (let x = 0; x < DEFAULT_BOARD_WIDTH; x += 1) {
      boardEl.appendChild(createPreviewCell(x, y));
    }
  }
  boardEl.style.gridTemplateColumns = `repeat(${DEFAULT_BOARD_WIDTH}, minmax(40px, 1fr))`;
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

function renderHand(hand = [], canPlay = false) {
  const handEl = $('#hand');
  if (!handEl) return;
  clearElement(handEl);

  if (!hand.length) {
    renderEmptyState(handEl, EMPTY_MESSAGES.hand);
    return;
  }

  hand.forEach((card, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}`.trim();
    button.dataset.handIndex = index;
    button.appendChild(createCardImageElement(card.image, card.name, 'card-image-hand'));

    const header = document.createElement('div');
    header.className = 'hand-card-header';
    appendTextElement(header, 'span', `#${index + 1}`, 'hand-card-index');
    appendTextElement(header, 'h4', card.name, 'hand-card-title');

    const details = document.createElement('div');
    details.className = 'hand-card-details';
    details.append(
      createSummaryField('Familia', card.family || '-'),
      createSummaryField('Stage', card.stage || '-'),
      createSummaryField('Invocación', estimateSummonCost(card)),
      createSummaryField('Stats', summarizeCardStats(card))
    );

    button.append(header, details);
    button.addEventListener('click', () => {
      if (!canPlay) {
        setActionFeedback('Todavía no es tu turno. Esperá a que la IA termine de jugar.', 'error');
        return;
      }
      const isSameCard = appState.selectedHandIndex === index;
      appState.selectedHandIndex = isSameCard ? null : index;
      appState.selectedUnitId = null;
      if (isSameCard) {
        setActionFeedback('Carta deseleccionada. Elegí otra carta o una unidad propia.', 'normal');
      } else {
        setActionFeedback(`Carta seleccionada: ${hand[index].name}. Elegí una casilla verde para invocar.`, 'normal');
      }
      renderBoard();
    });

    handEl.appendChild(button);
  });

  installCardImageFallbacks(handEl);
}

function renderMatchSummary({ me, enemy, selectedHandCard, selectedUnit, canPlay }) {
  const summaryEl = $('#match-summary');
  if (!summaryEl) return;
  clearElement(summaryEl);

  if (!appState.match) {
    renderEmptyState(summaryEl, EMPTY_MESSAGES.summary);
    return;
  }

  summaryEl.append(
    createSummaryField('Turno', appState.match.turn?.number || 1),
    createSummaryField('Activo', appState.match.turn?.active_side || '-'),
    createSummaryField('Energía', `${me?.energy ?? '-'}/${me?.max_energy ?? '-'}`),
    createSummaryField('IA', `${enemy?.energy ?? '-'}/${enemy?.max_energy ?? '-'}`),
    createSummaryField('Mano / mazo', `${me?.hand_count ?? '-'} / ${me?.library_count ?? '-'}`),
    createSummaryField('Ganador', appState.match.winner || 'sin definir')
  );

  const selection = createSummaryField('Selección', getSelectionSummary({ selectedHandCard, selectedUnit, canPlay }), 'selection-summary');
  summaryEl.appendChild(selection);
}

function renderUnitList(ownUnits = [], enemyUnits = []) {
  const unitListEl = $('#unit-list');
  if (!unitListEl) return;
  clearElement(unitListEl);

  appendTextElement(unitListEl, 'strong', 'Tus unidades');
  if (ownUnits.length) {
    ownUnits.forEach((unit) => unitListEl.appendChild(createUnitListEntry(unit)));
  } else {
    appendTextElement(unitListEl, 'div', EMPTY_MESSAGES.units);
  }

  unitListEl.appendChild(document.createElement('hr'));
  appendTextElement(unitListEl, 'strong', 'Unidades IA');
  if (enemyUnits.length) {
    enemyUnits.forEach((unit) => unitListEl.appendChild(createUnitListEntry(unit)));
  } else {
    appendTextElement(unitListEl, 'div', EMPTY_MESSAGES.units);
  }
}

function renderBoardGrid({ me, enemy, selectedUnit, selectedHandCard, canPlay, width, height, moveTargets, attackTargets, myDeployment, enemyDeployment }) {
  const boardEl = $('#board');
  if (!boardEl) return;

  clearElement(boardEl);
  boardEl.style.gridTemplateColumns = `repeat(${width}, minmax(40px, 1fr))`;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const ownUnit = findUnitAt(me?.units, x, y);
      const enemyUnit = findUnitAt(enemy?.units, x, y);
      const cell = createBoardCell({
        x,
        y,
        ownUnit,
        enemyUnit,
        selectedUnit,
        selectedHandCard,
        canPlay,
        myDeployment,
        enemyDeployment,
        moveTargets,
        attackTargets,
      });
      cell.addEventListener('click', () => {
        onCellClick(x, y).catch((err) => setStatus(err.message, true));
      });
      boardEl.appendChild(cell);
    }
  }

  installCardImageFallbacks(boardEl);
}

function renderBoard() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone);
  if (!appState.match) {
    renderStaticBoard();
    renderEmptyState($('#hand'), EMPTY_MESSAGES.handPreview);
    renderEmptyState($('#match-summary'), EMPTY_MESSAGES.summary);
    renderEmptyState($('#unit-list'), EMPTY_MESSAGES.units);
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

  renderBoardGrid({
    me,
    enemy,
    selectedUnit,
    selectedHandCard,
    canPlay,
    width,
    height,
    moveTargets,
    attackTargets,
    myDeployment,
    enemyDeployment,
  });
  renderHand(me?.hand || [], canPlay);
  renderMatchSummary({ me, enemy, selectedHandCard, selectedUnit, canPlay });
  renderUnitList(me?.units || [], enemy?.units || []);
  renderMatchLog(appState.match.log || []);
}

function populateFamilyFilter(cards = []) {
  if (!familyFilter) return;
  clearElement(familyFilter);

  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = 'Todas las familias';
  familyFilter.appendChild(defaultOption);

  [...new Set(cards.map((card) => card.family).filter(Boolean))].forEach((family) => {
    const option = document.createElement('option');
    option.value = family;
    option.textContent = family;
    familyFilter.appendChild(option);
  });
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
  populateFamilyFilter(cards);
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
