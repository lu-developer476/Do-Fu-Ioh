const CARD_IMAGE_PLACEHOLDER = '/static/core/img/placeholders/card-placeholder.svg';
const STORAGE_KEY = 'do_fu_ioh_backendless_match_v3';
const EMPTY_MESSAGES = { catalog: 'No hay cartas disponibles para mostrar.', matchLog: 'Aún no hay actividad registrada.', hand: 'No quedan cartas en la mano.', handPreview: 'La mano se mostrará al iniciar el duelo.', summary: 'Iniciá un duelo para ver el estado.', arena: 'Espacio libre' };
const STAGE_RANK = { base: 0, fusion: 1, evolution: 2 };
const MAX_ENERGY = 10;
const FREE_SUMMON_COST = 0;
const BOARD_WIDTH = 13;
const BOARD_HEIGHT = 9;
const DEPLOY_ROWS = { host: [BOARD_HEIGHT - 1], guest: [0] };
const SIDE_DEPLOY_DEPTH = 3;
const MATCH_SETUP_STEPS = ['cards', 'bestiary', 'mode'];
const INITIAL_HAND_OPTIONS = new Set([1, 2, 5]);
const appState = { cards: [], roomCode: null, match: null, selectedHandIndex: null, selectedUnitId: null, selectedCatalogCardIds: new Set(), selectedFamily: '', actionFeedback: { message: 'Seleccioná una carta o una unidad para continuar.', tone: 'normal' }, clientLog: [], combatEffects: [], aiPlayback: false, hasPromptedInitialHand: false, lastMatchConfig: null, matchSetupStep: 0, audio: { ctx: null, enabled: true, unlocked: false } };
const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

const FUSION_RECIPES = {
  'Pío combinado': ['Pío albino', 'Pío negruzco'],
  'Pío otoñal': ['Pío anaranjado', 'Pío castaño'],
  'Kitsu kumiawase': ['Kitsu amatista', 'Kitsu magenta'],
  'Kitsu nishiki': ['Kitsu mizu', 'Kitsu midori no mizu'],
  'Kitsu penta': ['Kitsu amatista', 'Kitsu anaranjado', 'Kitsu carmine', 'Kitsu magenta', 'Kitsu silvestre'],
  'Kitsu yin yang': ['Kitsu dākuburakku', 'Kitsu junsuina hikari'],
  'Escarahoja duocromada': ['Escarahoja anaranjada', 'Escarahoja tostada'],
  'Escarahoja mecanizada': ['Escarahoja tostada', 'Escarahoja limonada'],
  'Escarahoja tricolor': ['Escarahoja sonrosada', 'Escarahoja violeta'],
  'Escarahoja variopinta': ['Escarahoja anaranjada', 'Escarahoja limonada', 'Escarahoja sonrosada', 'Escarahoja tostada', 'Escarahoja violeta']
};
const EVOLUTION_RECIPES = {
  'Pío otoñal': 'Píoloro',
  'Kitsu silvestre': 'Kitsu silvestre evolucionado',
  'Kitsu nishiki': 'Kitsu nishiki evolucionado',
  'Kitsu penta': 'Kitsu penta evolucionado',
  'Kitsu yin yang': 'Kitsu yin yang evolucionado',
  'Escarahoja duocromada': 'Escarasubjefe Bronce',
  'Escarahoja mecanizada': 'Escarasubjefe Bronce',
  'Escarahoja tricolor': 'Escarasubjefe Bronce',
  'Escarahoja variopinta': 'Escarasubjefe Bronce'
};

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
function summarizeCardStats(card = {}) { return `PdV ${hpLabel(card)} · PdE ${card.shell ?? 0} · PA ${card.action_points ?? '-'} · PM ${card.movement_points ?? '-'}`; }
function stageLabel(stage) { return { base: 'Base', fusion: 'Fusión', evolution: 'Evolución' }[stage] || stage || '-'; }
function formatSideLabel(side) { return side === 'host' ? 'Jugador' : side === 'guest' ? 'IA' : side || '-'; }

