const CARD_IMAGE_PLACEHOLDER = '/static/core/img/placeholders/card-placeholder.svg';
const STORAGE_KEY = 'do_fu_ioh_backendless_match_v1';
const EMPTY_MESSAGES = { catalog: 'No hay cartas disponibles para mostrar.', matchLog: 'Aún no hay actividad registrada.', hand: 'No quedan cartas en la mano.', handPreview: 'La mano se mostrará al iniciar el duelo.', summary: 'Iniciá un duelo para ver el estado.', arena: 'Espacio libre' };
const STAGE_RANK = { base: 0, fusion: 1, evolution: 2 };
const MAX_ENERGY = 10;
const FREE_SUMMON_COST = 0;
const BOARD_WIDTH = 9;
const BOARD_HEIGHT = 13;
const DEPLOY_ROWS = { host: [BOARD_HEIGHT - 1], guest: [0] };
const INITIAL_HAND_OPTIONS = new Set([1, 2, 5]);
const appState = { cards: [], roomCode: null, match: null, selectedHandIndex: null, selectedUnitId: null, selectedCatalogCardIds: new Set(), selectedFamily: '', actionFeedback: { message: 'Seleccioná una carta o una unidad para continuar.', tone: 'normal' }, clientLog: [], combatEffects: [], aiPlayback: false, hasPromptedInitialHand: false };
const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');
function setStatus(message, isError = false) { const status = $('#auth-status'); if (!status) return; status.textContent = message; status.classList.toggle('status-error', isError); }
function pushClientLog(message) { if (!message) return; appState.clientLog = [`${new Date().toLocaleTimeString('es-AR')} · ${message}`, ...appState.clientLog].slice(0, 8); }
function setActionFeedback(message, tone = 'normal', options = {}) { appState.actionFeedback = { message, tone }; if (!options.silentLog) pushClientLog(message); const feedback = $('#action-feedback'); if (!feedback) return; feedback.textContent = message; feedback.classList.remove('feedback-normal', 'feedback-error', 'feedback-success'); feedback.classList.add(`feedback-${tone}`); }
function clearElement(element) { if (element) element.replaceChildren(); }
function appendTextElement(parent, tagName, text, className = '') { const element = document.createElement(tagName); if (className) element.className = className; element.textContent = text; parent.appendChild(element); return element; }
function renderEmptyState(element, message, className = 'small') { if (!element) return; const empty = document.createElement('div'); empty.className = className; empty.textContent = message; element.replaceChildren(empty); }
function appendBadgeRow(parent, values = []) { const row = document.createElement('div'); row.className = 'meta'; values.forEach((value) => appendTextElement(row, 'span', value, 'badge')); parent.appendChild(row); return row; }
function localSeedCards() { const seedTag = document.getElementById('cards-seed'); if (!seedTag) return []; try { const parsed = JSON.parse(seedTag.textContent || '[]'); return Array.isArray(parsed) ? parsed : []; } catch { return []; } }
function resolveCardImage(image) { const raw = String(image ?? '').trim(); if (!raw) return CARD_IMAGE_PLACEHOLDER; if (raw.startsWith('data:') || raw.startsWith('blob:')) return raw; if (/^https?:\/\//i.test(raw)) { try { return new URL(raw).href; } catch { return CARD_IMAGE_PLACEHOLDER; } } if (/^[a-z]+:/i.test(raw)) return CARD_IMAGE_PLACEHOLDER; const normalized = raw.replace(/^\.\//, '').replace(/^public\//, '/static/').replace(/^static\//, '/static/'); return normalized.startsWith('/') ? normalized : `/static/${normalized}`; }
function createCardImageElement(image, name, className = '') { const frame = document.createElement('span'); frame.className = `card-image-frame${className ? ` ${className}` : ''}`; const img = document.createElement('img'); img.className = ['card-image', className].filter(Boolean).join(' '); img.src = resolveCardImage(image); img.alt = name || 'Carta sin nombre'; img.loading = 'lazy'; img.decoding = 'async'; const fallback = document.createElement('span'); fallback.className = 'card-image-fallback'; fallback.textContent = 'Imagen no disponible'; img.addEventListener('error', () => { frame.classList.add('is-fallback'); img.src = CARD_IMAGE_PLACEHOLDER; }); frame.append(img, fallback); return frame; }
function cardImage(card = {}) { return card.image || card.image_fallback || CARD_IMAGE_PLACEHOLDER; }
function hpLabel(card = {}) {
  const hpMin = Number.isInteger(card.hp_min) ? card.hp_min : card.hp;
  const hpMax = Number.isInteger(card.hp_max) ? card.hp_max : card.hp;
  if (!Number.isInteger(hpMin) && !Number.isInteger(hpMax)) return '-';
  return hpMin === hpMax ? `${hpMax}` : `${hpMin}-${hpMax}`;
}
function summarizeCardStats(card = {}) { return `PdV ${hpLabel(card)} · PdE ${card.shell ?? 0} · PA ${card.action_points ?? '-'} · PM ${card.movement_points ?? '-'} · Invocación gratis`; }
function stageLabel(stage) { return { base: 'Base', fusion: 'Fusión', evolution: 'Evolución' }[stage] || stage || '-'; }
function formatSideLabel(side) { return side === 'host' ? 'Jugador' : side === 'guest' ? 'IA' : side || '-'; }
function estimateDamage(card = {}) { return (card.action_points || 0) + 2 + (STAGE_RANK[card.stage] || 0); }
function calculatePlayerLife(player = {}) { return (player.units || []).reduce((total, unit) => total + Math.max(0, Number(unit.hp_current) || 0), 0); }
function createSummaryField(label, value, className = '') { const item = document.createElement('div'); item.className = ['summary-field', className].filter(Boolean).join(' '); appendTextElement(item, 'strong', `${label}:`); item.append(` ${value}`); return item; }
function resolveSides() { return appState.match ? { me: appState.match.host, enemy: appState.match.guest, mySide: 'host' } : { me: null, enemy: null, mySide: null }; }
function isMyTurn(mySide) { return Boolean(appState.match && mySide && appState.match.turn?.active_side === mySide); }
function syncSelectedUnit(me) { const selected = me?.units?.find((u) => u.id === appState.selectedUnitId) || null; if (!selected) appState.selectedUnitId = null; return selected; }
function getSelectedEnemy(enemy) { return enemy?.units?.find((u) => u.id === appState.selectedUnitId) || null; }
function resetSelections() { appState.selectedHandIndex = null; appState.selectedUnitId = null; }
function shuffle(items) { return [...items].sort(() => Math.random() - 0.5); }
function summonCost(card = {}) { return FREE_SUMMON_COST; }
function normalizeCard(card, index) { return { ...card, id: card.id ?? index + 1, summon_cost: summonCost(card) }; }
function createPlayer(side, cards) { const hand = cards.map((card, index) => normalizeCard(card, index)); return { side, energy: 1, max_energy: 1, hand, library: [], library_count: 0, hand_count: hand.length, units: [], summons_this_turn: 0, summon_sequence: 0 }; }
function persistMatch() { if (appState.match) localStorage.setItem(STORAGE_KEY, JSON.stringify({ roomCode: appState.roomCode, match: appState.match })); else localStorage.removeItem(STORAGE_KEY); }
function loadStoredMatch() { try { const payload = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); if (payload?.match) { appState.roomCode = payload.roomCode || payload.match.room_code; appState.match = payload.match; return true; } } catch { localStorage.removeItem(STORAGE_KEY); } return false; }
function refreshCounts() { ['host', 'guest'].forEach((side) => { const p = appState.match[side]; p.hand_count = p.hand.length; p.library_count = p.library.length; }); }
function appendLog(message) { appState.match.log.push(`${new Date().toLocaleTimeString('es-AR')} · ${message}`); appState.match.log = appState.match.log.slice(-18); }
function randomId(prefix) { return globalThis.crypto?.randomUUID?.() || `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`; }
function delay(ms = 620) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function pushCombatEffect(effect = {}) {
  const id = randomId('fx');
  appState.combatEffects = [...(appState.combatEffects || []), { id, createdAt: Date.now(), ...effect }].slice(-12);
  setTimeout(() => { appState.combatEffects = (appState.combatEffects || []).filter((item) => item.id !== id); renderGame(); }, 1150);
}
function effectsAt(x, y) { return (appState.combatEffects || []).filter((effect) => effect.x === x && effect.y === y); }
function movementRange(card = {}) { return Math.max(0, Number(card.movement_points) || 0); }
function spellRange(card = {}) { return Math.min(7, 2 + (STAGE_RANK[card.stage] || 0) + Math.floor((card.action_points || 0) / 2)); }
function unitAt(x, y) { return [...(appState.match?.host.units || []), ...(appState.match?.guest.units || [])].find((unit) => unit.x === x && unit.y === y); }
function nextSummonLabel(side) { const player = appState.match?.[side]; if (!player) return `${side === 'host' ? 'J' : 'IA'}?`; player.summon_sequence = (player.summon_sequence || 0) + 1; return `${side === 'host' ? 'J' : 'IA'}${player.summon_sequence}`; }
function unitBattleLabel(unit) { return unit.battle_label || `${unit.owner === 'host' ? 'J' : 'IA'}?`; }
function distance(a, b) { return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); }
function buildUnit(side, card, position) { return { id: randomId(side), owner: side, battle_label: nextSummonLabel(side), slot: position.x, x: position.x, y: position.y, card, hp_current: card.hp, shell_current: card.shell || 0, pa_current: card.action_points || 1, move_points: movementRange(card), can_act: true, summoned_turn: appState.match.turn.number, attack_range: spellRange(card), attackable_unit_ids: [] }; }
function deployCells(side) { const rows = DEPLOY_ROWS[side] || []; const occupied = new Set([...(appState.match?.host.units || []), ...(appState.match?.guest.units || [])].map((unit) => `${unit.x},${unit.y}`)); const cells = []; rows.forEach((y) => { for (let x = 0; x < BOARD_WIDTH; x += 1) if (!occupied.has(`${x},${y}`)) cells.push({ x, y }); }); return cells; }
function openSlots(player) { return deployCells(player.side).slice(0, BOARD_WIDTH).map((cell) => cell.x); }
function updateDerivedCombat() { if (!appState.match) return; ['host', 'guest'].forEach((side) => { const enemy = side === 'host' ? appState.match.guest : appState.match.host; appState.match[side].units.forEach((unit) => { unit.move_points = movementRange(unit.card); unit.attack_range = spellRange(unit.card); unit.attackable_unit_ids = unit.can_act && unit.pa_current > 0 ? enemy.units.filter((target) => distance(unit, target) <= unit.attack_range).map((target) => target.id).sort() : []; }); }); }
function checkWinner(actingSide) { const alive = (p) => Boolean(p.units.length || p.hand.length || p.library.length); const host = alive(appState.match.host); const guest = alive(appState.match.guest); if (!host || !guest) appState.match.winner = host ? 'host' : guest ? 'guest' : actingSide; }
function resetTurn(player) { player.summons_this_turn = 0; player.max_energy = Math.min(MAX_ENERGY, player.max_energy + 1); player.energy = player.max_energy; player.units.forEach((unit) => { unit.pa_current = unit.card.action_points || 1; unit.can_act = true; }); }
function pickInitialCards(selectedIds = [], count = 5) { const selected = selectedIds.map(String); const selectedCards = selected.map((id) => appState.cards.find((card) => String(card.id) === id)).filter(Boolean); const pool = appState.cards.filter((card) => !selected.includes(String(card.id))); return [...selectedCards, ...shuffle(pool)].slice(0, count); }
function startLocalMatch(selectedIds = [], requestedCount = 5) { const handSize = INITIAL_HAND_OPTIONS.has(Number(requestedCount)) ? Number(requestedCount) : 5; const hostCards = pickInitialCards(selectedIds, handSize); const guestCards = shuffle(appState.cards).slice(0, handSize); const roomCode = `local-${Date.now()}`; appState.roomCode = roomCode; appState.match = { room_code: roomCode, mode: 'local_vs_ai', ai_difficulty: 'normal', arena: { slots: BOARD_WIDTH }, board: { width: BOARD_WIDTH, height: BOARD_HEIGHT }, initial_hand_size: handSize, turn: { number: 1, active_side: 'host' }, host: createPlayer('host', hostCards), guest: createPlayer('guest', guestCards), winner: null, log: [`Duelo local iniciado con ${handSize} carta(s) iniciales contra la IA.`, `Tablero táctico ${BOARD_HEIGHT} × ${BOARD_WIDTH} activo para movimiento y hechizos.`] }; resetSelections(); updateDerivedCombat(); persistMatch(); }
function applySummon(side, handIndex, position) { const player = appState.match[side]; if (!deployCells(side).some((cell) => cell.x === position.x && cell.y === position.y)) throw new Error('Esa celda no está disponible para invocar.'); const card = player.hand[handIndex]; if (!card) throw new Error('Carta inválida.'); player.hand.splice(handIndex, 1); player.summons_this_turn += 1; player.units.push(buildUnit(side, card, position)); appendLog(`${formatSideLabel(side)} invocó ${card.name} en (${position.x + 1}, ${position.y + 1}).`); }
function applyMove(side, unitId, position) { const unit = appState.match[side].units.find((item) => item.id === unitId); if (!unit || !unit.can_act || unit.pa_current <= 0) throw new Error('Movimiento inválido.'); if (position.x < 0 || position.y < 0 || position.x >= BOARD_WIDTH || position.y >= BOARD_HEIGHT || unitAt(position.x, position.y)) throw new Error('La celda está ocupada o fuera del tablero.'); if (distance(unit, position) > unit.move_points) throw new Error('La celda está fuera del rango de movimiento.'); const from = { x: unit.x, y: unit.y }; unit.x = position.x; unit.y = position.y; unit.slot = position.x; unit.pa_current -= 1; unit.can_act = unit.pa_current > 0; pushCombatEffect({ x: from.x, y: from.y, text: 'Salida', tone: 'move ghost' }); pushCombatEffect({ x: position.x, y: position.y, text: '-1 PA', tone: 'move' }); appendLog(`${formatSideLabel(side)} movió ${unit.card.name} de (${from.x + 1}, ${from.y + 1}) a (${position.x + 1}, ${position.y + 1}).`); }
function applyAttack(side, attackerId, targetId) { const actor = appState.match[side]; const enemySide = side === 'host' ? 'guest' : 'host'; const enemy = appState.match[enemySide]; const attacker = actor.units.find((unit) => unit.id === attackerId); const target = enemy.units.find((unit) => unit.id === targetId); if (!attacker || !target || attacker.pa_current <= 0 || !attacker.can_act || distance(attacker, target) > attacker.attack_range) throw new Error('Hechizo inválido o fuera de rango.'); attacker.pa_current -= 1; attacker.can_act = attacker.pa_current > 0; const previousHp = target.hp_current; const previousShell = target.shell_current; const power = estimateDamage(attacker.card); const absorbed = Math.min(target.shell_current, Math.max(0, power - 1)); target.shell_current = Math.max(0, target.shell_current - absorbed); const damage = Math.max(1, power - absorbed); target.hp_current -= damage; const hpLost = Math.max(0, previousHp - Math.max(0, target.hp_current)); pushCombatEffect({ x: attacker.x, y: attacker.y, text: '-1 PA', tone: 'cast' }); pushCombatEffect({ x: target.x, y: target.y, text: `-${damage} daño`, tone: 'damage' }); pushCombatEffect({ x: target.x, y: target.y, text: `-${hpLost} PdV`, tone: 'hp' }); if (absorbed > 0) pushCombatEffect({ x: target.x, y: target.y, text: `-${previousShell - target.shell_current} PdE`, tone: 'shield' }); appendLog(`${formatSideLabel(side)} lanzó un hechizo con ${attacker.card.name}: ${damage} daño, ${hpLost} PdV perdidos${absorbed ? ` y ${absorbed} PdE reducidos` : ''}.`); if (target.hp_current <= 0) { enemy.units = enemy.units.filter((unit) => unit.id !== target.id); appendLog(`${target.card.name} fue derrotado.`); } }
function endSideTurn(side) { const nextSide = side === 'host' ? 'guest' : 'host'; appState.match.turn.active_side = nextSide; if (nextSide === 'host') appState.match.turn.number += 1; resetTurn(appState.match[nextSide]); appendLog(`Fin del turno de ${formatSideLabel(side)}.`); }
function stepToward(unit, target) { const candidates = [{ x: unit.x + Math.sign(target.x - unit.x), y: unit.y }, { x: unit.x, y: unit.y + Math.sign(target.y - unit.y) }, { x: unit.x + Math.sign(target.x - unit.x), y: unit.y + Math.sign(target.y - unit.y) }].filter((cell) => cell.x >= 0 && cell.y >= 0 && cell.x < BOARD_WIDTH && cell.y < BOARD_HEIGHT && !unitAt(cell.x, cell.y)); return candidates.sort((a, b) => distance(a, target) - distance(b, target))[0]; }
async function runAiTurn() {
  if (appState.match.winner || appState.match.turn.active_side !== 'guest') return;
  appState.aiPlayback = true;
  setActionFeedback('La IA está resolviendo sus movimientos...', 'normal');
  const ai = appState.match.guest;
  while (ai.hand.length && deployCells('guest').length) {
    const bestIndex = ai.hand
      .map((card, index) => ({ card, index }))
      .sort((a, b) => (STAGE_RANK[b.card.stage] || 0) - (STAGE_RANK[a.card.stage] || 0) || (b.card.action_points || 0) - (a.card.action_points || 0) || (b.card.hp || 0) - (a.card.hp || 0))[0]?.index;
    if (bestIndex === undefined) break;
    applySummon('guest', bestIndex, deployCells('guest')[0]);
    refreshCounts(); updateDerivedCombat(); renderGame(); await delay();
  }
  for (const unit of [...ai.units]) {
    while (!appState.match.winner && unit.can_act && appState.match.host.units.length) {
      const target = [...appState.match.host.units].sort((a, b) => distance(unit, a) - distance(unit, b) || a.hp_current - b.hp_current)[0];
      if (distance(unit, target) <= unit.attack_range) { applyAttack('guest', unit.id, target.id); checkWinner('guest'); }
      else { const nextCell = stepToward(unit, target); if (!nextCell) break; applyMove('guest', unit.id, nextCell); }
      refreshCounts(); updateDerivedCombat(); renderGame(); await delay();
    }
  }
  if (!appState.match.winner) endSideTurn('guest');
  appState.aiPlayback = false;
}
async function applyLocalAction(payload) { if (!appState.match || appState.match.winner) throw new Error('La partida ya terminó o no existe.'); if (appState.match.turn.active_side !== 'host') throw new Error('El turno activo corresponde a la IA.'); if (payload.action === 'summon') applySummon('host', payload.hand_index, payload.position); else if (payload.action === 'move') applyMove('host', payload.unit_id, payload.position); else if (payload.action === 'attack') applyAttack('host', payload.attacker_id, payload.target_id); else if (payload.action === 'end_turn') endSideTurn('host'); checkWinner('host'); refreshCounts(); updateDerivedCombat(); renderGame(); if (appState.match.turn.active_side === 'guest' && !appState.match.winner) await runAiTurn(); refreshCounts(); updateDerivedCombat(); persistMatch(); }
async function sendAction(actionPayload) { await applyLocalAction(actionPayload); renderGame(); }
async function onSlotClick() { const firstDeployCell = deployCells('host')[0]; if (firstDeployCell) return onBoardCellClick(firstDeployCell.x, firstDeployCell.y); return setActionFeedback('No hay celdas libres para invocar.', 'error'); }
async function onArenaCardClick(unit, side) { const { me, enemy, mySide } = resolveSides(); if (!me || !enemy) return; if (side === 'host') { appState.selectedUnitId = unit.id; appState.selectedHandIndex = null; setActionFeedback(`${unit.card.name} seleccionado. Elegí una unidad rival para atacar.`, 'normal'); renderGame(); return; } const attacker = me.units?.find((item) => item.id === appState.selectedUnitId); if (!attacker) return setActionFeedback('Seleccioná primero una unidad propia para atacar.', 'error'); if (!isMyTurn(mySide)) return setActionFeedback('El turno activo corresponde a la IA.', 'error'); try { await sendAction({ action: 'attack', attacker_id: attacker.id, target_id: unit.id }); setActionFeedback(`${attacker.card.name} lanzó un hechizo contra ${unit.card.name}.`, 'success'); } catch (err) { setActionFeedback(err.message, 'error'); } }

