/**
 * O.R.I.O.N. — RedRock Capital
 * Dashboard d'Intelligence Systémique Intégrée
 *
 * Client WebSocket + API REST pour le contrôle et la visualisation
 * temps réel du système de trading algorithmique.
 */

// ═══ STATE ═══
let ws = null;
let cycleCount = 0;
let autoTradeActive = false;
let perfChart = null;
let allocChart = null;
let portfolioHistory = [];
let lastData = null;
let initialPrices = {};
let reconnectAttempts = 0;
let ibkrConnected = false;

// ═══ INIT ═══
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initCharts();
  connectWebSocket();
  updateClock();
  setInterval(updateClock, 1000);
});

// ═══ NAVIGATION ═══
function initNavigation() {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      document.querySelectorAll('.content').forEach(p => p.classList.add('hidden'));
      const page = document.getElementById('page-' + tab.dataset.page);
      if (page) page.classList.remove('hidden');
    });
  });
}

// ═══ WEBSOCKET ═══
function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    reconnectAttempts = 0;
    updateStatus('connected', 'Connecté');
    console.log('[O.R.I.O.N.] WebSocket connecté');
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      lastData = data;
      cycleCount++;
      processUpdate(data);
    } catch (e) {
      console.error('[O.R.I.O.N.] Erreur parsing:', e);
    }
  };

  ws.onclose = () => {
    updateStatus('disconnected', 'Déconnecté');
    // Reconnexion automatique avec backoff
    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
    console.log(`[O.R.I.O.N.] Reconnexion dans ${delay/1000}s...`);
    setTimeout(connectWebSocket, delay);
  };

  ws.onerror = () => {
    updateStatus('error', 'Erreur connexion');
  };
}

function sendCommand(command, data = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ command, ...data }));
  }
}

// ═══ API CALLS ═══
async function apiCall(endpoint, method = 'GET') {
  try {
    const resp = await fetch(`/api/${endpoint}`, { method });
    return await resp.json();
  } catch (e) {
    console.error(`[API] Erreur ${endpoint}:`, e);
    return null;
  }
}

async function toggleAutoTrade() {
  autoTradeActive = !autoTradeActive;
  const action = autoTradeActive ? 'start' : 'stop';
  await apiCall(`auto-trade/${action}`, 'POST');
  updateAutoTradeUI();
}

async function runSingleCycle() {
  const data = await apiCall('cycle');
  if (data) {
    lastData = data;
    cycleCount++;
    processUpdate(data);
  }
}

async function closePosition(symbol) {
  const encoded = symbol.replace('/', '-');
  await apiCall(`close-position/${encoded}`, 'POST');
}

// ═══ PROCESS UPDATE ═══
function processUpdate(data) {
  document.getElementById('cycleCounter').textContent = `Cycle: ${cycleCount}`;
  document.getElementById('cycleTime').textContent =
    `Dernier cycle: ${new Date().toLocaleTimeString('fr-FR')}`;

  if (data.execution) updatePortfolio(data.execution);
  if (data.macro) updateMacro(data.macro);
  if (data.volatility) updateVolatility(data.volatility);
  if (data.signals) updateSignals(data.signals);
  if (data.allocation) updateAllocation(data.allocation);
  if (data.risk) updateRisk(data.risk);
  if (data.prices) updateMarkets(data.prices);
  if (data.ibkr) updateIBKR(data.ibkr);

  autoTradeActive = data.execution?.auto_trade || false;
  updateAutoTradeUI();
}

// ═══ PORTFOLIO ═══
function updatePortfolio(exec) {
  const value = exec.portfolio_value || 100000;
  const cash = exec.cash || 100000;
  const pnl = exec.total_pnl || 0;

  document.getElementById('portfolioValue').textContent = formatCurrency(value);
  document.getElementById('cashValue').textContent = formatCurrency(cash);

  const pnlEl = document.getElementById('portfolioPnl');
  pnlEl.textContent = `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)}`;
  pnlEl.className = `card-change ${pnl >= 0 ? 'positive' : 'negative'}`;

  // Portfolio history for chart
  portfolioHistory.push({ time: new Date(), value });
  if (portfolioHistory.length > 100) portfolioHistory.shift();
  updatePerfChart();

  // Positions
  updatePositions(exec.open_positions || {});

  // Trade stats
  if (exec.stats) updateTradeStats(exec.stats);
  if (exec.trade_history) updateTradeHistory(exec.trade_history);
}