function spellDamageRange(spell = {}, card = {}) {
  const min = Number.isFinite(Number(spell.damage_min)) ? Number(spell.damage_min) : Math.max(0, (Number(spell.cost) || 1) + (STAGE_RANK[card.stage] || 0));
  const max = Number.isFinite(Number(spell.damage_max)) ? Number(spell.damage_max) : Math.max(min, min + 2 + (STAGE_RANK[card.stage] || 0));
  return { min, max };
}
function spellDamageLabel(spell = {}, card = {}) { const { min, max } = spellDamageRange(spell, card); return min === max ? `${max}` : `${min}-${max}`; }
function spellMetaLabel(spell = {}, card = {}) {
  const parts = [`${spell.cost ?? '-'} PA`, `rango ${spell.range ?? '-'}`];
  if (!isFusionSpell(spell) && !isEvolutionSpell(spell)) parts.push(`daño ${spellDamageLabel(spell, card)}`);
  return parts.join(' · ');
}
function defaultSpell(card = {}) { const fallbackDamage = Math.max(1, (Number(card.action_points) || 1) + 2 + (STAGE_RANK[card.stage] || 0)); return (Array.isArray(card.spells) && card.spells[0]) || { name: 'Ataque básico', cost: 1, range: 1, damage_min: fallbackDamage, damage_max: fallbackDamage + 2, description: 'Ataque básico del monstruo.' }; }
function estimateDamage(card = {}, spell = null) { const selected = spell || defaultSpell(card); const { min, max } = spellDamageRange(selected, card); return Math.max(0, Math.floor((min + max) / 2)); }
function shellRegenPercent(card = {}) {
  const family = String(card.family || '').toLowerCase();
  const base = family.includes('gelatina') ? 0.22 : family.includes('escarahoja') ? 0.20 : family.includes('kitsu') ? 0.16 : family.includes('pío') || family.includes('pio') ? 0.14 : 0.15;
  return Math.min(0.28, base + ((STAGE_RANK[card.stage] || 0) * 0.03));
}

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
function appendLog(message) {
  if (!appState.match || !message) return;
  appState.match.log.push(`${new Date().toLocaleTimeString('es-AR')} · ${message}`);
  appState.match.log = appState.match.log.slice(-36);
  renderMatchLog(appState.match.log || []);
  syncBoardActionButtons();
}
function getAudioContext() {
  if (!appState.audio.enabled) return null;
  const AudioContextClass = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!AudioContextClass) return null;
  appState.audio.ctx ||= new AudioContextClass();
  return appState.audio.ctx;
}
function unlockCombatAudio() {
  const ctx = getAudioContext();
  if (!ctx) return;
  if (ctx.state === 'suspended') ctx.resume();
  appState.audio.unlocked = true;
}
function playTone({ frequency = 220, duration = 0.12, type = 'sine', gain = 0.035, slideTo = null, delayStart = 0 } = {}) {
  const ctx = getAudioContext();
  if (!ctx || !appState.audio.unlocked) return;
  const start = ctx.currentTime + delayStart;
  const osc = ctx.createOscillator();
  const amp = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(frequency, start);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(Math.max(1, slideTo), start + duration);
  amp.gain.setValueAtTime(0.0001, start);
  amp.gain.exponentialRampToValueAtTime(gain, start + 0.015);
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(amp).connect(ctx.destination);
  osc.start(start);
  osc.stop(start + duration + 0.03);
}
function playCombatSound(kind = 'combat') {
  const presets = {
    summon: [{ frequency: 330, slideTo: 660, duration: .16, type: 'triangle' }, { frequency: 990, duration: .09, type: 'sine', delayStart: .06, gain: .025 }],
    move: [{ frequency: 180, slideTo: 260, duration: .08, type: 'sine', gain: .02 }, { frequency: 140, slideTo: 210, duration: .08, type: 'sine', delayStart: .08, gain: .018 }],
    monster: [{ frequency: 95, slideTo: 62, duration: .22, type: 'sawtooth', gain: .026 }, { frequency: 132, slideTo: 88, duration: .18, type: 'square', delayStart: .04, gain: .018 }],
    hit: [{ frequency: 160, slideTo: 55, duration: .13, type: 'square', gain: .04 }, { frequency: 520, slideTo: 210, duration: .08, type: 'sawtooth', gain: .022 }],
    damage: [{ frequency: 240, slideTo: 120, duration: .12, type: 'triangle', gain: .032 }],
    death: [{ frequency: 180, slideTo: 42, duration: .36, type: 'sawtooth', gain: .038 }, { frequency: 90, slideTo: 30, duration: .42, type: 'triangle', delayStart: .08, gain: .026 }],
    combat: [{ frequency: 220, slideTo: 330, duration: .1, type: 'triangle', gain: .02 }]
  };
  (presets[kind] || presets.combat).forEach(playTone);
}
['pointerdown', 'keydown', 'touchstart'].forEach((eventName) => document.addEventListener(eventName, unlockCombatAudio, { once: true, passive: true }));
function randomId(prefix) { return globalThis.crypto?.randomUUID?.() || `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`; }
function delay(ms = 620) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function pushCombatEffect(effect = {}) {
  const id = randomId('fx');
  appState.combatEffects = [...(appState.combatEffects || []), { id, createdAt: Date.now(), ...effect }].slice(-12);
  setTimeout(() => { appState.combatEffects = (appState.combatEffects || []).filter((item) => item.id !== id); renderGame(); }, 1150);
}
function effectsAt(x, y) { return (appState.combatEffects || []).filter((effect) => effect.x === x && effect.y === y); }
function movementRange(card = {}) { return Math.max(0, Number(card.movement_points) || 0); }
function isBossCard(card = {}) { return /\bReal\b|Escarasubjefe/i.test(card.name || ''); }
function isSpecialDeckCard(card = {}) { return card.stage === 'fusion' || card.stage === 'evolution' || isBossCard(card); }
function currentCardPool() { const scope = document.querySelector('input[name="deck-scope"]:checked')?.value || 'all'; const tier = document.querySelector('input[name="deck-tier"]:checked')?.value || 'all'; const family = $('#match-family-select')?.value || ''; return appState.cards.filter((card) => { const familyAllowed = scope !== 'family' || !family || card.family === family; const tierAllowed = tier === 'special' ? isSpecialDeckCard(card) : tier === 'base' ? card.stage === 'base' && !isBossCard(card) : true; return familyAllowed && tierAllowed; }); }
function findCardByName(name) { return appState.cards.find((card) => card.name === name); }
function isFusionSpell(spell = {}) { return /fusi[oó]n/i.test(spell.name || ''); }
function isEvolutionSpell(spell = {}) { return /evoluci[oó]n/i.test(spell.name || ''); }
function cloneCard(card) { return JSON.parse(JSON.stringify(card)); }
function spellRange(card = {}) { const ranges = Array.isArray(card.spells) ? card.spells.map((spell) => Number(spell.range)).filter((range) => Number.isFinite(range) && range > 0) : []; return Math.max(1, ...(ranges.length ? ranges : [Math.min(7, 2 + (STAGE_RANK[card.stage] || 0) + Math.floor((card.action_points || 0) / 2))])); }
function effectiveSpellRange(spell = {}, unit = {}) { const raw = Number(spell.range); if (Number.isFinite(raw)) return Math.max(0, raw); return Math.max(1, Number(unit.attack_range) || spellRange(unit.card || {}) || 1); }
function isSelfTargetSpell(spell = {}) { return effectiveSpellRange(spell) === 0; }
function unitAt(x, y) { return [...(appState.match?.host.units || []), ...(appState.match?.guest.units || [])].find((unit) => unit.x === x && unit.y === y); }
function nextSummonLabel(side) { const player = appState.match?.[side]; if (!player) return `${side === 'host' ? 'J' : 'IA'}?`; player.summon_sequence = (player.summon_sequence || 0) + 1; return `${side === 'host' ? 'J' : 'IA'}${player.summon_sequence}`; }
function unitBattleLabel(unit) { return unit.battle_label || `${unit.owner === 'host' ? 'J' : 'IA'}?`; }
function distance(a, b) { return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); }
function buildUnit(side, card, position, options = {}) { return { id: randomId(side), owner: side, battle_label: nextSummonLabel(side), slot: position.x, x: position.x, y: position.y, card, hp_current: card.hp, shell_current: card.shell || 0, pa_current: card.action_points || 1, move_points: movementRange(card), can_act: true, summoned_turn: appState.match.turn.number, summoned_by_spell: Boolean(options.summoned_by_spell), non_evolvable: Boolean(options.non_evolvable), attack_range: spellRange(card), attackable_unit_ids: [] }; }
function isDeployCell(side, x, y) {
  if ((DEPLOY_ROWS[side] || []).includes(y)) return true;
  const isSideColumn = x === 0 || x === BOARD_WIDTH - 1;
  if (!isSideColumn) return false;
  if (side === 'host') return y >= BOARD_HEIGHT - SIDE_DEPLOY_DEPTH;
  if (side === 'guest') return y < SIDE_DEPLOY_DEPTH;
  return false;
}
function deployCells(side) { const occupied = new Set([...(appState.match?.host.units || []), ...(appState.match?.guest.units || [])].map((unit) => `${unit.x},${unit.y}`)); const cells = []; for (let y = 0; y < BOARD_HEIGHT; y += 1) for (let x = 0; x < BOARD_WIDTH; x += 1) if (isDeployCell(side, x, y) && !occupied.has(`${x},${y}`)) cells.push({ x, y }); return cells; }
function openSlots(player) { return deployCells(player.side).slice(0, BOARD_WIDTH).map((cell) => cell.x); }
function namesMatchRecipe(names = [], requirements = []) { const sortedNames = names.slice().sort(); const sortedReq = requirements.slice().sort(); return sortedNames.length === sortedReq.length && sortedReq.every((name, index) => name === sortedNames[index]); }
function fusionRecipeForPair(unit, target) { if (!unit || !target || unit.owner !== target.owner) return null; const names = [unit.card.name, target.card.name]; return Object.entries(FUSION_RECIPES).find(([, req]) => req.length === 2 && namesMatchRecipe(names, req)) || null; }
function fusionUnitsForRecipe(anchor, recipeName) { const requirements = FUSION_RECIPES[recipeName] || []; const allies = (appState.match?.[anchor.owner]?.units || []).filter((unit) => unit.id === anchor.id || distance(anchor, unit) <= 1); const selected = []; for (const requiredName of requirements) { const unit = allies.find((candidate) => candidate.card.name === requiredName && !selected.some((item) => item.id === candidate.id)); if (!unit) return []; selected.push(unit); } return selected.some((unit) => unit.id === anchor.id) ? selected : []; }
function fusionRecipeForBattle(unit, target = null) { if (!unit || (target && unit.owner !== target.owner)) return null; const pair = fusionRecipeForPair(unit, target); if (pair) return pair; return Object.entries(FUSION_RECIPES).find(([name, req]) => req.includes(unit.card.name) && (!target || req.includes(target.card.name)) && fusionUnitsForRecipe(unit, name).length === req.length) || null; }
function virtualFusionSpell(unit, target) { const recipe = fusionRecipeForBattle(unit, target); if (!recipe) return null; const fusionLabel = recipe[0].replace(/^Kitsu /i, ''); return { name: `Fusión ${fusionLabel.charAt(0).toUpperCase()}${fusionLabel.slice(1)}`, cost: 0, range: 1, damage_min: 0, damage_max: 0, description: `Fusiona ${recipe[1].join(' + ')} para crear ${recipe[0]}.` }; }
function canUnitEvolve(unit) { return Boolean(unit && !unit.summoned_by_spell && !unit.non_evolvable && !unit.card?.non_evolvable && EVOLUTION_RECIPES[unit.card?.name] && (unit.card.stage === 'fusion' || unit.card.name === 'Kitsu silvestre')); }
function virtualEvolutionSpell(unit) { return canUnitEvolve(unit) ? { name: 'Evolución', cost: 0, range: 0, damage_min: 350, damage_max: 350, area_range: 2, usable_from_turn: 5, description: 'Hace 350 daño en área de 2 casillas y asciende a la evolución correspondiente desde el 5° turno.' } : null; }
function spellCost(spell = {}) { return Math.max(0, Number(spell.cost) || 0); }
function usableSpells(unit, target = null) { const baseSpells = Array.isArray(unit?.card?.spells) && unit.card.spells.length ? unit.card.spells : [defaultSpell(unit?.card || {})]; const specials = [target ? virtualFusionSpell(unit, target) : virtualEvolutionSpell(unit)].filter(Boolean); const spells = [...specials, ...baseSpells]; return spells.filter((spell) => { if (spellCost(spell) > (unit?.pa_current || 0)) return false; if (!target) return true; const range = effectiveSpellRange(spell, unit); if (range === 0) return target.id === unit?.id; return distance(unit, target) <= range; }); }
function chooseBestSpell(unit, target = null) { return usableSpells(unit, target).sort((a, b) => estimateDamage(unit.card, b) - estimateDamage(unit.card, a) || (Number(a.cost) || 1) - (Number(b.cost) || 1))[0] || defaultSpell(unit?.card || {}); }
function updateDerivedCombat() { if (!appState.match) return; ['host', 'guest'].forEach((side) => { const enemy = side === 'host' ? appState.match.guest : appState.match.host; appState.match[side].units.forEach((unit) => { unit.move_points = Number.isFinite(Number(unit.move_points)) ? Math.max(0, Number(unit.move_points)) : movementRange(unit.card); unit.attack_range = spellRange(unit.card); unit.attackable_unit_ids = unit.can_act && unit.pa_current > 0 ? enemy.units.filter((target) => distance(unit, target) <= unit.attack_range).map((target) => target.id).sort() : []; }); }); }
function checkWinner(actingSide) { const alive = (p) => Boolean(p.units.length || p.hand.length || p.library.length); const host = alive(appState.match.host); const guest = alive(appState.match.guest); if (!host || !guest) appState.match.winner = host ? 'host' : guest ? 'guest' : actingSide; }
function resetTurn(player) { player.summons_this_turn = 0; player.max_energy = Math.min(MAX_ENERGY, player.max_energy + 1); player.energy = player.max_energy; player.units.forEach((unit) => { unit.pa_current = unit.card.action_points || 1; unit.move_points = movementRange(unit.card); unit.can_act = true; }); }
function pickInitialCards(selectedIds = [], count = 5, poolCards = currentCardPool()) { const selected = selectedIds.map(String); const source = poolCards; const selectedCards = selected.map((id) => source.find((card) => String(card.id) === id)).filter(Boolean); const pool = source.filter((card) => !selected.includes(String(card.id))); return [...selectedCards, ...shuffle(pool)].slice(0, count); }
function startLocalMatch(selectedIds = [], requestedCount = 5) { const handSize = INITIAL_HAND_OPTIONS.has(Number(requestedCount)) ? Number(requestedCount) : 5; const pool = currentCardPool(); if (!pool.length) throw new Error('No hay cartas que cumplan las restricciones elegidas. Cambiá el bestiario o la variedad.'); const hostCards = pickInitialCards(selectedIds, handSize, pool); const guestCards = shuffle(pool).slice(0, handSize); appState.lastMatchConfig = { selectedIds, handSize }; const roomCode = `local-${Date.now()}`; appState.roomCode = roomCode; appState.match = { room_code: roomCode, mode: 'local_vs_ai', ai_difficulty: 'normal', arena: { slots: BOARD_WIDTH }, board: { width: BOARD_WIDTH, height: BOARD_HEIGHT }, initial_hand_size: handSize, turn: { number: 1, active_side: 'host' }, host: createPlayer('host', hostCards), guest: createPlayer('guest', guestCards), winner: null, paused: false, log: [`Duelo local iniciado con ${handSize} carta(s) iniciales contra la IA.`, `Bestiario activo: ${(pool.length && pool.length !== appState.cards.length) ? pool[0].family : 'todo el bestiario'}.`, `Duelo preparado en la arena local.`] }; resetSelections(); updateDerivedCombat(); persistMatch(); }
function applySummon(side, handIndex, position) { const player = appState.match[side]; if (!deployCells(side).some((cell) => cell.x === position.x && cell.y === position.y)) throw new Error('Esa celda no está disponible para invocar.'); const card = player.hand[handIndex]; if (!card) throw new Error('Carta inválida.'); player.hand.splice(handIndex, 1); player.summons_this_turn += 1; player.units.push(buildUnit(side, card, position)); playCombatSound('summon'); playCombatSound('monster'); appendLog(`${formatSideLabel(side)} invocó ${card.name} en (${position.x + 1}, ${position.y + 1}).`); }
function applyMove(side, unitId, position) { const unit = appState.match[side].units.find((item) => item.id === unitId); if (!unit || !unit.can_act || unit.move_points <= 0) throw new Error('Movimiento inválido: los desplazamientos consumen PM.'); if (position.x < 0 || position.y < 0 || position.x >= BOARD_WIDTH || position.y >= BOARD_HEIGHT || unitAt(position.x, position.y)) throw new Error('La celda está ocupada o fuera del tablero.'); const spentPm = distance(unit, position); if (spentPm > unit.move_points) throw new Error('La celda está fuera del rango de movimiento.'); const from = { x: unit.x, y: unit.y }; unit.x = position.x; unit.y = position.y; unit.slot = position.x; unit.move_points -= spentPm; unit.can_act = unit.pa_current > 0 || unit.move_points > 0; pushCombatEffect({ x: from.x, y: from.y, text: 'Salida', tone: 'move ghost' }); pushCombatEffect({ x: position.x, y: position.y, text: `-${spentPm} PM`, tone: 'move' }); playCombatSound('move'); appendLog(`${formatSideLabel(side)} movió ${unit.card.name} de (${from.x + 1}, ${from.y + 1}) a (${position.x + 1}, ${position.y + 1}) y gastó ${spentPm} PM.`); }
function applyAttack(side, attackerId, targetId, spellName = null) { const actor = appState.match[side]; const enemySide = side === 'host' ? 'guest' : 'host'; const enemy = appState.match[enemySide]; const attacker = actor.units.find((unit) => unit.id === attackerId); const target = enemy.units.find((unit) => unit.id === targetId) || actor.units.find((unit) => unit.id === targetId); const namedSpell = (attacker?.card?.spells || []).find((item) => item.name === spellName); const specialSpell = isEvolutionSpell({ name: spellName }) ? virtualEvolutionSpell(attacker) : virtualFusionSpell(attacker, target); if (spellName && isEvolutionSpell({ name: spellName }) && !specialSpell && !namedSpell) throw new Error('Los monstruos invocados no pueden evolucionar.'); const spell = namedSpell || specialSpell || virtualEvolutionSpell(attacker) || defaultSpell(attacker?.card || {}); const cost = spellCost(spell); const range = isEvolutionSpell(spell) ? 0 : effectiveSpellRange(spell, attacker); if (!attacker || !target || attacker.pa_current < cost || !attacker.can_act || (range === 0 ? target.id !== attacker.id : distance(attacker, target) > range)) throw new Error('Hechizo inválido, sin PA suficientes o fuera de rango.'); if (isFusionSpell(spell)) return applyFusionSpell(side, attacker, target, cost, spell); if (isEvolutionSpell(spell)) return applyEvolutionSpell(side, attacker, cost); attacker.pa_current -= cost; attacker.can_act = attacker.pa_current > 0 || attacker.move_points > 0; const previousHp = target.hp_current; const previousShell = target.shell_current; const power = estimateDamage(attacker.card, spell); const shieldDamage = Math.min(target.shell_current, power); target.shell_current = Math.max(0, target.shell_current - shieldDamage); const hpDamage = Math.max(0, power - shieldDamage); target.hp_current -= hpDamage; const hpLost = Math.max(0, previousHp - Math.max(0, target.hp_current)); pushCombatEffect({ x: attacker.x, y: attacker.y, text: `-${cost} PA`, tone: 'cast' }); playCombatSound('monster'); playCombatSound('hit'); if (shieldDamage > 0) pushCombatEffect({ x: target.x, y: target.y, text: `-${previousShell - target.shell_current} PdE`, tone: 'shield' }); if (hpDamage > 0) { playCombatSound('damage'); pushCombatEffect({ x: target.x, y: target.y, text: `-${hpDamage} daño`, tone: 'damage' }); pushCombatEffect({ x: target.x, y: target.y, text: `-${hpLost} PdV`, tone: 'hp' }); } appendLog(`${formatSideLabel(side)} usó ${spell.name} con ${attacker.card.name} contra ${target.card.name}: ${shieldDamage} PdE absorbidos y ${hpLost} PdV perdidos.`); if (target.hp_current <= 0) { playCombatSound('death'); const targetPlayer = appState.match[target.owner]; targetPlayer.units = targetPlayer.units.filter((unit) => unit.id !== target.id); appendLog(`${target.card.name} fue derrotado por ${attacker.card.name}.`); } }