async function onBoardCellClick(x, y) {
  const { me, enemy, mySide } = resolveSides();
  if (!appState.match || !isMyTurn(mySide)) return setActionFeedback('El turno activo corresponde a la IA.', 'error');
  const occupant = unitAt(x, y);
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  const selectedUnit = me?.units?.find((unit) => unit.id === appState.selectedUnitId);
  try {
    if (occupant) return onArenaCardClick(occupant, occupant.owner);
    if (selectedHandCard) {
      await sendAction({ action: 'summon', hand_index: appState.selectedHandIndex, position: { x, y } });
      appState.selectedHandIndex = null;
      return setActionFeedback(`${selectedHandCard.name} fue invocada en (${x + 1}, ${y + 1}).`, 'success');
    }
    if (selectedUnit) {
      await sendAction({ action: 'move', unit_id: selectedUnit.id, position: { x, y } });
      return setActionFeedback(`${selectedUnit.card.name} se movió a (${x + 1}, ${y + 1}).`, 'success');
    }
    return setActionFeedback('Seleccioná una carta de la mano o una unidad propia primero.', 'error');
  } catch (err) { return setActionFeedback(err.message, 'error'); }
}
function renderBoard({ me, enemy, canPlay, selectedUnit, selectedHandCard }) {
  const board = $('#tactical-board'); if (!board) return;
  clearElement(board);
  board.style.gridTemplateColumns = `repeat(${BOARD_WIDTH}, minmax(0, var(--board-cell-size)))`;
  const deployHost = new Set(deployCells('host').map((c) => `${c.x},${c.y}`));
  const deployGuestRows = new Set(DEPLOY_ROWS.guest);
  const moveHints = new Set(); const attackHints = new Set();
  if (canPlay && selectedUnit) {
    for (let y = 0; y < BOARD_HEIGHT; y += 1) for (let x = 0; x < BOARD_WIDTH; x += 1) {
      const key = `${x},${y}`; const probe = { x, y };
      if (!unitAt(x, y) && distance(selectedUnit, probe) <= selectedUnit.move_points) moveHints.add(key);
      if (distance(selectedUnit, probe) <= selectedUnit.attack_range) attackHints.add(key);
    }
  }
  const units = new Map([...(me?.units || []), ...(enemy?.units || [])].map((unit) => [`${unit.x},${unit.y}`, unit]));
  for (let y = 0; y < BOARD_HEIGHT; y += 1) for (let x = 0; x < BOARD_WIDTH; x += 1) {
    const key = `${x},${y}`; const unit = units.get(key);
    const cell = document.createElement('button'); cell.type = 'button';
    cell.className = ['cell', (x + y) % 2 ? 'square-dark' : 'square-light', unit ? 'has-unit' : '', unit?.owner === 'host' ? 'ally' : '', unit?.owner === 'guest' ? 'enemy' : '', DEPLOY_ROWS.host.includes(y) ? 'deploy-ally' : '', deployGuestRows.has(y) ? 'deploy-enemy' : '', selectedUnit?.id === unit?.id ? 'selected' : '', selectedHandCard && deployHost.has(key) ? 'hint-summon' : '', moveHints.has(key) ? 'hint-move' : '', unit?.owner === 'guest' && attackHints.has(key) ? 'hint-attack' : '', canPlay ? 'is-actionable' : ''].filter(Boolean).join(' ');
    if (unit) cell.appendChild(renderToken(unit, unit.owner === 'host' ? 'ally' : 'enemy', selectedUnit)); else appendTextElement(cell, 'span', '', 'cell-empty-state');
    const cellEffects = effectsAt(x, y);
    if (cellEffects.length) { const fxStack = document.createElement('span'); fxStack.className = 'combat-fx-stack'; cellEffects.forEach((effect) => appendTextElement(fxStack, 'span', effect.text, `combat-fx combat-fx-${effect.tone}`)); cell.appendChild(fxStack); }
    cell.addEventListener('click', () => onBoardCellClick(x, y)); board.appendChild(cell);
  }

}
function formatSpells(card = {}) {
  const spells = Array.isArray(card.spells) ? card.spells : [];
  if (!spells.length) return 'Hechizos: sin hechizos configurados.';
  return `Hechizos: ${spells.map((spell) => `${spell.name} (${spell.cost ?? '-'} PA, rango ${spell.range ?? '-'})`).join(' · ')}`;
}
function unitTooltip(unit) {
  return `${unit.card.name}
PdV: ${unit.hp_current}/${unit.card.hp}
PdE: ${unit.shell_current}/${unit.card.shell || 0}
PA usados: ${Math.max(0, (unit.card.action_points || 0) - (unit.pa_current || 0))}/${unit.card.action_points || 0}
PA restantes: ${unit.pa_current || 0}
PM: ${unit.move_points || 0}
Rango hechizo: ${unit.attack_range ?? '-'}
${formatSpells(unit.card)}`;
}
function renderToken(unit, tone, selectedUnit) {
  const token = document.createElement('span'); token.className = `token token-${tone} ${selectedUnit?.id === unit.id ? 'token-selected' : ''}`.trim(); token.title = unitTooltip(unit); token.setAttribute('aria-label', unitTooltip(unit));
  token.appendChild(createCardImageElement(cardImage(unit.card), unit.card.name, 'card-image-token'));
  return token;
}
function renderCatalog() {
  const catalogEl = $('#catalog'); if (!catalogEl) return;
  clearElement(catalogEl);
  const family = appState.selectedFamily || '';
  const cards = appState.cards.filter((card) => !family || card.family === family);
  if (!cards.length) return renderEmptyState(catalogEl, EMPTY_MESSAGES.catalog);
  cards.forEach((card) => {
    const article = document.createElement('article');
    article.className = 'card';
    article.appendChild(createCardImageElement(cardImage(card), card.name, 'card-image-catalog'));
    appendTextElement(article, 'h4', card.name);
    appendBadgeRow(article, [stageLabel(card.stage), card.family, summarizeCardStats(card)]);
    appendTextElement(article, 'p', formatSpells(card), 'spell-summary');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost catalog-select-button';
    button.setAttribute('aria-pressed', String(appState.selectedCatalogCardIds.has(String(card.id))));
    button.textContent = appState.selectedCatalogCardIds.has(String(card.id)) ? 'Quitar / cambiar' : 'Agregar a mano';
    button.addEventListener('click', () => toggleCatalogSelection(card));
    article.appendChild(button);
    catalogEl.appendChild(article);
  });
}
function renderArenaCard(unit, side, selectedUnit) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `arena-card ${side === 'host' ? 'ally-card' : 'enemy-card'} ${selectedUnit?.id === unit.id ? 'selected' : ''}`.trim();
  button.appendChild(createCardImageElement(cardImage(unit.card), unit.card.name, 'card-image-arena'));
  appendTextElement(button, 'strong', `${unitBattleLabel(unit)} · ${unit.card.name}`, 'arena-card-name');
  const stats = document.createElement('div');
  stats.className = 'stat-grid';
  stats.append(createSummaryField('PdV', unit.hp_current), createSummaryField('PdE', unit.shell_current), createSummaryField('PA', unit.pa_current), createSummaryField('PM', unit.move_points), createSummaryField('Rango', unit.attack_range ?? '-'));
  appendTextElement(stats, 'span', formatSpells(unit.card), 'spell-summary');
  button.appendChild(stats);
  button.addEventListener('click', () => onArenaCardClick(unit, side));
  return button;
}
function renderArenaRow(selector, units = [], side, canPlay, selectedUnit, selectedHandCard) {
  const row = $(selector); if (!row) return;
  clearElement(row);
  const bySlot = new Map(units.map((unit) => [unit.slot, unit]));
  for (let slot = 0; slot < BOARD_WIDTH; slot += 1) {
    const unit = bySlot.get(slot);
    if (unit) {
      row.appendChild(renderArenaCard(unit, side, selectedUnit));
    } else {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `arena-slot ${side === 'host' && canPlay && selectedHandCard ? 'summon-ready' : ''}`.trim();
      appendTextElement(button, 'span', `Espacio ${slot + 1}`, 'slot-label');
      appendTextElement(button, 'span', side === 'host' && selectedHandCard ? `Invocar ${selectedHandCard.name}` : EMPTY_MESSAGES.arena);
      button.disabled = side !== 'host';
      button.addEventListener('click', () => onSlotClick(slot));
      row.appendChild(button);
    }
  }
}
function renderHand(hand = [], canPlay = false) {
  const handEl = $('#hand'); if (!handEl) return;
  clearElement(handEl);
  if (!hand.length) return renderEmptyState(handEl, EMPTY_MESSAGES.hand);
  hand.forEach((card, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}`.trim();
    button.appendChild(createCardImageElement(cardImage(card), card.name, 'card-image-hand'));
    appendTextElement(button, 'h4', card.name, 'hand-card-title');
    appendBadgeRow(button, [stageLabel(card.stage), card.family, summarizeCardStats(card)]);
    button.addEventListener('click', () => {
      if (!canPlay) return setActionFeedback('El turno activo corresponde a la IA.', 'error');
      const isSame = appState.selectedHandIndex === index;
      appState.selectedHandIndex = isSame ? null : index; appState.selectedUnitId = null;
      setActionFeedback(isSame ? 'Selección cancelada.' : `Carta seleccionada: ${card.name}. Elegí un espacio libre.`, 'normal');
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
    createSummaryField('Invocación', 'gratis, sin límite por turno'),
    createSummaryField('Mano / Mazo', `${me?.hand_count ?? '-'}/${me?.library_count ?? '-'}`),
    createSummaryField('Ganador', appState.match.winner ? formatSideLabel(appState.match.winner) : 'sin definir')
  );
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
    renderEmptyState($('#hand'), EMPTY_MESSAGES.handPreview); renderEmptyState($('#match-summary'), EMPTY_MESSAGES.summary); renderBoard({ me: { units: [] }, enemy: { units: [] }, canPlay: false, selectedUnit: null, selectedHandCard: null }); renderMatchLog(); return;
  }
  const { me, enemy, mySide } = resolveSides();
  const canPlay = isMyTurn(mySide);
  const selectedUnit = syncSelectedUnit(me);
  const selectedHandCard = me?.hand?.[appState.selectedHandIndex] || null;
  renderBoard({ me, enemy, canPlay, selectedUnit, selectedHandCard });
  renderHand(me?.hand || [], canPlay);
  renderMatchSummary({ me, enemy });
  renderMatchLog(appState.match.log || []);
}

function createFamilyFilterButton(label, value) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'filter-chip';
  button.textContent = label;
  button.setAttribute('aria-pressed', String((appState.selectedFamily || '') === value));
  button.addEventListener('click', () => {
    appState.selectedFamily = value;
    populateFamilyFilter(appState.cards);
    renderCatalog();
  });
  return button;
}
function populateFamilyFilter(cards = []) {
  if (!familyFilter) return;
  clearElement(familyFilter);
  familyFilter.appendChild(createFamilyFilterButton('Todas las familias', ''));
  [...new Set(cards.map((card) => card.family).filter(Boolean))].forEach((family) => { familyFilter.appendChild(createFamilyFilterButton(family, family)); });
}
function loadCards() { appState.cards = localSeedCards(); populateFamilyFilter(appState.cards); renderCatalog(); return Promise.resolve(); }
function loadActiveMatch() { loadStoredMatch(); updateDerivedCombat(); renderGame(); return Promise.resolve(); }
function requestedHandSize() { return Number(document.querySelector('input[name="initial-hand-size"]:checked')?.value || 5); }
async function createAIMatch(selectedCardIds = []) { startLocalMatch(selectedCardIds, requestedHandSize()); renderGame(); setStatus(selectedCardIds.length ? 'Duelo local creado con la selección manual como mano disponible.' : 'Duelo local creado con mano aleatoria.'); }
async function shuffleMonsters() { await createAIMatch(); setActionFeedback(`Cartas barajadas. Mano Disponible tiene ${appState.match.initial_hand_size} carta(s) aleatoria(s).`, 'success'); }
async function createSelectedMatch() { const ids = [...appState.selectedCatalogCardIds]; if (!ids.length) return setActionFeedback('Seleccioná al menos una carta del catálogo.', 'error'); await createAIMatch(ids); setActionFeedback(`Selección aplicada. Mano Disponible tiene ${appState.match.host.hand.length} carta(s) seleccionada(s).`, 'success'); }
async function endTurn() { if (!appState.roomCode) throw new Error('No hay duelo activo.'); try { await sendAction({ action: 'end_turn' }); resetSelections(); setActionFeedback('Turno terminado. La IA local resolvió su respuesta.', 'success'); renderGame(); } catch (err) { setActionFeedback(err.message, 'error'); } }
function toggleCatalogSelection(card) {
  const id = String(card.id);
  if (appState.selectedCatalogCardIds.has(id)) {
    appState.selectedCatalogCardIds.delete(id);
    if (appState.match?.host) { appState.match.host.hand = appState.match.host.hand.filter((item) => String(item.id) !== id); refreshCounts(); persistMatch(); }
    setActionFeedback(`${card.name} quitada de la mano manual.`, 'normal');
  } else {
    if (appState.selectedCatalogCardIds.size >= requestedHandSize()) return setActionFeedback(`La mano manual admite ${requestedHandSize()} carta(s). Quitá una para cambiarla.`, 'error');
    appState.selectedCatalogCardIds.add(id);
    if (appState.match?.host) { appState.match.host.hand.push(normalizeCard(card, appState.match.host.hand.length)); refreshCounts(); persistMatch(); }
    setActionFeedback(`${card.name} agregada a la mano manual.`, 'success');
  }
  renderCatalog(); renderGame();
}
function bindAsyncButton(selector, handler) {
  const button = $(selector); if (!button) return;
  const idleLabel = button.textContent; const loadingLabel = button.dataset.loadingLabel || 'Procesando...';
  button.addEventListener('click', async () => { if (button.disabled) return; button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = loadingLabel; try { await handler(); } catch (err) { setStatus(err.message || 'Error inesperado', true); } finally { button.disabled = false; button.setAttribute('aria-busy', 'false'); button.textContent = idleLabel; } });
}
function openInitialHandDialog() { const dialog = $('#hand-choice-dialog'); if (dialog?.showModal) dialog.showModal(); }
function boot() {
  renderGame(); bindAsyncButton('#create-ai-match', () => createAIMatch()); bindAsyncButton('#shuffle-monsters', shuffleMonsters); bindAsyncButton('#create-selected-match', createSelectedMatch); bindAsyncButton('#end-turn-btn', endTurn); $('#modal-random-hand')?.addEventListener('click', () => createAIMatch()); $('#modal-manual-hand')?.addEventListener('click', () => { setActionFeedback('Elegí tus cartas desde Bestiario de cartas y presioná Usar selección.', 'normal'); });
  loadCards().then(loadActiveMatch).catch((err) => { setStatus(err.message || 'No se pudo iniciar el juego.', true); setActionFeedback('No se pudo cargar el duelo. Iniciá un nuevo enfrentamiento o usá la selección manual.', 'error'); renderGame(); }).finally(() => { if (!appState.match) { setStatus('Sin duelo local activo. Iniciá uno nuevo o prepará una selección manual.'); openInitialHandDialog(); } });
}
document.addEventListener('DOMContentLoaded', boot, { once: true });