function updatePositions(positions) {
  const tbody = document.getElementById('positionsTable');
  const empty = document.getElementById('posEmpty');
  const count = Object.keys(positions).length;
  document.getElementById('posCount').textContent = count;

  if (count === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = Object.entries(positions).map(([sym, pos]) => {
    const pnlClass = pos.pnl >= 0 ? 'positive' : 'negative';
    const sideTag = pos.side === 'buy' ? 'tag-buy' : 'tag-sell';
    return `<tr>
      <td><strong>${sym}</strong></td>
      <td><span class="tag ${sideTag}">${pos.side.toUpperCase()}</span></td>
      <td>${pos.quantity}</td>
      <td>${formatPrice(pos.entry_price)}</td>
      <td>${formatPrice(pos.current_price)}</td>
      <td class="${pnlClass}">${pos.pnl >= 0 ? '+' : ''}${formatCurrency(pos.pnl)}</td>
      <td class="${pnlClass}">${pos.pnl_pct >= 0 ? '+' : ''}${pos.pnl_pct.toFixed(2)}%</td>
      <td>${formatPrice(pos.stop_loss)}</td>
      <td>${formatPrice(pos.take_profit)}</td>
      <td><button class="btn btn-danger btn-sm" onclick="closePosition('${sym}')">Fermer</button></td>
    </tr>`;
  }).join('');
}

// ═══ MACRO ═══
function updateMacro(macro) {
  if (macro.regime) {
    const regime = macro.regime;
    const badge = document.getElementById('regimeBadge');
    const regimeLabels = {
      early_expansion: 'Expansion',
      late_expansion: 'Expansion Tardive',
      slowdown: 'Ralentissement',
      contraction: 'Contraction',
      crisis: 'Crise',
      recovery: 'Reprise',
      stagnation: 'Stagnation',
      reflation: 'Reflation',
    };
    badge.textContent = regimeLabels[regime.regime] || regime.regime;
    badge.className = `card-value regime-badge regime-${regime.regime}`;
    document.getElementById('regimeConfidence').textContent =
      `Confiance: ${(regime.confidence * 100).toFixed(0)}%`;
  }

  // Cycles
  if (macro.cycle?.cycles) {
    const cycleDiv = document.getElementById('cycleInfo');
    if (cycleDiv) {
      const cycleLabels = {
        kitchin: 'Kitchin (3-5a)',
        juglar: 'Juglar (7-11a)',
        kuznets: 'Kuznets (15-25a)',
        kondratiev: 'Kondratiev (40-60a)',
        debt_super: 'Debt Super (75-100a)',
      };
      cycleDiv.innerHTML = Object.entries(macro.cycle.cycles).map(([name, data]) => `
        <div class="cycle-row">
          <span class="cycle-name">${cycleLabels[name] || name}</span>
          <span class="cycle-phase">${data.phase}</span>
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${data.position * 100}%"></div>
          </div>
        </div>
      `).join('');
    }
  }

  // Transition probabilities (from API)
  if (macro.transition_probabilities) {
    const transDiv = document.getElementById('transitionInfo');
    if (transDiv) {
      const entries = Object.entries(macro.transition_probabilities)
        .sort((a, b) => b[1] - a[1]);
      transDiv.innerHTML = entries.map(([regime, prob]) => `
        <div class="cycle-row">
          <span class="cycle-name">${regime}</span>
          <span>${(prob * 100).toFixed(0)}%</span>
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${prob * 100}%"></div>
          </div>
        </div>
      `).join('');
    }
  }
}

// ═══ VOLATILITY ═══
function updateVolatility(vol) {
  document.getElementById('meanVol').textContent = vol.mean_regime || '—';
  document.getElementById('volRegime').textContent =
    `Régime: ${vol.mean_regime || '—'}`;
}

// ═══ SIGNALS ═══
function updateSignals(signals) {
  const entries = Object.entries(signals)
    .sort((a, b) => b[1].score - a[1].score);

  const top5 = entries.filter(([, s]) => s.score > 0).slice(0, 8);
  const bottom5 = entries.filter(([, s]) => s.score < 0).slice(-8).reverse();

  document.getElementById('topSignals').innerHTML = top5.map(([sym, s]) =>
    signalItemHTML(sym, s)
  ).join('');

  document.getElementById('bottomSignals').innerHTML = bottom5.map(([sym, s]) =>
    signalItemHTML(sym, s)
  ).join('');

  // Full signals table
  const tbody = document.getElementById('signalsTable');
  if (tbody) {
    tbody.innerHTML = entries.map(([sym, s]) => {
      const typeTag = s.type === 'overweight' ? 'tag-overweight' :
                      s.type === 'underweight' ? 'tag-underweight' : 'tag-neutral';
      const scoreClass = s.score >= 0 ? 'positive' : 'negative';
      return `<tr>
        <td><strong>${sym}</strong></td>
        <td><span class="tag ${typeTag}">${s.type}</span></td>
        <td class="${scoreClass}">${s.score >= 0 ? '+' : ''}${s.score.toFixed(3)}</td>
        <td>${s.strength}</td>
        <td>${(s.confidence * 100).toFixed(0)}%</td>
        <td>${(s.sources?.macro_regime || 0).toFixed(2)}</td>
        <td>${(s.sources?.volatility || 0).toFixed(2)}</td>
        <td>${(s.sources?.cycle_position || 0).toFixed(2)}</td>
        <td>${(s.sources?.risk_budget || 0).toFixed(2)}</td>
      </tr>`;
    }).join('');
  }
}

function signalItemHTML(sym, signal) {
  const score = signal.score;
  const cls = score >= 0 ? 'positive' : 'negative';
  const barCls = score >= 0 ? 'positive' : 'negative';
  const width = Math.min(Math.abs(score) * 100, 50);

  return `<div class="signal-item">
    <span class="symbol">${sym}</span>
    <div class="signal-bar">
      <div class="signal-bar-fill ${barCls}" style="width: ${width}%"></div>
    </div>
    <span class="signal-score ${cls}">${score >= 0 ? '+' : ''}${score.toFixed(3)}</span>
  </div>`;
}

// ═══ ALLOCATION ═══
function updateAllocation(alloc) {
  if (!alloc.weights || Object.keys(alloc.weights).length === 0) return;

  // Aggregate by asset class
  const classes = {};
  Object.entries(alloc.weights).forEach(([sym, w]) => {
    const cls = classifyAsset(sym);
    classes[cls] = (classes[cls] || 0) + w;
  });

  const labels = Object.keys(classes);
  const data = Object.values(classes).map(v => +(v * 100).toFixed(1));
  const colors = labels.map(l => assetClassColor(l));

  if (allocChart) {
    allocChart.data.labels = labels;
    allocChart.data.datasets[0].data = data;
    allocChart.data.datasets[0].backgroundColor = colors;
    allocChart.update('none');
  }
}

// ═══ RISK ═══
function updateRisk(risk) {
  if (!risk) return;
  const m = risk;
  if (m.var !== undefined) document.getElementById('riskVar').textContent = (m.var * 100).toFixed(2) + '%';
  if (m.cvar !== undefined) document.getElementById('riskCvar').textContent = (m.cvar * 100).toFixed(2) + '%';
  if (m.sharpe !== undefined) document.getElementById('riskSharpe').textContent = m.sharpe.toFixed(2);
  if (m.max_drawdown !== undefined) document.getElementById('riskDrawdown').textContent = (m.max_drawdown * 100).toFixed(2) + '%';
}

// ═══ MARKETS ═══
function updateMarkets(prices) {
  const grid = document.getElementById('marketsGrid');
  if (!grid) return;

  // Store initial prices for change calc
  Object.entries(prices).forEach(([sym, price]) => {
    if (!initialPrices[sym]) initialPrices[sym] = price;
  });

  grid.innerHTML = Object.entries(prices).map(([sym, price]) => {
    const initial = initialPrices[sym] || price;
    const change = ((price - initial) / initial) * 100;
    const changeClass = change >= 0 ? 'positive' : 'negative';
    return `<div class="market-tile">
      <div class="market-symbol">${sym}</div>
      <div class="market-price">${formatPrice(price)}</div>
      <div class="market-change ${changeClass}">${change >= 0 ? '+' : ''}${change.toFixed(3)}%</div>
    </div>`;
  }).join('');
}

// ═══ TRADE STATS ═══
function updateTradeStats(stats) {
  document.getElementById('statTotalTrades').textContent = stats.total_trades || 0;
  document.getElementById('statWinRate').textContent = (stats.win_rate || 0) + '%';
  document.getElementById('statAvgPnl').textContent = formatCurrency(stats.avg_pnl || 0);
  document.getElementById('statProfitFactor').textContent = stats.profit_factor || 0;
}

function updateTradeHistory(trades) {
  const tbody = document.getElementById('tradeHistoryTable');
  const empty = document.getElementById('tradesEmpty');
  if (!tbody) return;

  if (trades.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = trades.slice().reverse().map(t => {
    const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
    const sideTag = t.side === 'buy' ? 'tag-buy' : 'tag-sell';
    return `<tr>
      <td>${new Date(t.entry_time).toLocaleDateString('fr-FR')}</td>
      <td><strong>${t.symbol}</strong></td>
      <td><span class="tag ${sideTag}">${t.side.toUpperCase()}</span></td>
      <td>${formatPrice(t.entry_price)}</td>
      <td>${formatPrice(t.exit_price)}</td>
      <td class="${pnlClass}">${t.pnl >= 0 ? '+' : ''}${formatCurrency(t.pnl)}</td>
      <td class="${pnlClass}">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</td>
      <td>${t.duration_hours.toFixed(1)}h</td>
    </tr>`;
  }).join('');
}

// ═══ CHARTS ═══
function initCharts() {
  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#8888aa', font: { family: 'monospace', size: 11 } } },
    },
  };

  // Performance chart
  const perfCtx = document.getElementById('perfChart');
  if (perfCtx) {
    perfChart = new Chart(perfCtx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Portefeuille ($)',
          data: [],
          borderColor: '#4a6cf7',
          backgroundColor: 'rgba(74, 108, 247, 0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        }],
      },
      options: {
        ...chartDefaults,
        scales: {
          x: { display: false },
          y: {
            grid: { color: 'rgba(42, 42, 64, 0.5)' },
            ticks: { color: '#8888aa', font: { family: 'monospace', size: 10 } },
          },
        },
      },
    });
  }

  // Allocation chart
  const allocCtx = document.getElementById('allocChart');
  if (allocCtx) {
    allocChart = new Chart(allocCtx, {
      type: 'doughnut',
      data: {
        labels: [],
        datasets: [{
          data: [],
          backgroundColor: [],
          borderWidth: 0,
        }],
      },
      options: {
        ...chartDefaults,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#8888aa', font: { family: 'monospace', size: 10 }, padding: 8 },
          },
        },
      },
    });
  }
}