function replaceUnitWithCard(side, unitsToRemove, newCard, anchorUnit, logMessage) {
  const player = appState.match[side];
  const removeIds = new Set(unitsToRemove.map((unit) => unit.id));
  player.units = player.units.filter((unit) => !removeIds.has(unit.id));
  const evolved = buildUnit(side, cloneCard(newCard), { x: anchorUnit.x, y: anchorUnit.y });
  evolved.summoned_turn = appState.match.turn.number;
  player.units.push(evolved);
  appendLog(logMessage);
}
function applyFusionSpell(side, attacker, target, cost, spell = {}) {
  if (target.owner !== side) throw new Error('La fusión sólo puede elegir monstruos aliados adyacentes.');
  if (distance(attacker, target) !== 1) throw new Error('Los monstruos requisito deben estar en casillas aledañas.');
  const fusionName = (spell.name || '').startsWith('Fusión: ') ? spell.name.replace('Fusión: ', '') : fusionRecipeForBattle(attacker, target)?.[0];
  const fusionCard = fusionName && findCardByName(fusionName);
  const fusionUnits = fusionName ? fusionUnitsForRecipe(attacker, fusionName) : [];
  if (!fusionCard || !fusionUnits.length) throw new Error('Estos monstruos no cumplen una receta de fusión disponible.');
  attacker.pa_current -= cost;
  playCombatSound('summon'); replaceUnitWithCard(side, fusionUnits, fusionCard, attacker, `${formatSideLabel(side)} fusionó ${fusionUnits.map((unit) => unit.card.name).sort().join(' + ')} y creó ${fusionName}.`);
}
function applyEvolutionSpell(side, attacker, cost) {
  const evolutionName = EVOLUTION_RECIPES[attacker.card.name];
  const evolutionCard = evolutionName && findCardByName(evolutionName);
  if (!evolutionCard) throw new Error('Este monstruo no tiene evolución configurada.');
  if (!canUnitEvolve(attacker)) throw new Error('Los monstruos invocados no pueden evolucionar; sólo una fusión o Kitsu silvestre propios pueden hacerlo.');
  if ((appState.match.turn?.number || 1) < 5) throw new Error('Evolución sólo puede usarse a partir del 5° turno de combate.');
  attacker.pa_current -= cost;
  const enemySide = side === 'host' ? 'guest' : 'host';
  const enemies = appState.match[enemySide].units || [];
  let damaged = 0;
  enemies.filter((unit) => distance(attacker, unit) <= 2).forEach((unit) => {
    const previousHp = unit.hp_current;
    const shieldDamage = Math.min(unit.shell_current, 350);
    unit.shell_current = Math.max(0, unit.shell_current - shieldDamage);
    const hpDamage = Math.max(0, 350 - shieldDamage);
    unit.hp_current -= hpDamage;
    damaged += 1;
    if (shieldDamage > 0) pushCombatEffect({ x: unit.x, y: unit.y, text: `-${shieldDamage} PdE`, tone: 'shield' });
    if (hpDamage > 0) pushCombatEffect({ x: unit.x, y: unit.y, text: `-${Math.max(0, previousHp - Math.max(0, unit.hp_current))} PdV`, tone: 'hp' });
  });
  appState.match[enemySide].units = enemies.filter((unit) => unit.hp_current > 0);
  playCombatSound('summon');
  playCombatSound('damage');
  replaceUnitWithCard(side, [attacker], evolutionCard, attacker, `${formatSideLabel(side)} evolucionó ${attacker.card.name} a ${evolutionName} e infligió 350 de daño en área de 2 casillas a ${damaged} objetivo(s).`);
}

