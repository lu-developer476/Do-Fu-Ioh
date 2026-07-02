const CARD_IMAGE_PLACEHOLDER = '/static/core/img/placeholders/card-placeholder.svg';
const EMPTY_MESSAGES = {
  catalog: 'No hay cartas disponibles.',
  matchLog: 'Todavía no hay eventos registrados.',
  hand: 'No quedan cartas en mano.',
  handPreview: 'Tu mano aparecerá acá.',
  summary: 'Iniciá un duelo contra la IA para comenzar.',
  arena: 'Slot libre',
};

const appState = {
  cards: [],
  roomCode: null,
  match: null,
  selectedHandIndex: null,
  selectedUnitId: null,
  actionFeedback: { message: 'Seleccioná una carta o monstruo para jugar.', tone: 'normal' },
  clientLog: [],
};

const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

function setStatus(message, isError = false) {
  const status = $('#auth-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('status-error', isError);
}

function pushClientLog(message) {
  if (!message) return;
  appState.clientLog = [`${new Date().toLocaleTimeString('es-AR')} · ${message}`, ...appState.clientLog].slice(0, 8);
}

function setActionFeedback(message, tone = 'normal', options = {}) {
  appState.actionFeedback = { message, tone };
  if (!options.silentLog) pushClientLog(message);
  const feedback = $('#action-feedback');
  if (!feedback) return;
  feedback.textContent = message;
  feedback.classList.remove('feedback-normal', 'feedback-error', 'feedback-success');
  feedback.classList.add(`feedback-${tone}`);
}

function clearElement(element) { if (element) element.replaceChildren(); }
function appendTextElement(parent, tagName, text, className = '') {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
}
function renderEmptyState(element, message, className = 'small') {
  if (!element) return;
  const empty = document.createElement('div');
  empty.className = className;
  empty.textContent = message;
  element.replaceChildren(empty);
}
function appendBadgeRow(parent, values = []) {
  const row = document.createElement('div');
  row.className = 'meta';
  values.forEach((value) => appendTextElement(row, 'span', value, 'badge'));
  parent.appendChild(row);
  return row;
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map((entry) => entry.trim()).find((entry) => entry.startsWith(prefix))?.slice(prefix.length) || '';
}
function getCsrfToken() {
  const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')?.trim();
  return metaToken && metaToken !== 'NOTPROVIDED' ? metaToken : getCookie('csrftoken');
}
async function api(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if ((options.method || 'GET').toUpperCase() !== 'GET') {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
  }
  const response = await fetch(url, { credentials: 'same-origin', ...options, headers });
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
  if (!response.ok) throw new Error(data.message || `El servidor respondió con error ${response.status}. Probá refrescar el duelo.`);
  return data;
}

function localSeedCards() {
  const seedTag = document.getElementById('cards-seed');
  if (!seedTag) return [];
  try { const parsed = JSON.parse(seedTag.textContent || '[]'); return Array.isArray(parsed) ? parsed : []; } catch { return []; }
}
function resolveCardImage(image) {
  const raw = String(image ?? '').trim();
  if (!raw) return CARD_IMAGE_PLACEHOLDER;
  if (raw.startsWith('data:') || raw.startsWith('blob:')) return raw;
  if (/^https?:\/\//i.test(raw)) { try { return new URL(raw).href; } catch { return CARD_IMAGE_PLACEHOLDER; } }
  if (/^[a-z]+:/i.test(raw)) return CARD_IMAGE_PLACEHOLDER;
  const normalized = raw.replace(/^\.\//, '').replace(/^public\//, '/static/').replace(/^static\//, '/static/');
  return normalized.startsWith('/') ? normalized : `/static/${normalized}`;
}
function createCardImageElement(image, name, className = '') {
  const frame = document.createElement('span');
  frame.className = `card-image-frame${className ? ` ${className}` : ''}`;
  const img = document.createElement('img');
  img.className = ['card-image', className].filter(Boolean).join(' ');
  img.src = resolveCardImage(image);
  img.alt = name || 'Carta sin nombre';
  img.loading = 'lazy';
  img.decoding = 'async';
  const fallback = document.createElement('span');
  fallback.className = 'card-image-fallback';
  fallback.textContent = 'Sin imagen';
  img.addEventListener('error', () => { frame.classList.add('is-fallback'); img.src = CARD_IMAGE_PLACEHOLDER; });
  frame.append(img, fallback);
  return frame;
}

function summarizeCardStats(card = {}) {
  return `PdV ${card.hp ?? '-'} · Esc ${card.shell ?? 0} · PA ${card.action_points ?? '-'} · Coste ${card.summon_cost ?? '?'}`;
}
function stageLabel(stage) { return { base: 'Base', fusion: 'Fusión', evolution: 'Evolución' }[stage] || stage || '-'; }
function formatSideLabel(side) { return side === 'host' ? 'Jugador' : side === 'guest' ? 'IA' : side || '-'; }
function estimateDamage(card = {}) {
  const rank = { base: 0, fusion: 1, evolution: 2 }[card.stage] || 0;
  return (card.action_points || 0) + 2 + rank;
}
function calculatePlayerLife(player = {}) {
  return (player.units || []).reduce((total, unit) => total + Math.max(0, Number(unit.hp_current) || 0), 0);
}
function createSummaryField(label, value, className = '') {
  const item = document.createElement('div');
  item.className = ['summary-field', className].filter(Boolean).join(' ');
  appendTextElement(item, 'strong', `${label}:`);
  item.append(` ${value}`);
  return item;
}
function resolveSides() { return appState.match ? { me: appState.match.host, enemy: appState.match.guest, mySide: 'host' } : { me: null, enemy: null, mySide: null }; }
function isMyTurn(mySide) { return Boolean(appState.match && mySide && appState.match.turn?.active_side === mySide); }
function syncSelectedUnit(me) {
  const selected = me?.units?.find((u) => u.id === appState.selectedUnitId) || null;
  if (!selected) appState.selectedUnitId = null;
  return selected;
}
function getSelectedEnemy(enemy) { return enemy?.units?.find((u) => u.id === appState.selectedUnitId) || null; }

function resetSelections() { appState.selectedHandIndex = null; appState.selectedUnitId = null; }
function resetMatchState({ roomCode = null, match = null, feedbackMessage = EMPTY_MESSAGES.summary, feedbackTone = 'normal' } = {}) {
  appState.roomCode = roomCode; appState.match = match; resetSelections(); setActionFeedback(feedbackMessage, feedbackTone);
}
function applyMatchPayload(data, opts = {}) {
  const match = data?.match ?? null;
  const roomCode = match ? (data?.room_code ?? match.room_code ?? null) : null;
  if (!match || !roomCode) { resetMatchState({ feedbackMessage: opts.emptyFeedbackMessage || EMPTY_MESSAGES.summary, feedbackTone: opts.emptyFeedbackTone || 'normal' }); return false; }
  resetMatchState({ roomCode, match, feedbackMessage: 'Duelo listo. Seleccioná una carta o monstruo.', feedbackTone: 'normal' });
  return true;
}

function renderCatalog() {
  const catalogEl = $('#catalog'); if (!catalogEl) return;
  clearElement(catalogEl);
  const filter = familyFilter?.value || '';
  const filteredCards = appState.cards.filter((card) => !filter || card.family === filter);
  if (!filteredCards.length) return renderEmptyState(catalogEl, EMPTY_MESSAGES.catalog);
  filteredCards.forEach((card) => {
    const article = document.createElement('article');
    article.className = 'card';
    article.appendChild(createCardImageElement(card.image, card.name, 'card-image-catalog'));
    appendTextElement(article, 'h4', card.name);
    appendBadgeRow(article, [card.family, stageLabel(card.stage), summarizeCardStats(card)]);
    appendTextElement(article, 'p', card.description || 'Monstruo listo para invocar.');
    catalogEl.appendChild(article);
  });
}

function createMonsterCard(unit, side, selectedUnit) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = ['arena-card', side === 'host' ? 'ally-card' : 'enemy-card', selectedUnit?.id === unit.id ? 'selected' : ''].filter(Boolean).join(' ');
  button.appendChild(createCardImageElement(unit.card.image, unit.card.name, 'card-image-arena'));
  appendTextElement(button, 'strong', unit.card.name, 'arena-card-name');
  appendBadgeRow(button, [stageLabel(unit.card.stage), unit.card.family, `Slot ${unit.slot + 1}`]);
  const stats = document.createElement('div');
  stats.className = 'stat-grid';
  [['PdV', unit.hp_current], ['Esc', unit.shell_current], ['PA', unit.pa_current], ['Daño', estimateDamage(unit.card)]].forEach(([label, value]) => stats.appendChild(createSummaryField(label, value)));
  button.appendChild(stats);
  button.addEventListener('click', () => onArenaCardClick(unit, side));
  return button;
}

function createEmptySlot(slot, side, canPlay, selectedHandCard) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = ['arena-slot', side === 'host' ? 'ally-slot' : 'enemy-slot', selectedHandCard && side === 'host' && canPlay ? 'summon-ready' : ''].filter(Boolean).join(' ');
  appendTextElement(button, 'span', `Slot ${slot + 1}`, 'slot-label');
  appendTextElement(button, 'strong', EMPTY_MESSAGES.arena);
  if (side === 'host') button.addEventListener('click', () => onSlotClick(slot));
  return button;
}

function renderArenaRow(selector, units = [], side, canPlay, selectedUnit, selectedHandCard) {
  const el = $(selector); if (!el) return;
  clearElement(el);
  const slots = appState.match?.arena?.slots || 5;
  for (let slot = 0; slot < slots; slot += 1) {
    const unit = units.find((item) => item.slot === slot);
    el.appendChild(unit ? createMonsterCard(unit, side, selectedUnit) : createEmptySlot(slot, side, canPlay, selectedHandCard));
  }
}

async function sendAction(actionPayload, failureMessage = 'La acción no pudo resolverse.') {
  const data = await api(`/api/match/${appState.roomCode}/action/`, { method: 'POST', body: JSON.stringify(actionPayload) });
  applyMatchPayload(data, { emptyFeedbackMessage: 'La partida activa ya no existe.', emptyFeedbackTone: 'error' });
  renderGame();
}
async function onSlotClick(slot) {
  const { me, mySide } = resolveSides();
  if (!appState.match || !isMyTurn(mySide)) return setActionFeedback('Todavía no es tu turno.', 'error');
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  if (!selectedHandCard) return setActionFeedback('Seleccioná una carta de tu mano antes de invocar.', 'error');
  await sendAction({ action: 'summon', hand_index: appState.selectedHandIndex, slot }, `No se pudo invocar ${selectedHandCard.name}.`);
  appState.selectedHandIndex = null;
  setActionFeedback(`${selectedHandCard.name} fue invocada en el slot ${slot + 1}.`, 'success');
}
async function onArenaCardClick(unit, side) {
  const { me, enemy, mySide } = resolveSides();
  if (!me || !enemy) return;
  if (side === 'host') {
    appState.selectedUnitId = unit.id; appState.selectedHandIndex = null;
    setActionFeedback(`${unit.card.name} seleccionado. Elegí un monstruo de la IA para atacar.`, 'normal');
    renderGame(); return;
  }
  const attacker = me.units?.find((item) => item.id === appState.selectedUnitId);
  if (!attacker) return setActionFeedback('Seleccioná primero uno de tus monstruos para atacar.', 'error');
  if (!isMyTurn(mySide)) return setActionFeedback('Todavía no es tu turno.', 'error');
  if (!attacker.attackable_unit_ids?.includes(unit.id)) return setActionFeedback(`${attacker.card.name} no puede atacar ahora.`, 'error');
  await sendAction({ action: 'attack', attacker_id: attacker.id, target_id: unit.id }, 'No se pudo concretar el ataque.');
  setActionFeedback(`${attacker.card.name} atacó a ${unit.card.name}.`, 'success');
}

function renderHand(hand = [], canPlay = false) {
  const handEl = $('#hand'); if (!handEl) return;
  clearElement(handEl);
  if (!hand.length) return renderEmptyState(handEl, EMPTY_MESSAGES.hand);
  hand.forEach((card, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}`.trim();
    button.appendChild(createCardImageElement(card.image, card.name, 'card-image-hand'));
    appendTextElement(button, 'h4', card.name, 'hand-card-title');
    appendBadgeRow(button, [stageLabel(card.stage), card.family, summarizeCardStats(card)]);
    button.addEventListener('click', () => {
      if (!canPlay) return setActionFeedback('Todavía no es tu turno.', 'error');
      const isSame = appState.selectedHandIndex === index;
      appState.selectedHandIndex = isSame ? null : index; appState.selectedUnitId = null;
      setActionFeedback(isSame ? 'Carta deseleccionada.' : `Carta seleccionada: ${card.name}. Elegí un slot libre.`, 'normal');
      renderGame();
    });
    handEl.appendChild(button);
  });
}

function renderMatchSummary({ me, enemy }) {
  const summaryEl = $('#match-summary'); if (!summaryEl) return;
  clearElement(summaryEl);
  if (!appState.match) return renderEmptyState(summaryEl, EMPTY_MESSAGES.summary);
  summaryEl.append(
    createSummaryField('Turno', appState.match.turn?.number || 1),
    createSummaryField('Lado activo', formatSideLabel(appState.match.turn?.active_side)),
    createSummaryField('Vida jugador', calculatePlayerLife(me)),
    createSummaryField('Vida IA', calculatePlayerLife(enemy)),
    createSummaryField('Energía', `${me?.energy ?? '-'}/${me?.max_energy ?? '-'}`),
    createSummaryField('Mano / Mazo', `${me?.hand_count ?? '-'}/${me?.library_count ?? '-'}`),
    createSummaryField('Ganador', appState.match.winner ? formatSideLabel(appState.match.winner) : 'sin definir')
  );
}
function renderSelectionDetail({ selectedHandCard, selectedUnit, selectedEnemy }) {
  const el = $('#selection-detail'); if (!el) return;
  clearElement(el);
  const card = selectedHandCard || selectedUnit?.card || selectedEnemy?.card;
  if (!card) return renderEmptyState(el, 'Seleccioná una carta o monstruo para ver sus características.');
  el.append(createSummaryField('Nombre', card.name), createSummaryField('Familia', card.family), createSummaryField('Etapa', stageLabel(card.stage)), createSummaryField('Características', summarizeCardStats(card)), createSummaryField('Daño estimado', estimateDamage(card)), createSummaryField('Descripción', card.description || 'Sin descripción.'));
  if (selectedUnit || selectedEnemy) el.append(createSummaryField('Estado actual', `PdV ${selectedUnit?.hp_current ?? selectedEnemy?.hp_current} · Esc ${selectedUnit?.shell_current ?? selectedEnemy?.shell_current} · PA ${selectedUnit?.pa_current ?? selectedEnemy?.pa_current}`));
}
function renderMatchLog(logEntries = []) {
  const logEl = $('#match-log'); if (!logEl) return;
  clearElement(logEl);
  const entries = [...(appState.clientLog || []), ...((Array.isArray(logEntries) ? logEntries : []).map(String))];
  if (!entries.length) return renderEmptyState(logEl, EMPTY_MESSAGES.matchLog);
  const list = document.createElement('ol'); list.className = 'match-log-list';
  entries.forEach((entry, index) => { const item = document.createElement('li'); item.className = 'match-log-item'; appendTextElement(item, 'span', String(index + 1).padStart(2, '0'), 'match-log-order'); appendTextElement(item, 'p', entry); list.appendChild(item); });
  logEl.appendChild(list);
}

function renderGame() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone, { silentLog: true });
  if (!appState.match) {
    renderEmptyState($('#hand'), EMPTY_MESSAGES.handPreview); renderEmptyState($('#match-summary'), EMPTY_MESSAGES.summary); renderEmptyState($('#selection-detail'), 'Sin selección.'); renderEmptyState($('#player-arena'), EMPTY_MESSAGES.arena, 'arena-slot'); renderEmptyState($('#enemy-arena'), EMPTY_MESSAGES.arena, 'arena-slot'); renderMatchLog(); return;
  }
  const { me, enemy, mySide } = resolveSides();
  const canPlay = isMyTurn(mySide);
  const selectedUnit = syncSelectedUnit(me);
  const selectedEnemy = getSelectedEnemy(enemy);
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  renderArenaRow('#enemy-arena', enemy?.units || [], 'guest', canPlay, selectedUnit, selectedHandCard);
  renderArenaRow('#player-arena', me?.units || [], 'host', canPlay, selectedUnit, selectedHandCard);
  renderHand(me?.hand || [], canPlay);
  renderMatchSummary({ me, enemy });
  renderSelectionDetail({ selectedHandCard, selectedUnit, selectedEnemy });
  renderMatchLog(appState.match.log || []);
}

function populateFamilyFilter(cards = []) {
  if (!familyFilter) return; clearElement(familyFilter);
  const defaultOption = document.createElement('option'); defaultOption.value = ''; defaultOption.textContent = 'Todas las familias'; familyFilter.appendChild(defaultOption);
  [...new Set(cards.map((card) => card.family).filter(Boolean))].forEach((family) => { const option = document.createElement('option'); option.value = family; option.textContent = family; familyFilter.appendChild(option); });
}
async function loadCards() {
  let cards = [];
  try { const data = await api('/api/cards/'); cards = data.cards || []; } catch { cards = localSeedCards(); }
  if (!cards.length) cards = localSeedCards();
  appState.cards = cards; populateFamilyFilter(cards); renderCatalog();
}
async function loadActiveMatch() {
  const data = await api('/api/match/active/');
  applyMatchPayload(data, { emptyFeedbackMessage: 'No hay duelo activo. Hacé clic en "Jugar vs IA" para iniciar.' }); renderGame();
}
async function createAIMatch() { const data = await api('/api/match/create-vs-ai/', { method: 'POST', body: '{}' }); applyMatchPayload(data); renderGame(); setStatus('Duelo nuevo creado con todos los monstruos barajados en mano.'); }
async function shuffleMonsters() { await createAIMatch(); setActionFeedback('Monstruos barajados: tu mano inicial incluye todo el catálogo.', 'success'); }
async function refreshMatch() { if (!appState.roomCode) return loadActiveMatch(); const data = await api(`/api/match/${appState.roomCode}/`); applyMatchPayload(data); renderGame(); }
async function endTurn() { if (!appState.roomCode) throw new Error('No hay duelo activo.'); await sendAction({ action: 'end_turn' }); resetSelections(); setActionFeedback('Turno terminado. La IA resolvió su respuesta.', 'success'); renderGame(); }
function bindAsyncButton(selector, handler) {
  const button = $(selector); if (!button) return;
  const idleLabel = button.textContent; const loadingLabel = button.dataset.loadingLabel || 'Procesando...';
  button.addEventListener('click', async () => { if (button.disabled) return; button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = loadingLabel; try { await handler(); } catch (err) { setStatus(err.message || 'Error inesperado', true); } finally { button.disabled = false; button.setAttribute('aria-busy', 'false'); button.textContent = idleLabel; } });
}
function boot() {
  renderGame(); bindAsyncButton('#create-ai-match', createAIMatch); bindAsyncButton('#shuffle-monsters', shuffleMonsters); bindAsyncButton('#refresh-state', refreshMatch); bindAsyncButton('#end-turn-btn', endTurn); familyFilter?.addEventListener('change', renderCatalog);
  loadCards().then(loadActiveMatch).catch((err) => { setStatus(err.message || 'No se pudo iniciar el juego.', true); setActionFeedback('No se pudo cargar el duelo. Probá reiniciar con "Jugar vs IA".', 'error'); renderGame(); }).finally(() => { if (!appState.match) setStatus('Sin login: hacé clic en "Jugar vs IA" para iniciar.'); });
}
document.addEventListener('DOMContentLoaded', boot, { once: true });