function updatePerfChart() {
  if (!perfChart || portfolioHistory.length === 0) return;
  perfChart.data.labels = portfolioHistory.map(p =>
    p.time.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  );
  perfChart.data.datasets[0].data = portfolioHistory.map(p => p.value);
  perfChart.update('none');
}

// ═══ UI HELPERS ═══
function updateAutoTradeUI() {
  const btn = document.getElementById('btnAutoTrade');
  const status = document.getElementById('autoStatus');
  if (autoTradeActive) {
    btn.textContent = 'Désactiver le Trading Auto';
    btn.classList.add('active');
    status.textContent = 'Mode: Trading Automatique';
    status.style.color = '#00d97e';
  } else {
    btn.textContent = 'Activer le Trading Auto';
    btn.classList.remove('active');
    status.textContent = 'Mode: Observation';
    status.style.color = '';
  }
}

function updateStatus(state, text) {
  const el = document.getElementById('systemStatus');
  if (!el) return;
  const dot = el.querySelector('.status-dot');
  const txt = el.querySelector('.status-text');
  txt.textContent = text;
  dot.style.background = state === 'connected' ? '#00d97e' :
                          state === 'error' ? '#e63946' : '#555570';
}

function updateClock() {
  const el = document.getElementById('footerTime');
  if (el) el.textContent = new Date().toLocaleString('fr-FR');
}