function regenerateShields(player) { const turn = appState.match.turn?.number || 1; if (turn % 2 !== 0) return; player.units.forEach((unit) => { const maxShell = Number(unit.card.shell) || 0; if (!maxShell || unit.shell_current >= maxShell) return; const restored = Math.min(maxShell - unit.shell_current, Math.max(1, Math.ceil(maxShell * shellRegenPercent(unit.card)))); unit.shell_current += restored; appendLog(`${unit.card.name} regeneró ${restored} PdE (${Math.round(shellRegenPercent(unit.card) * 100)}%).`); }); }
function endSideTurn(side) { const nextSide = side === 'host' ? 'guest' : 'host'; appState.match.turn.active_side = nextSide; if (nextSide === 'host') appState.match.turn.number += 1; resetTurn(appState.match[nextSide]); regenerateShields(appState.match[nextSide]); appendLog(`Fin del turno de ${formatSideLabel(side)}.`); }
function stepToward(unit, target) { const steps = []; for (let dx = -1; dx <= 1; dx += 1) for (let dy = -1; dy <= 1; dy += 1) if (Math.abs(dx) + Math.abs(dy) === 1) steps.push({ x: unit.x + dx, y: unit.y + dy }); const candidates = steps.filter((cell) => cell.x >= 0 && cell.y >= 0 && cell.x < BOARD_WIDTH && cell.y < BOARD_HEIGHT && !unitAt(cell.x, cell.y) && distance(cell, target) < distance(unit, target)); return candidates.sort((a, b) => distance(a, target) - distance(b, target))[0]; }
function adjacentAllyFusion(unit, units = []) { return units.find((ally) => ally.id !== unit.id && fusionRecipeForBattle(unit, ally) && distance(unit, ally) === 1); }
function canEvolveNow(unit) { return canUnitEvolve(unit); }
async function runAiTurn() {
  if (appState.match?.paused) return;
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
    let safety = 0;
    while (!appState.match.winner && unit.can_act && safety < 8) {
      safety += 1;
      try {
        if (!ai.units.some((current) => current.id === unit.id)) break;
        if (canEvolveNow(unit)) { applyAttack('guest', unit.id, unit.id, 'Evolución'); refreshCounts(); updateDerivedCombat(); renderGame(); await delay(); break; }
        const fusionAlly = adjacentAllyFusion(unit, ai.units);
        if (fusionAlly) { const spell = virtualFusionSpell(unit, fusionAlly); applyAttack('guest', unit.id, fusionAlly.id, spell.name); refreshCounts(); updateDerivedCombat(); renderGame(); await delay(); break; }
        if (!appState.match.host.units.length) break;
        const target = [...appState.match.host.units].sort((a, b) => distance(unit, a) - distance(unit, b) || a.hp_current - b.hp_current)[0];
        const spell = usableSpells(unit, target).filter((item) => !isFusionSpell(item) && !isEvolutionSpell(item)).sort((a, b) => estimateDamage(unit.card, b) - estimateDamage(unit.card, a))[0];
        if (spell && distance(unit, target) <= Math.max(1, Number(spell.range) || unit.attack_range)) { applyAttack('guest', unit.id, target.id, spell.name); checkWinner('guest'); }
        else { const nextCell = stepToward(unit, target); if (!nextCell || unit.move_points <= 0) { unit.can_act = false; break; } applyMove('guest', unit.id, nextCell); }
      } catch (err) {
        unit.can_act = false;
        appendLog(`La IA descartó una acción inválida de ${unit.card?.name || 'una unidad'}: ${err.message}`);
        break;
      }
      refreshCounts(); updateDerivedCombat(); renderGame(); await delay();
    }
    if (safety >= 8) { unit.can_act = false; appendLog(`La IA agotó el plan de ${unit.card.name} y cedió la acción para evitar trabas.`); }
  }
  if (!appState.match.winner) endSideTurn('guest');
  appState.aiPlayback = false;
}
async function applyLocalAction(payload) { if (!appState.match || appState.match.winner) throw new Error('La partida ya terminó o no existe.'); if (appState.match.paused) throw new Error('La partida está pausada. Reanudala desde Nuevo duelo.'); if (appState.match.turn.active_side !== 'host') throw new Error('La IA está jugando ahora; revisá el Registro para ver cada invocación, movimiento y ataque.'); if (payload.action === 'summon') applySummon('host', payload.hand_index, payload.position); else if (payload.action === 'move') applyMove('host', payload.unit_id, payload.position); else if (payload.action === 'attack') applyAttack('host', payload.attacker_id, payload.target_id, payload.spell_name); else if (payload.action === 'end_turn') endSideTurn('host'); checkWinner('host'); refreshCounts(); updateDerivedCombat(); renderGame(); if (appState.match.turn.active_side === 'guest' && !appState.match.winner) await runAiTurn(); refreshCounts(); updateDerivedCombat(); persistMatch(); }
async function sendAction(actionPayload) { await applyLocalAction(actionPayload); renderGame(); }
async function onSlotClick() { const firstDeployCell = deployCells('host')[0]; if (firstDeployCell) return onBoardCellClick(firstDeployCell.x, firstDeployCell.y); return setActionFeedback('No hay celdas libres para invocar.', 'error'); }
async function chooseSpellForAttack(attacker, target) {
  const spells = usableSpells(attacker, target);
  if (!spells.length) { setActionFeedback('No hay hechizos disponibles: faltan PA o el objetivo está fuera de rango.', 'error'); return null; }
  const dialog = $('#spell-choice-dialog'); const list = $('#spell-choice-list'); const title = $('#spell-choice-title'); const targetText = $('#spell-choice-target');
  if (!dialog?.showModal || !list) return chooseBestSpell(attacker, target);
  title.textContent = 'Elegí un hechizo'; targetText.textContent = ''; clearElement(list);
  return new Promise((resolve) => {
    let done = false; const finish = (spell) => { if (done) return; done = true; dialog.close(); resolve(spell); };
    spells.forEach((spell) => { const button = document.createElement('button'); button.type = 'button'; button.className = 'spell-choice-option'; appendTextElement(button, 'strong', spell.name); appendTextElement(button, 'span', spellMetaLabel(spell, attacker.card)); appendTextElement(button, 'small', spell.description || spell.effect || 'Sin descripción.'); button.addEventListener('click', () => finish(spell)); list.appendChild(button); });
    $('#spell-choice-cancel')?.addEventListener('click', () => finish(null), { once: true }); dialog.addEventListener('cancel', () => finish(null), { once: true }); dialog.showModal();
  });
}
async function onArenaCardClick(unit, side) { const { me, enemy, mySide } = resolveSides(); if (!me || !enemy) return; if (side === 'host') { const active = me.units?.find((item) => item.id === appState.selectedUnitId); if (active && active.id === unit.id) { appState.selectedUnitId = unit.id; appState.selectedHandIndex = null; renderGame(); return openUnitControlDialog(unit); } if (active && active.id !== unit.id && fusionRecipeForBattle(active, unit)) { if (!isMyTurn(mySide)) return setActionFeedback('La IA está jugando ahora; el Registro detalla sus jugadas.', 'error'); const spell = await chooseSpellForAttack(active, unit); if (!spell) return setActionFeedback('Fusión cancelada.', 'normal'); try { await sendAction({ action: 'attack', attacker_id: active.id, target_id: unit.id, spell_name: spell.name }); return setActionFeedback(`${active.card.name} se fusionó con ${unit.card.name}.`, 'success'); } catch (err) { return setActionFeedback(err.message, 'error'); } } appState.selectedUnitId = unit.id; appState.selectedHandIndex = null; renderGame(); return openUnitControlDialog(unit); } const attacker = me.units?.find((item) => item.id === appState.selectedUnitId); if (!attacker) return setActionFeedback('Seleccioná primero una unidad propia para atacar.', 'error'); if (!isMyTurn(mySide)) return setActionFeedback('La IA está jugando ahora; el Registro detalla sus jugadas.', 'error'); const spell = await chooseSpellForAttack(attacker, unit); if (!spell) return setActionFeedback('Ataque cancelado.', 'normal'); try { await sendAction({ action: 'attack', attacker_id: attacker.id, target_id: unit.id, spell_name: spell.name }); setActionFeedback(`${attacker.card.name} usó ${spell.name} contra ${unit.card.name}.`, 'success'); } catch (err) { setActionFeedback(err.message, 'error'); } }

