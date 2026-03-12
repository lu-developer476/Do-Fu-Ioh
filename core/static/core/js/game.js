let appState = {
  me: null,
  cards: [],
  roomCode: null,
  match: null,
};

const $ = (sel) => document.querySelector(sel);
const familyFilter = $('#family-filter');

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || 'Error inesperado');
  return data;
}

function renderCatalog() {
  const filter = familyFilter.value;
  const cards = appState.cards.filter((card) => !filter || card.family === filter);
  $('#catalog').innerHTML = cards.map(card => `
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
  if (!match || !appState.me) return { me: null, enemy: null, mySide: null };
  const mySide = match.host.user_id === appState.me.id ? 'host' : 'guest';
  return {
    me: match[mySide],
    enemy: match[mySide === 'host' ? 'guest' : 'host'],
    mySide,
  };
}

function findUnitAt(units = [], x, y) {
  return units.find(u => u.x === x && u.y === y);
}

function shortId(unitId) {
  return unitId?.slice(-4) || '----';
}

function renderBoard() {
  const match = appState.match;
  if (!match) {
    $('#board').innerHTML = '<div class="small">Todavía no hay partida.</div>';
    $('#hand').innerHTML = '<div class="small">Tu mano aparecerá acá.</div>';
    $('#match-summary').innerHTML = '<div class="small">Crea o únete a una sala.</div>';
    $('#unit-list').innerHTML = '<div class="small">Sin unidades.</div>';
    $('#log').innerHTML = '';
    return;
  }

  const { me, enemy, mySide } = resolveSides();
  const width = match.board.width;
  const height = match.board.height;

  const cells = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const ownUnit = findUnitAt(me?.units, x, y);
      const enemyUnit = findUnitAt(enemy?.units, x, y);
      const unit = ownUnit || enemyUnit;
      const ownerClass = ownUnit ? 'ally' : (enemyUnit ? 'enemy' : 'empty');
      cells.push(`
        <div class="cell ${ownerClass}">
          <div class="coord">${x},${y}</div>
          ${unit ? `<div class="token"><strong>${unit.card.name}</strong><span>#${shortId(unit.id)}</span><span>PdV ${unit.current_hp} · PdC ${unit.current_shell}</span><span>Ataques ${unit.attacks_left} · Movimiento ${unit.move_left}</span></div>` : '<div class="small">·</div>'}
        </div>
      `);
    }
  }
  $('#board').innerHTML = cells.join('');

  $('#hand').innerHTML = (me?.hand || []).map((card, index) => `
    <article class="card">
      <img src="${card.image}" alt="${card.name}" />
      <h4>#${index} · ${card.name}</h4>
      <div class="meta">
        <span class="badge">${card.family}</span>
        <span class="badge">${card.stage}</span>
        <span class="badge">PA ${card.action_points}</span>
        <span class="badge">PM ${card.movement_points}</span>
      </div>
    </article>
  `).join('') || '<div class="small">No quedan cartas en mano.</div>';

  $('#match-summary').innerHTML = `
    <div><strong>Sala:</strong> ${appState.roomCode || '-'}</div>
    <div><strong>Tu lado:</strong> ${mySide || '-'}</div>
    <div><strong>Turno:</strong> ${match.turn.active_side}</div>
    <div><strong>Número de turno:</strong> ${match.turn.number}</div>
    <div><strong>Fase:</strong> ${match.turn.phase}</div>
    <div><strong>Tu vida:</strong> ${me?.life ?? '-'} · <strong>Energía:</strong> ${me?.energy ?? '-'}/${me?.max_energy ?? '-'}</div>
    <div><strong>Vida rival:</strong> ${enemy?.life ?? '-'}</div>
    <div><strong>Biblioteca rival:</strong> ${enemy?.library_count ?? 0} · <strong>Mano rival:</strong> ${enemy?.hand_count ?? 0}</div>
    <div><strong>Ganador:</strong> ${match.winner || 'sin definir'}</div>
  `;

  const ownUnits = me?.units || [];
  const enemyUnits = enemy?.units || [];
  $('#unit-list').innerHTML = `
    <strong>Tus unidades</strong>
    ${ownUnits.map(u => `<div>#${shortId(u.id)} · ${u.card.name} (${u.x},${u.y}) · ATK ${u.attacks_left} · MOV ${u.move_left}</div>`).join('') || '<div>Sin unidades propias.</div>'}
    <hr />
    <strong>Unidades enemigas</strong>
    ${enemyUnits.map(u => `<div>#${shortId(u.id)} · ${u.card.name} (${u.x},${u.y})</div>`).join('') || '<div>Sin unidades enemigas.</div>'}
  `;

  $('#log').innerHTML = (match.log || []).slice().reverse().map(item => `<div class="log-item">${item}</div>`).join('');
}

async function loadCards() {
  const data = await api('/api/cards/');
  appState.cards = data.cards;
  const families = [...new Set(data.cards.map(card => card.family))];
  familyFilter.innerHTML = '<option value="">Todas las familias</option>' + families.map(f => `<option value="${f}">${f}</option>`).join('');
  renderCatalog();
}

async function authAction(kind) {
  const payload = {
    username: $('#username').value,
    email: $('#email').value,
    password: $('#password').value,
  };
  const data = await api(`/api/auth/${kind}/`, { method: 'POST', body: JSON.stringify(payload) });
  appState.me = data.user;
  $('#auth-status').textContent = `Sesión activa como ${data.user.username}.`;
}

async function loadProfile() {
  try {
    const data = await api('/api/auth/profile/');
    appState.me = data.user;
    $('#auth-status').textContent = `Sesión activa como ${data.user.username}.`;
  } catch {
    $('#auth-status').textContent = 'Todavía no iniciaste sesión.';
  }
}

async function createMatch() {
  const data = await api('/api/match/create/', { method: 'POST', body: '{}' });
  appState.roomCode = data.room_code;
  appState.match = data.match;
  renderBoard();
}

async function joinMatch() {
  const code = $('#join-room-code').value.trim().toUpperCase();
  const data = await api(`/api/match/${code}/join/`, { method: 'POST', body: '{}' });
  appState.roomCode = data.room_code;
  appState.match = data.match;
  renderBoard();
}

async function refreshMatch() {
  if (!appState.roomCode) return;
  const data = await api(`/api/match/${appState.roomCode}/`);
  appState.match = data.match;
  renderBoard();
}

async function action(kind) {
  if (!appState.roomCode) return alert('Primero crea o únete a una sala.');
  const payload = {
    action: kind,
    hand_index: Number($('#hand-index').value),
    x: Number($('#summon-x').value),
    y: Number($('#summon-y').value),
    unit_id: $('#unit-id').value.trim(),
    to_x: Number($('#move-x').value),
    to_y: Number($('#move-y').value),
    attacker_id: $('#attacker-id').value.trim(),
    target_id: $('#target-id').value.trim(),
  };
  const data = await api(`/api/match/${appState.roomCode}/action/`, { method: 'POST', body: JSON.stringify(payload) });
  appState.match = data.match;
  renderBoard();
}

$('#register-btn').addEventListener('click', () => authAction('register').catch(err => alert(err.message)));
$('#login-btn').addEventListener('click', () => authAction('login').catch(err => alert(err.message)));
$('#logout-btn').addEventListener('click', async () => {
  await api('/api/auth/logout/', { method: 'POST', body: '{}' });
  appState.me = null;
  $('#auth-status').textContent = 'Sesión cerrada.';
});
$('#create-match').addEventListener('click', () => createMatch().catch(err => alert(err.message)));
$('#join-match').addEventListener('click', () => joinMatch().catch(err => alert(err.message)));
$('#refresh-state').addEventListener('click', () => refreshMatch().catch(err => alert(err.message)));
$('#summon-btn').addEventListener('click', () => action('summon').catch(err => alert(err.message)));
$('#move-btn').addEventListener('click', () => action('move').catch(err => alert(err.message)));
$('#attack-btn').addEventListener('click', () => action('attack').catch(err => alert(err.message)));
$('#direct-attack-btn').addEventListener('click', () => action('direct_attack').catch(err => alert(err.message)));
$('#next-phase-btn').addEventListener('click', () => action('next_phase').catch(err => alert(err.message)));
$('#end-turn-btn').addEventListener('click', () => action('end_turn').catch(err => alert(err.message)));
familyFilter.addEventListener('change', renderCatalog);

loadCards().then(loadProfile).then(renderBoard);