// ═══ FORMATTERS ═══
function formatCurrency(val) {
  return '$' + Number(val).toLocaleString('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
}

function formatPrice(val) {
  if (val >= 1000) return Number(val).toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (val >= 10) return Number(val).toFixed(2);
  if (val >= 1) return Number(val).toFixed(4);
  return Number(val).toFixed(5);
}

function classifyAsset(symbol) {
  const s = symbol.toUpperCase();
  if (s.includes('/') && !s.includes('BTC') && !s.includes('ETH') && !s.includes('SOL')) return 'Forex';
  if (['SPX','NDX','DJIA','DAX','FTSE100','CAC40','NIKKEI225','HSI','STOXX600'].some(x => s.includes(x))) return 'Actions';
  if (s.match(/\d+Y$/) || s.includes('TIPS')) return 'Obligations';
  if (['GOLD','SILVER','WTI','BRENT','NATGAS','COPPER','WHEAT','CORN'].some(x => s.includes(x))) return 'Matières';
  if (['BTC','ETH','SOL'].some(x => s.includes(x))) return 'Crypto';
  if (['VIX','VSTOXX','VDAX','MOVE'].some(x => s.includes(x))) return 'Volatilité';
  return 'Autre';
}

function assetClassColor(cls) {
  const colors = {
    'Forex': '#4a6cf7',
    'Actions': '#00d97e',
    'Obligations': '#00d4ff',
    'Matières': '#ff9f43',
    'Crypto': '#a855f7',
    'Volatilité': '#e63946',
    'Autre': '#555570',
  };
  return colors[cls] || '#555570';
}

// ═══ IBKR ═══
function updateIBKR(ibkr) {
  if (!ibkr) return;

  const card = document.getElementById('ibkrCard');
  const statusText = document.getElementById('ibkrStatusText');
  const account = document.getElementById('ibkrAccount');
  const reconnect = document.getElementById('ibkrReconnect');
  const toggle = document.getElementById('ibkrToggle');
  const btn = document.getElementById('ibkrBtn');
  const loader = document.getElementById('ibkrLoader');

  const status = ibkr.status;
  ibkrConnected = status === 'connected';

  // Remove all state classes
  card.classList.remove('connected', 'disconnected', 'connecting');

  // Hide loader unless connecting
  if (status !== 'connecting') {
    loader.classList.add('hidden');
  }

  if (status === 'connected') {
    card.classList.add('connected');
    statusText.textContent = `Connecté — ${ibkr.account_id}`;
    account.textContent = ibkr.account_id;
    reconnect.textContent = '';
    toggle.checked = true;
    btn.textContent = 'Déconnecter';
  } else if (status === 'connecting') {
    card.classList.add('connecting');
    statusText.textContent = 'Connexion en cours...';
    account.textContent = '';
    reconnect.textContent = '';
    loader.classList.remove('hidden');
  } else if (status === 'reconnecting') {
    card.classList.add('disconnected');
    statusText.textContent = ibkr.last_error || 'Déconnecté';
    account.textContent = '';
    toggle.checked = false;
    btn.textContent = 'Connecter';
    if (ibkr.reconnect_countdown > 0) {
      reconnect.textContent = `Reconnexion dans ${ibkr.reconnect_countdown}s...`;
    }
  } else {
    // disconnected or error
    card.classList.add('disconnected');
    statusText.textContent = ibkr.last_error || 'Déconnecté';
    account.textContent = '';
    reconnect.textContent = '';
    toggle.checked = false;
    btn.textContent = 'Connecter';
  }
}

async function handleIBKRToggle(checkbox) {
  if (checkbox.checked) {
    await connectIBKR();
  } else {
    await disconnectIBKR();
  }
}

async function handleIBKRButton() {
  if (ibkrConnected) {
    await disconnectIBKR();
  } else {
    await connectIBKR();
  }
}

async function connectIBKR() {
  const loader = document.getElementById('ibkrLoader');
  const card = document.getElementById('ibkrCard');
  const statusText = document.getElementById('ibkrStatusText');

  // Show loading state
  loader.classList.remove('hidden');
  card.classList.remove('connected', 'disconnected');
  card.classList.add('connecting');
  statusText.textContent = 'Connexion en cours...';

  const result = await apiCall('ibkr/connect', 'POST');
  if (result) {
    updateIBKR(result);
  }
  loader.classList.add('hidden');
}

async function disconnectIBKR() {
  const result = await apiCall('ibkr/disconnect', 'POST');
  if (result) {
    updateIBKR(result);
  }
}