async function onBoardCellClick(x, y) {
  const { me, enemy, mySide } = resolveSides();
  if (!appState.match || !isMyTurn(mySide)) return setActionFeedback('La IA está jugando ahora; el Registro detalla sus jugadas.', 'error');
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

function appendUnitStat(parent, label, value) {
  parent.appendChild(createSummaryField(label, value));
}
function openUnitControlDialog(unit) {
  const dialog = $('#unit-control-dialog'); const title = $('#unit-control-title'); const body = $('#unit-control-body'); const spellList = $('#unit-control-spells');
  if (!dialog?.showModal || !body || !unit) return;
  if (title) title.textContent = `${unitBattleLabel(unit)} · ${unit.card.name}`;
  clearElement(body); clearElement(spellList);
  body.appendChild(createCardImageElement(cardImage(unit.card), unit.card.name, 'card-image-unit-modal'));
  const stats = document.createElement('div'); stats.className = 'unit-control-stats';
  appendUnitStat(stats, 'PdV', `${unit.hp_current}/${unit.card.hp}`);
  appendUnitStat(stats, 'PdE', `${unit.shell_current}/${unit.card.shell || 0}`);
  appendUnitStat(stats, 'PA', `${unit.pa_current}/${unit.card.action_points || 0}`);
  appendUnitStat(stats, 'PM', unit.move_points || 0);
  appendUnitStat(stats, 'Rango', unit.attack_range ?? '-');
  body.appendChild(stats);
  appendTextElement(body, 'p', unit.card.description || 'Sin descripción disponible.', 'unit-control-description');
  const selfSpells = usableSpells(unit, unit).filter((spell) => effectiveSpellRange(spell, unit) === 0);
  selfSpells.forEach((spell) => { const button = document.createElement('button'); button.type = 'button'; button.className = 'spell-choice-option'; appendTextElement(button, 'strong', spell.name); appendTextElement(button, 'span', spellMetaLabel(spell, unit.card)); appendTextElement(button, 'small', spell.description || spell.effect || 'Se usa sobre el lanzador.'); button.addEventListener('click', async () => { dialog.close(); try { await sendAction({ action: 'attack', attacker_id: unit.id, target_id: unit.id, spell_name: spell.name }); setActionFeedback(`${unit.card.name} usó ${spell.name} sobre sí mismo.`, 'success'); } catch (err) { setActionFeedback(err.message, 'error'); } }); spellList.appendChild(button); });
  const moveButton = $('#unit-control-move');
  if (moveButton) moveButton.onclick = () => { dialog.close(); appState.selectedUnitId = unit.id; appState.selectedHandIndex = null; renderGame(); setActionFeedback(`${unit.card.name} seleccionado para mover. Elegí una casilla libre dentro de su PM.`, 'normal'); };
  dialog.showModal();
}

function renderBoard({ me, enemy, canPlay, selectedUnit, selectedHandCard }) {
  const board = $('#tactical-board'); if (!board) return;
  clearElement(board);
  board.style.gridTemplateColumns = `repeat(${BOARD_WIDTH}, minmax(0, var(--board-cell-size)))`;
  const deployHost = new Set(deployCells('host').map((c) => `${c.x},${c.y}`));
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
    cell.className = ['cell', (x + y) % 2 ? 'square-dark' : 'square-light', unit ? 'has-unit' : '', unit?.owner === 'host' ? 'ally' : '', unit?.owner === 'guest' ? 'enemy' : '', isDeployCell('host', x, y) ? 'deploy-ally' : '', isDeployCell('guest', x, y) ? 'deploy-enemy' : '', selectedUnit?.id === unit?.id ? 'selected' : '', selectedHandCard && deployHost.has(key) ? 'hint-summon' : '', moveHints.has(key) ? 'hint-move' : '', unit?.owner === 'guest' && attackHints.has(key) ? 'hint-attack' : '', canPlay ? 'is-actionable' : ''].filter(Boolean).join(' ');
    if (unit) cell.appendChild(renderToken(unit, unit.owner === 'host' ? 'ally' : 'enemy', selectedUnit)); else appendTextElement(cell, 'span', '', 'cell-empty-state');
    const cellEffects = effectsAt(x, y);
    if (cellEffects.length) { const fxStack = document.createElement('span'); fxStack.className = 'combat-fx-stack'; cellEffects.forEach((effect) => appendTextElement(fxStack, 'span', effect.text, `combat-fx combat-fx-${effect.tone}`)); cell.appendChild(fxStack); }
    cell.addEventListener('click', () => onBoardCellClick(x, y)); board.appendChild(cell);
  }

}
function formatSpells(card = {}) {
  const spells = Array.isArray(card.spells) ? card.spells : [];
  if (!spells.length) return 'Hechizos: sin hechizos configurados.';
  return `Hechizos: ${spells.map((spell) => `${spell.name} (${spellMetaLabel(spell, card)}): ${spell.description || spell.effect || 'Sin descripción.'}`).join(' · ')}`;
}
function appendCardDescription(parent, card = {}) { appendTextElement(parent, 'p', card.description || 'Sin descripción disponible.', 'card-description'); }
function appendCardDescriptionContent(parent, card = {}) {
  appendTextElement(parent, 'p', `Familia: ${card.family || '-'}`);
  appendTextElement(parent, 'p', `Forma: ${stageLabel(card.stage)}`);
  appendTextElement(parent, 'p', card.description || 'Sin descripción disponible.');
}
function appendCardSpellsContent(parent, card = {}) {
  const list = Array.isArray(card.spells) ? card.spells : [];
  if (!list.length) {
    appendTextElement(parent, 'p', 'Sin hechizos configurados.');
    return;
  }
  list.forEach((spell) => appendTextElement(parent, 'p', `${spell.name} (${spellMetaLabel(spell, card)}): ${spell.description || spell.effect || 'Sin descripción.'}`));
}
function openCardInfoDialog(card = {}, section = 'description') {
  const dialog = $('#card-info-dialog');
  const title = $('#card-info-title');
  const body = $('#card-info-body');
  if (!dialog?.showModal || !body) return;
  clearElement(body);
  const isSpells = section === 'spells';
  if (title) title.textContent = isSpells ? 'Hechizos' : 'Descripción';
  if (isSpells) appendCardSpellsContent(body, card);
  else appendCardDescriptionContent(body, card);
  dialog.showModal();
}
function appendCardInfoControls(parent, card = {}) {
  const controls = document.createElement('div');
  controls.className = 'card-info-controls';
  const description = document.createElement('button');
  description.type = 'button';
  description.className = 'card-info-button';
  description.textContent = 'Descripción';
  description.addEventListener('click', () => openCardInfoDialog(card, 'description'));
  const spells = document.createElement('button');
  spells.type = 'button';
  spells.className = 'card-info-button';
  spells.textContent = 'Hechizos';
  spells.addEventListener('click', () => openCardInfoDialog(card, 'spells'));
  controls.append(description, spells);
  parent.appendChild(controls);
  return controls;
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
    appendCardInfoControls(article, card);
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
    const article = document.createElement('article');
    article.className = `card hand-card ${appState.selectedHandIndex === index ? 'selected' : ''}`.trim();
    article.appendChild(createCardImageElement(cardImage(card), card.name, 'card-image-hand'));
    appendTextElement(article, 'h4', card.name, 'hand-card-title');
    appendBadgeRow(article, [stageLabel(card.stage), card.family, summarizeCardStats(card)]);
    appendCardInfoControls(article, card);
    const select = document.createElement('button');
    select.type = 'button';
    select.className = 'ghost hand-select-button';
    select.textContent = appState.selectedHandIndex === index ? 'Cancelar selección' : 'Invocar';
    select.addEventListener('click', () => {
      if (!canPlay) return setActionFeedback('La IA está jugando ahora; el Registro detalla sus jugadas.', 'error');
      const isSame = appState.selectedHandIndex === index;
      appState.selectedHandIndex = isSame ? null : index; appState.selectedUnitId = null;
      setActionFeedback(isSame ? 'Selección cancelada.' : `Carta seleccionada: ${card.name}. Elegí un espacio libre.`, 'normal');
      renderGame();
    });
    article.appendChild(select);
    handEl.appendChild(article);
  });
}

function renderMatchSummary({ me, enemy }) {
  const summaryEl = $('#match-summary'); if (!summaryEl) return;
  clearElement(summaryEl);
  if (!appState.match) return renderEmptyState(summaryEl, EMPTY_MESSAGES.summary);
  summaryEl.append(
    createSummaryField('Turno', appState.match.turn?.number || 1),
    createSummaryField('Mano / Mazo', `${me?.hand_count ?? '-'}/${me?.library_count ?? '-'}`),
    createSummaryField('Estado', appState.match.paused ? 'pausada' : 'en curso'),
    createSummaryField('Ganador', appState.match.winner ? formatSideLabel(appState.match.winner) : 'sin definir')
  );
}
function renderMatchLog(logEntries = []) {
  const logEl = $('#match-log'); if (!logEl) return;
  clearElement(logEl);
  const matchEntries = (Array.isArray(logEntries) ? logEntries : []).map(String).reverse();
  const entries = [...(appState.clientLog || []), ...matchEntries];
  if (!entries.length) return renderEmptyState(logEl, EMPTY_MESSAGES.matchLog);
  const list = document.createElement('ol'); list.className = 'match-log-list';
  entries.forEach((entry, index) => { const item = document.createElement('li'); item.className = 'match-log-item'; appendTextElement(item, 'span', String(index + 1).padStart(2, '0'), 'match-log-order'); appendTextElement(item, 'p', entry); list.appendChild(item); });
  logEl.appendChild(list);
}

function renderGame() {
  setActionFeedback(appState.actionFeedback.message, appState.actionFeedback.tone, { silentLog: true });
  syncBoardActionButtons();
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
function loadCards() { appState.cards = localSeedCards(); populateFamilyFilter(appState.cards); syncFamilySelects(); renderOstControls(); renderCatalog(); return Promise.resolve(); }
function loadActiveMatch() { localStorage.removeItem(STORAGE_KEY); appState.roomCode = null; appState.match = null; updateDerivedCombat(); renderGame(); return Promise.resolve(); }
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
  button.addEventListener('click', async () => { if (button.disabled) return; button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = loadingLabel; try { await handler(); } catch (err) { setStatus(err.message || 'Error inesperado', true); } finally { button.disabled = false; button.setAttribute('aria-busy', 'false'); button.textContent = idleLabel; syncBoardActionButtons(); } });
}
function syncModalHandSize() { const current = String(requestedHandSize()); document.querySelectorAll('input[name="modal-initial-hand-size"]').forEach((input) => { input.checked = input.value === current; }); }
function applyModalHandSize() { const selected = document.querySelector('input[name="modal-initial-hand-size"]:checked')?.value; const target = selected && document.querySelector(`input[name="initial-hand-size"][value="${selected}"]`); if (target) target.checked = true; }

function selectedSetupMode() { return document.querySelector('input[name="modal-deck-mode"]:checked')?.value || 'random'; }
function renderMatchSetupStep() {
  const stepKey = MATCH_SETUP_STEPS[appState.matchSetupStep] || MATCH_SETUP_STEPS[0];
  document.querySelectorAll('[data-setup-step]').forEach((panel) => { panel.hidden = panel.dataset.setupStep !== stepKey; });
  document.querySelectorAll('[data-setup-dot]').forEach((dot, index) => {
    dot.classList.toggle('is-active', index === appState.matchSetupStep);
    dot.classList.toggle('is-complete', index < appState.matchSetupStep);
  });
  const prev = $('#setup-prev-step'); const next = $('#setup-next-step'); const accept = $('#setup-accept');
  if (prev) prev.disabled = appState.matchSetupStep === 0;
  if (next) next.hidden = appState.matchSetupStep === MATCH_SETUP_STEPS.length - 1;
  if (accept) accept.hidden = appState.matchSetupStep !== MATCH_SETUP_STEPS.length - 1;
}
function setMatchSetupStep(step) { appState.matchSetupStep = Math.max(0, Math.min(MATCH_SETUP_STEPS.length - 1, step)); renderMatchSetupStep(); }
async function acceptMatchSetup() {
  applyModalHandSize();
  applyModalDeckScope();
  closeInitialHandDialog();
  if (selectedSetupMode() === 'manual') {
    setActionFeedback('Configuración aplicada. Abrí Bestiario, elegí cartas y presioná Usar selección desde Mano.', 'normal');
    document.querySelector('#catalog-panel')?.closest('details')?.setAttribute('open', '');
    return;
  }
  await createAIMatch();
}

function closeNewMatchPanel() { $('#close-new-match-panel')?.closest('details')?.removeAttribute('open'); }
function chooseManualMatchSetup() { setActionFeedback('Abrí Bestiario, elegí cartas y presioná Usar selección desde Mano.', 'normal'); closeNewMatchPanel(); }
function openInitialHandDialog() { syncModalHandSize(); syncModalDeckScope(); setMatchSetupStep(0); const dialog = $('#match-setup-dialog'); closeNewMatchPanel(); if (dialog?.showModal) dialog.showModal(); else createAIMatch(); }
function closeInitialHandDialog() { const dialog = $('#match-setup-dialog'); if (dialog?.open) dialog.close(); }



let audioContext = null;
let activeOst = null;
const OST_TRACKS = [
  {
    name: 'Forja de Wakfu Roto',
    bpm: 168,
    lead: [330, 494, 440, 370, 523, 587, 494, 392, 466, 415, 349, 554],
    bass: [82, 110, 123, 98, 92, 117],
    wave: 'square',
    accentWave: 'sawtooth',
    percussion: 'spark',
  },
  {
    name: 'Ritual del Bosque Profundo',
    bpm: 104,
    lead: [147, 220, 262, 330, 294, 247, 196, 233, 277, 349],
    bass: [36, 55, 73, 49, 65],
    wave: 'triangle',
    accentWave: 'sine',
    percussion: 'pulse',
  },
];
function playOstTone(gain, frequency, duration, type = 'sine', volume = 1, detune = 0) {
  const osc = audioContext.createOscillator(); const env = audioContext.createGain();
  osc.type = type; osc.frequency.value = frequency; osc.detune.value = detune;
  env.gain.setValueAtTime(0.0001, audioContext.currentTime);
  env.gain.exponentialRampToValueAtTime(0.018 * volume, audioContext.currentTime + 0.025);
  env.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + duration);
  osc.connect(env); env.connect(gain); osc.start(); osc.stop(audioContext.currentTime + duration + 0.03);
}
function playNoise(gain, duration = 0.05, volume = 0.45) {
  const buffer = audioContext.createBuffer(1, audioContext.sampleRate * duration, audioContext.sampleRate);
  const data = buffer.getChannelData(0); for (let i = 0; i < data.length; i += 1) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  const source = audioContext.createBufferSource(); const env = audioContext.createGain();
  source.buffer = buffer; env.gain.value = 0.025 * volume; source.connect(env); env.connect(gain); source.start();
}
function playOst(index = 0) {
  stopOst();
  audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
  const track = OST_TRACKS[index % OST_TRACKS.length];
  const gain = audioContext.createGain(); gain.gain.value = 0.32; gain.connect(audioContext.destination);
  let step = 0; const beatMs = Math.max(90, Math.round(60000 / track.bpm / 2));
  activeOst = setInterval(() => {
    const lead = track.lead[step % track.lead.length]; const bass = track.bass[Math.floor(step / 2) % track.bass.length];
    playOstTone(gain, bass, beatMs / 1000 * 0.9, 'sawtooth', step % 4 === 0 ? 1.2 : 0.8, -8);
    if (step % 2 === 0) playOstTone(gain, lead, beatMs / 1000 * 0.72, track.wave, 0.72);
    if (step % 4 === 2) playOstTone(gain, lead * 1.5, beatMs / 1000 * 0.45, track.accentWave, 0.35, 5);
    if (track.percussion === 'spark' && step % 2 === 0) playNoise(gain, 0.03, step % 8 === 0 ? 0.62 : 0.28);
    if (track.percussion === 'pulse' && step % 4 === 0) playNoise(gain, 0.08, step % 8 === 0 ? 0.36 : 0.18);
    step += 1;
  }, beatMs);
  setActionFeedback(`OST de combate activa: ${track.name}.`, 'success');
}
function stopOst() { if (activeOst) clearInterval(activeOst); activeOst = null; setActionFeedback('OST silenciada.', 'normal'); }
function renderOstControls() {
  const target = $('#ost-controls'); if (!target) return;
  clearElement(target);
  OST_TRACKS.forEach((track, index) => { const button = document.createElement('button'); button.type = 'button'; button.className = 'ghost'; button.textContent = `${index + 1}. ${track.name}`; button.addEventListener('click', () => playOst(index)); target.appendChild(button); });
  const stop = document.createElement('button'); stop.type = 'button'; stop.className = 'ghost danger'; stop.textContent = 'Silenciar OST'; stop.addEventListener('click', stopOst); target.appendChild(stop);
}

function syncFamilySelects() {
  const families = [...new Set(appState.cards.map((card) => card.family).filter(Boolean))];
  ['#match-family-select', '#modal-family-select'].forEach((selector) => {
    const select = $(selector); if (!select) return;
    const current = select.value;
    clearElement(select);
    families.forEach((family) => { const option = document.createElement('option'); option.value = family; option.textContent = family; select.appendChild(option); });
    if (families.includes(current)) select.value = current;
  });
}
function syncModalDeckScope() { const current = document.querySelector('input[name="deck-scope"]:checked')?.value || 'all'; const currentTier = document.querySelector('input[name="deck-tier"]:checked')?.value || 'all'; document.querySelectorAll('input[name="modal-deck-scope"]').forEach((input) => { input.checked = input.value === current; }); document.querySelectorAll('input[name="modal-deck-tier"]').forEach((input) => { input.checked = input.value === currentTier; }); const modalFamily = $('#modal-family-select'); if (modalFamily && $('#match-family-select')) modalFamily.value = $('#match-family-select').value; }
function applyModalDeckScope() { const selected = document.querySelector('input[name="modal-deck-scope"]:checked')?.value; const selectedTier = document.querySelector('input[name="modal-deck-tier"]:checked')?.value; const target = selected && document.querySelector(`input[name="deck-scope"][value="${selected}"]`); const tierTarget = selectedTier && document.querySelector(`input[name="deck-tier"][value="${selectedTier}"]`); if (target) target.checked = true; if (tierTarget) tierTarget.checked = true; if ($('#modal-family-select') && $('#match-family-select')) $('#match-family-select').value = $('#modal-family-select').value; }
function updatePauseShade() { const shade = $('#pause-shade'); if (shade) shade.classList.toggle('is-visible', Boolean(appState.match?.paused)); }
function setMatchPaused(paused) { if (!appState.match) return setActionFeedback('No hay duelo activo.', 'error'); if (appState.match.winner) return setActionFeedback('La partida ya terminó; reiniciala para seguir jugando.', 'error'); appState.match.paused = paused; appendLog(paused ? 'Partida pausada por el jugador.' : 'Partida reanudada por el jugador.'); persistMatch(); renderGame(); setActionFeedback(paused ? 'Partida pausada.' : 'Partida reanudada.', 'success'); }
function abandonMatch() { if (!appState.match) return setActionFeedback('No hay duelo activo.', 'error'); if (appState.match.winner) return setActionFeedback('La partida ya estaba terminada.', 'error'); appendLog('El jugador abandonó la partida.'); appState.match.winner = 'guest'; persistMatch(); renderGame(); setActionFeedback('Abandonaste la partida. La IA gana el duelo.', 'error'); }
function restartMatch() { const cfg = appState.lastMatchConfig || { selectedIds: [...appState.selectedCatalogCardIds], handSize: requestedHandSize() }; startLocalMatch(cfg.selectedIds || [], cfg.handSize || requestedHandSize()); renderGame(); setActionFeedback('Partida reiniciada con la misma configuración.', 'success'); }
function showSuccessDialog(title, message) { const dialog = $('#success-dialog'); if (!dialog?.showModal) return; $('#success-title').textContent = title; $('#success-message').textContent = message; dialog.showModal(); }
function confirmDecision(title, message) {
  const dialog = $('#decision-dialog'); if (!dialog?.showModal) return Promise.resolve(window.confirm(message));
  $('#decision-title').textContent = title; $('#decision-message').textContent = message;
  return new Promise((resolve) => {
    let done = false; const finish = (value) => { if (done) return; done = true; dialog.close(); resolve(value); };
    $('#decision-confirm')?.addEventListener('click', () => finish(true), { once: true });
    $('#decision-cancel')?.addEventListener('click', () => finish(false), { once: true });
    $('#decision-close')?.addEventListener('click', () => finish(false), { once: true });
    dialog.addEventListener('cancel', () => finish(false), { once: true });
    dialog.showModal();
  });
}
async function confirmRestartMatch() { if (await confirmDecision('Reiniciar partida', '¿Realmente querés reiniciar la partida?')) { restartMatch(); showSuccessDialog('Partida reiniciada', 'La partida se reinició correctamente.'); } }
async function confirmAbandonMatch() { if (await confirmDecision('Abandonar partida', '¿Realmente querés abandonar la partida?')) { abandonMatch(); showSuccessDialog('Partida abandonada', 'Abandonaste la partida.'); } }
function openHandDialog() { const dialog = $('#hand-dialog'); if (dialog?.showModal) dialog.showModal(); }
function syncBoardActionButtons() { const hasMatch = Boolean(appState.match); const isBusy = Boolean(appState.aiPlayback); const finished = Boolean(appState.match?.winner); ['#end-turn-btn', '#pause-match-btn', '#restart-match-btn', '#abandon-match-btn'].forEach((selector) => { const button = $(selector); if (!button) return; button.disabled = !hasMatch || isBusy || (finished && selector !== '#restart-match-btn'); }); const pause = $('#pause-match-btn'); if (pause) pause.textContent = appState.match?.paused ? 'Reanudar' : 'Pausar'; updatePauseShade(); }

function boot() {
  renderGame(); $('#open-new-match-panel')?.addEventListener('click', (event) => { event.preventDefault(); openInitialHandDialog(); }); bindAsyncButton('#create-ai-match', () => { openInitialHandDialog(); return Promise.resolve(); }); $('#create-manual-match')?.addEventListener('click', chooseManualMatchSetup); $('#close-new-match-panel')?.addEventListener('click', closeNewMatchPanel); $('#match-setup-close')?.addEventListener('click', closeInitialHandDialog); bindAsyncButton('#shuffle-monsters', shuffleMonsters); bindAsyncButton('#create-selected-match', createSelectedMatch); bindAsyncButton('#end-turn-btn', endTurn); bindAsyncButton('#pause-match-btn', () => { setMatchPaused(!appState.match?.paused); return Promise.resolve(); }); bindAsyncButton('#restart-match-btn', confirmRestartMatch); bindAsyncButton('#abandon-match-btn', confirmAbandonMatch); $('#open-hand-dialog')?.addEventListener('click', openHandDialog); $('#close-hand-dialog')?.addEventListener('click', () => $('#hand-dialog')?.close()); $('#setup-prev-step')?.addEventListener('click', () => setMatchSetupStep(appState.matchSetupStep - 1)); $('#setup-next-step')?.addEventListener('click', () => setMatchSetupStep(appState.matchSetupStep + 1)); bindAsyncButton('#setup-accept', acceptMatchSetup);
  loadCards().then(loadActiveMatch).catch((err) => { setStatus(err.message || 'No se pudo iniciar el juego.', true); setActionFeedback('No se pudo cargar el duelo. Iniciá un nuevo enfrentamiento o usá la selección manual.', 'error'); renderGame(); }).finally(() => { if (!appState.match) setStatus('Sin duelo local activo. Iniciá uno nuevo o prepará una selección manual.'); });
}
document.addEventListener('DOMContentLoaded', boot, { once: true });
