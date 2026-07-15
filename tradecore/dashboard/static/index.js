// Global Application State
let ws = null;
let reconnectInterval = 1000;
let isWsOnline = false;
let pollingTimer = null;

let currentMode = "paper";
let tickerPrices = {};
let openPositions = [];
let tradesPage = 1;
const tradesPageSize = 50;
let equityChart = null;
let currentRange = "all";

// Price Chart Variables
let priceChart = null;
let candlestickSeries = null;
let lineSeries = null;
let candleMarkersPrimitive = null;
let lineMarkersPrimitive = null;
let currentChartSymbol = "BTC/USDT";
let currentChartView = "candle";
let currentChartRange = "all";
let lastCandle = null;

// DOM Elements
const modeBadge = document.getElementById("mode-badge");
const headerEquity = document.getElementById("header-equity");
const headerPnlToday = document.getElementById("header-pnl-today");
const headerPnlTotal = document.getElementById("header-pnl-total");
const btnModeSwitch = document.getElementById("btn-mode-switch");
const btnPauseResume = document.getElementById("btn-pause-resume");
const btnKillswitch = document.getElementById("btn-killswitch");
const btnRearm = document.getElementById("btn-rearm");
const btnResetPaper = document.getElementById("btn-reset-paper");
const killswitchBanner = document.getElementById("killswitch-banner");
const btnBannerRearm = document.getElementById("btn-banner-rearm");

const positionsBody = document.getElementById("positions-table-body");
const positionsEmpty = document.getElementById("positions-empty");
const tradesBody = document.getElementById("trades-table-body");
const tradesEmpty = document.getElementById("trades-empty");
const tradesPaginationInfo = document.getElementById("trades-pagination-info");
const btnTradesPrev = document.getElementById("btn-trades-prev");
const btnTradesNext = document.getElementById("btn-trades-next");
const signalsBody = document.getElementById("signals-table-body");
const signalsEmpty = document.getElementById("signals-empty");
const btnExportCsv = document.getElementById("btn-export-csv");

// Status Info Panel 5
const statusConnection = document.getElementById("status-connection");
const statusUptime = document.getElementById("status-uptime");
const statusRisk = document.getElementById("status-risk");
const statusStrategy = document.getElementById("status-strategy");
const statusOllama = document.getElementById("status-ollama");
const statusFeedDelays = document.getElementById("status-feed-delays");

// Modals
const modalModeSwitch = document.getElementById("modal-mode-switch");
const preflightBox = document.getElementById("preflight-box");
const preflightList = document.getElementById("preflight-list");
const overrideBox = document.getElementById("override-box");
const chkOverride = document.getElementById("chk-override");
const confirmationInputBox = document.getElementById("confirmation-input-box");
const txtConfirm = document.getElementById("txt-confirm");
const btnModalCancel = document.getElementById("btn-modal-cancel");
const btnModalConfirm = document.getElementById("btn-modal-confirm");

const modalRearm = document.getElementById("modal-rearm");
const txtRearmConfirm = document.getElementById("txt-rearm-confirm");
const btnRearmCancel = document.getElementById("btn-rearm-cancel");
const btnRearmSubmit = document.getElementById("btn-rearm-submit");


// Initialize Application
window.addEventListener("DOMContentLoaded", () => {
  // Chart init failures (e.g. a charting library API mismatch) must never
  // block websocket/data loading/button wiring below -- a previous CDN
  // version bump silently broke the whole dashboard this way.
  try {
    initChart();
  } catch (e) {
    console.error("Failed to initialize equity chart", e);
  }
  try {
    initPriceChart();
  } catch (e) {
    console.error("Failed to initialize price chart", e);
  }
  connectWebSocket();
  loadAllPanelData();

  // Range Selector Click Events
  document.querySelectorAll(".btn-range").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".btn-range").forEach(b => b.classList.remove("bg-blue-600", "text-white"));
      e.target.classList.add("bg-blue-600", "text-white");
      currentRange = e.target.getAttribute("data-range");
      loadEquityData();
    });
  });

  // Buttons Event Listeners
  btnModeSwitch.addEventListener("click", openModeSwitchModal);
  btnModalCancel.addEventListener("click", () => modalModeSwitch.classList.add("hidden"));
  btnPauseResume.addEventListener("click", toggleStrategyState);
  btnKillswitch.addEventListener("click", triggerKillswitch);
  
  btnRearm.addEventListener("click", openRearmModal);
  btnBannerRearm.addEventListener("click", openRearmModal);
  btnRearmCancel.addEventListener("click", () => modalRearm.classList.add("hidden"));
  btnRearmSubmit.addEventListener("click", submitRearm);
  txtRearmConfirm.addEventListener("input", checkRearmConfirm);

  btnResetPaper.addEventListener("click", resetPaperAccount);

  btnTradesPrev.addEventListener("click", () => { if (tradesPage > 1) { tradesPage--; loadTradesHistory(); } });
  btnTradesNext.addEventListener("click", () => { tradesPage++; loadTradesHistory(); });

  btnExportCsv.addEventListener("click", exportTradesCSV);

  document.getElementsByName("target-mode").forEach(radio => {
    radio.addEventListener("change", handleTargetModeChange);
  });
  txtConfirm.addEventListener("input", validateLiveConfirm);
  chkOverride.addEventListener("change", validateLiveConfirm);

  // Panel 6 Toggle bindings
  const reportHeader = document.getElementById("panel-report-header");
  const reportContent = document.getElementById("panel-report-content");
  const reportToggle = document.getElementById("report-toggle");

  reportHeader.addEventListener("click", () => {
    const isHidden = reportContent.classList.contains("hidden");
    if (isHidden) {
      reportContent.classList.remove("hidden");
      reportToggle.textContent = "Collapse [-]";
    } else {
      reportContent.classList.add("hidden");
      reportToggle.textContent = "Expand [+]";
    }
  });
});

// Websocket connection loop
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

  ws.onopen = () => {
    isWsOnline = true;
    reconnectInterval = 1000;
    statusConnection.textContent = "Connected";
    statusConnection.className = "text-sm font-semibold text-emerald-400";
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
    loadAllPanelData();
  };

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleWsEvent(payload.type, payload.data);
    } catch (e) {
      console.error("Failed to parse websocket message", e);
    }
  };

  ws.onclose = () => {
    isWsOnline = false;
    statusConnection.textContent = "Disconnected (polling)";
    statusConnection.className = "text-sm font-semibold text-amber-500";
    // Trigger polling fallback loop
    if (!pollingTimer) {
      pollingTimer = setInterval(pollFallback, 10000);
    }
    setTimeout(connectWebSocket, reconnectInterval);
    reconnectInterval = Math.min(reconnectInterval * 2, 30000);
  };
}

// Websocket Events Router
function handleWsEvent(type, data) {
  switch (type) {
    case "tick":
      tickerPrices[data.symbol] = data.price;
      updateLivePnls();
      if (data.symbol === currentChartSymbol && lastCandle) {
        const timeSec = Math.floor(Date.now() / 1000);
        const candleTime = Math.floor(timeSec / 3600) * 3600;
        if (candleTime > lastCandle.time) {
          lastCandle = {
            time: candleTime,
            open: data.price,
            high: data.price,
            low: data.price,
            close: data.price
          };
        } else {
          lastCandle.high = Math.max(lastCandle.high, data.price);
          lastCandle.low = Math.min(lastCandle.low, data.price);
          lastCandle.close = data.price;
        }
        if (candlestickSeries) candlestickSeries.update(lastCandle);
        if (lineSeries) lineSeries.update({ time: lastCandle.time, value: data.price });
      }
      break;
    case "fill":
      loadPositions();
      loadTradesHistory();
      loadStatus();
      loadEquityData();
      loadPriceChartData();
      break;
    case "mode":
      loadAllPanelData();
      break;
    case "killswitch":
      syncKillswitchUI(data.status === "triggered");
      loadStatus();
      break;
    case "equity":
      loadEquityData();
      break;
    case "status":
      updateStatusHeader(data);
      break;
  }
}

// Polling Fallback when Websocket is Offline
function pollFallback() {
  loadStatus();
  loadPositions();
}

function loadAllPanelData() {
  loadStatus();
  loadPositions();
  loadTradesHistory();
  loadSignals();
  loadEquityData();
  loadSystemData();
  loadAIReport();
  loadPriceChartData();
}

// Fetch REST API Data
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    updateStatusHeader(data);
  } catch (e) {
    console.error("Error loading status", e);
  }
}

function updateStatusHeader(data) {
  currentMode = data.mode;
  
  // Format badge
  modeBadge.textContent = currentMode;
  if(data.killswitch) {
    modeBadge.className = "px-3 py-1 text-xs font-bold font-outfit rounded-full uppercase tracking-wider bg-zinc-700 text-zinc-300";
  } else if (currentMode === "live") {
    modeBadge.className = "px-3 py-1 text-xs font-bold font-outfit rounded-full uppercase tracking-wider bg-red-600 text-white animate-pulse neon-glow-red";
  } else {
    modeBadge.className = "px-3 py-1 text-xs font-bold font-outfit rounded-full uppercase tracking-wider bg-blue-600 text-white neon-glow-blue";
  }

  // Update metrics
  headerEquity.textContent = `$${data.equity.toFixed(2)}`;

  // Today PNL
  const pnlTodayStr = `${data.pnl_today >= 0 ? "+" : ""}$${data.pnl_today.toFixed(2)}`;
  headerPnlToday.textContent = pnlTodayStr;
  headerPnlToday.className = data.pnl_today >= 0 ? "text-xl font-bold font-outfit text-emerald-450" : "text-xl font-bold font-outfit text-red-500";

  // Total PNL
  const pnlTotalStr = `${data.pnl_total >= 0 ? "+" : ""}$${data.pnl_total.toFixed(2)}`;
  headerPnlTotal.textContent = pnlTotalStr;
  headerPnlTotal.className = data.pnl_total >= 0 ? "text-xl font-bold font-outfit text-emerald-450" : "text-xl font-bold font-outfit text-red-500";

  // Status variables
  syncKillswitchUI(data.killswitch);
  
  // Pause/Resume Strategy
  if (data.paused) {
    btnPauseResume.textContent = "Resume Strategy";
    btnPauseResume.className = "px-4 py-2 text-sm font-semibold rounded-lg bg-emerald-650 hover:bg-emerald-600 text-white transition-all";
    statusStrategy.textContent = "Paused";
    statusStrategy.className = "text-sm font-semibold text-amber-500";
  } else {
    btnPauseResume.textContent = "Pause Strategy";
    btnPauseResume.className = "px-4 py-2 text-sm font-semibold rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-slate-700 transition-all text-slate-350";
    statusStrategy.textContent = "Running";
    statusStrategy.className = "text-sm font-semibold text-emerald-450";
  }
  btnPauseResume.classList.remove("hidden");

  // Show Reset Paper btn only in paper mode
  if (currentMode === "paper") {
    btnResetPaper.classList.remove("hidden");
  } else {
    btnResetPaper.classList.add("hidden");
  }
}

function syncKillswitchUI(isTriggered) {
  if (isTriggered) {
    killswitchBanner.classList.remove("hidden");
    statusRisk.textContent = "HALTED (Triggered)";
    statusRisk.className = "text-sm font-semibold text-red-500";
    btnRearm.classList.remove("hidden");
    btnExportCsv.disabled = true; // example disable
  } else {
    killswitchBanner.classList.add("hidden");
    statusRisk.textContent = "Armed";
    statusRisk.className = "text-sm font-semibold text-emerald-450";
    btnRearm.classList.add("hidden");
  }
}

async function loadPositions() {
  try {
    const res = await fetch("/api/positions");
    openPositions = await res.json();
    renderPositions();
  } catch (e) {
    console.error("Error loading positions", e);
  }
}

function renderPositions() {
  positionsBody.innerHTML = "";
  if (openPositions.length === 0) {
    positionsEmpty.classList.remove("hidden");
    return;
  }
  positionsEmpty.classList.add("hidden");

  openPositions.forEach(pos => {
    // Cache current price
    const curPrice = tickerPrices[pos.symbol] || pos.current_price;
    const unrealized = pos.qty * (curPrice - pos.entry_price);
    const unrealizedPct = (unrealized / (pos.entry_price * pos.qty)) * 100;

    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="py-3 px-4 font-semibold text-white">${pos.symbol}</td>
      <td class="py-3 px-4 font-bold text-emerald-450 uppercase">${pos.side}</td>
      <td class="py-3 px-4">${pos.qty}</td>
      <td class="py-3 px-4 font-mono">$${pos.entry_price.toFixed(2)}</td>
      <td class="py-3 px-4 font-mono" id="pos-price-${pos.symbol}">$${curPrice.toFixed(2)}</td>
      <td class="py-3 px-4 font-mono text-slate-400">$${pos.stop_price ? pos.stop_price.toFixed(2) : "--"}</td>
      <td class="py-3 px-4 font-mono" id="pos-pnl-${pos.symbol}">
        <span class="${unrealized >= 0 ? 'text-emerald-450' : 'text-red-500'}">
          ${unrealized >= 0 ? "+" : ""}${unrealized.toFixed(2)} (${unrealizedPct.toFixed(2)}%)
        </span>
      </td>
      <td class="py-3 px-4 text-slate-405 text-xs">${new Date(pos.opened_ts).toLocaleString()}</td>
      <td class="py-3 px-4 text-right">
        <button onclick="closePosition(${pos.id})" class="px-2.5 py-1 text-xs font-bold rounded bg-red-950/60 text-red-400 hover:bg-red-900 border border-red-500/20 transition-all font-outfit uppercase">
          Close
        </button>
      </td>
    `;
    positionsBody.appendChild(row);
  });
}

function updateLivePnls() {
  openPositions.forEach(pos => {
    const curPrice = tickerPrices[pos.symbol];
    if (curPrice === undefined) return;

    // Update current price cell
    const priceCell = document.getElementById(`pos-price-${pos.symbol}`);
    if (priceCell) priceCell.textContent = `$${curPrice.toFixed(2)}`;

    // Update PNL cell
    const pnlCell = document.getElementById(`pos-pnl-${pos.symbol}`);
    if (pnlCell) {
      const unrealized = pos.qty * (curPrice - pos.entry_price);
      const unrealizedPct = (unrealized / (pos.entry_price * pos.qty)) * 100;
      pnlCell.innerHTML = `
        <span class="${unrealized >= 0 ? 'text-emerald-450' : 'text-red-500'}">
          ${unrealized >= 0 ? "+" : ""}${unrealized.toFixed(2)} (${unrealizedPct.toFixed(2)}%)
        </span>
      `;
    }
  });
}

async function closePosition(id) {
  if (!confirm("Are you sure you want to close this position?")) return;
  try {
    const res = await fetch(`/api/positions/${id}/close`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json();
      alert(`Close failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Request error closing position: ${e}`);
  }
}

async function loadTradesHistory() {
  try {
    const res = await fetch(`/api/trades?mode=${currentMode}&page=${tradesPage}&page_size=${tradesPageSize}`);
    const data = await res.json();
    renderTradesHistory(data.items, data.total);
  } catch (e) {
    console.error("Error loading trades", e);
  }
}

function renderTradesHistory(items, total) {
  tradesBody.innerHTML = "";
  if (!items || items.length === 0) {
    tradesEmpty.classList.remove("hidden");
    tradesPaginationInfo.textContent = "Showing page 1";
    btnTradesPrev.disabled = true;
    btnTradesNext.disabled = true;
    return;
  }
  tradesEmpty.classList.add("hidden");

  items.forEach(t => {
    const pnl = t.realized_pnl || 0.0;
    const fees = t.fees_total || 0.0;
    
    // Compute duration helper
    let durationStr = "--";
    if (t.opened_ts && t.closed_ts) {
      const ms = new Date(t.closed_ts) - new Date(t.opened_ts);
      const mins = Math.floor(ms / 60000);
      if (mins < 60) {
        durationStr = `${mins}m`;
      } else {
        const hrs = Math.floor(mins / 60);
        durationStr = `${hrs}h ${mins % 60}m`;
      }
    }

    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="py-3 px-4 font-semibold text-white">${t.symbol}</td>
      <td class="py-3 px-4 font-bold text-emerald-450 uppercase">${t.side}</td>
      <td class="py-3 px-4">${t.qty}</td>
      <td class="py-3 px-4 font-mono">$${t.entry_price.toFixed(2)}</td>
      <td class="py-3 px-4 font-mono text-slate-400">$${t.exit_price ? t.exit_price.toFixed(2) : "--"}</td>
      <td class="py-3 px-4 font-mono">
        <span class="${pnl >= 0 ? 'text-emerald-450' : 'text-red-500'}">
          ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
        </span>
      </td>
      <td class="py-3 px-4 font-mono text-slate-500">$${fees.toFixed(2)}</td>
      <td class="py-3 px-4 text-xs font-semibold text-slate-405">${durationStr}</td>
      <td class="py-3 px-4 text-slate-450 font-mono text-xs">${t.strategy}</td>
      <td class="py-3 px-4 uppercase text-xs font-semibold text-slate-450">${t.mode}</td>
      <td class="py-3 px-4 text-xs max-w-xs truncate text-slate-400" title="${t.annotation || ''}">${t.annotation || '--'}</td>
    `;
    tradesBody.appendChild(row);
  });

  const totalPages = Math.ceil(total / tradesPageSize) || 1;
  tradesPaginationInfo.textContent = `Showing page ${tradesPage} of ${totalPages} (Total logs: ${total})`;
  btnTradesPrev.disabled = tradesPage <= 1;
  btnTradesNext.disabled = tradesPage >= totalPages;
}

function exportTradesCSV() {
  window.open(`/api/trades/export.csv?mode=${currentMode}`, "_blank");
}

async function loadSignals() {
  try {
    const res = await fetch("/api/signals?limit=100");
    const data = await res.json();
    renderSignals(data);
  } catch (e) {
    console.error("Error loading signals", e);
  }
}

function renderSignals(items) {
  signalsBody.innerHTML = "";
  if (!items || items.length === 0) {
    signalsEmpty.classList.remove("hidden");
    return;
  }
  signalsEmpty.classList.add("hidden");

  items.forEach(s => {
    const isApproved = s.risk_decision === "approved";
    const highlightRow = s.risk_reason && (s.risk_reason.includes("KILLSWITCH") || s.risk_reason.includes("WATCHDOG"));
    
    const row = document.createElement("tr");
    if (highlightRow) {
      row.className = "bg-red-950/20";
    }
    
    row.innerHTML = `
      <td class="py-2.5 px-4 text-slate-500 text-xs">${new Date(s.ts).toLocaleString()}</td>
      <td class="py-2.5 px-4 font-bold text-white">${s.symbol}</td>
      <td class="py-2.5 px-4 uppercase font-semibold text-xs text-slate-350">${s.side}</td>
      <td class="py-2.5 px-4">
        <span class="px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-wider ${isApproved ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/20' : 'bg-red-950 text-red-400 border border-red-500/20'}">
          ${s.risk_decision}
        </span>
      </td>
      <td class="py-2.5 px-4 text-xs font-semibold ${isApproved ? 'text-slate-400' : 'text-red-400'}">${s.risk_reason || "--"}</td>
    `;
    signalsBody.appendChild(row);
  });
}

// Chart.js Panel 1 Integration
function initChart() {
  const ctx = document.getElementById("equity-chart").getContext("2d");
  
  // Custom dark theme gradients
  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, "rgba(59, 130, 246, 0.35)");
  gradient.addColorStop(1, "rgba(59, 130, 246, 0)");

  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Account Equity",
        data: [],
        borderColor: "#3b82f6",
        borderWidth: 2,
        fill: true,
        backgroundColor: gradient,
        tension: 0.15,
        pointBackgroundColor: "#1e40af",
        pointBorderColor: "#60a5fa",
        pointHoverRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0f172a",
          titleColor: "#94a3b8",
          bodyColor: "#f8fafc",
          borderColor: "rgba(255,255,255,0.08)",
          borderWidth: 1,
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#475569", maxTicksLimit: 8, font: { size: 10 } }
        },
        y: {
          grid: { color: "rgba(71, 85, 105, 0.08)" },
          ticks: { color: "#475569", font: { size: 10 } }
        }
      }
    }
  });
}

async function loadEquityData() {
  if (!equityChart) return;
  try {
    const res = await fetch(`/api/equity?range=${currentRange}`);
    const data = await res.json();
    
    // Sort chronological just in case
    data.sort((a,b) => new Date(a.ts) - new Date(b.ts));

    const labels = data.map(item => new Date(item.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const values = data.map(item => item.equity);

    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = values;
    equityChart.update();
  } catch (e) {
    console.error("Error loading equity data", e);
  }
}

// System Details Panel 5
async function loadSystemData() {
  try {
    const res = await fetch("/api/system");
    const data = await res.json();

    // Ollama connection indicator
    statusOllama.textContent = data.ollama_ok ? "Online" : "Offline";
    statusOllama.className = data.ollama_ok ? "text-sm font-semibold text-emerald-450" : "text-sm font-semibold text-red-500";

    // Uptime formatter
    let seconds = data.uptime_sec || 0;
    const days = Math.floor(seconds / 86400); seconds %= 86400;
    const hrs = Math.floor(seconds / 3600); seconds %= 3600;
    const mins = Math.floor(seconds / 60);
    statusUptime.textContent = `${days > 0 ? days + "d " : ""}${hrs}h ${mins}m`;

    // Feed Delays Table Layout
    statusFeedDelays.innerHTML = "";
    if (!data.feeds || data.feeds.length === 0) {
      statusFeedDelays.textContent = "No active ticker feeds.";
      return;
    }
    data.feeds.forEach(f => {
      const div = document.createElement("div");
      div.className = "flex items-center justify-between";
      
      const isStale = f.delay_sec > 300; // max stale limit check
      div.innerHTML = `
        <span>${f.symbol}</span>
        <span class="${isStale ? 'text-red-500 font-semibold' : 'text-slate-400 font-mono'}">
          ${f.delay_sec < 0 ? '--' : f.delay_sec.toFixed(1) + 's'}
        </span>
      `;
      statusFeedDelays.appendChild(div);
    });
  } catch (e) {
    console.error("Error loading system status data", e);
  }
}

// Pause/Resume Strategy execution flow
async function toggleStrategyState() {
  const isPauseAction = btnPauseResume.textContent.includes("Pause");
  const path = isPauseAction ? "/api/strategy/pause" : "/api/strategy/resume";
  try {
    const res = await fetch(path, { method: "POST" });
    const data = await res.json();
    loadStatus();
  } catch (e) {
    alert(`Pause/Resume request failed: ${e}`);
  }
}

// Manual trigger Killswitch logic
async function triggerKillswitch() {
  if (!confirm("CRITICAL WARNING: This will flatten all open positions and lock strategy executions. Proceeed?")) return;
  try {
    const res = await fetch("/api/killswitch", { method: "POST" });
    if (res.ok) {
      loadStatus();
      loadPositions();
    } else {
      alert("Trigger failed.");
    }
  } catch (e) {
    alert(`Trigger error: ${e}`);
  }
}

// Rearm workflow modal
function openRearmModal() {
  txtRearmConfirm.value = "";
  btnRearmSubmit.disabled = true;
  modalRearm.classList.remove("hidden");
}
function checkRearmConfirm() {
  btnRearmSubmit.disabled = txtRearmConfirm.value.trim() !== "RE-ARM";
}
async function submitRearm() {
  try {
    const res = await fetch("/api/killswitch/rearm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation: "RE-ARM" })
    });
    if (res.ok) {
      modalRearm.classList.add("hidden");
      loadStatus();
    } else {
      const data = await res.json();
      alert(`Re-arm failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Request error: ${e}`);
  }
}

// Mode Switch modal configuration
function openModeSwitchModal() {
  document.getElementsByName("target-mode").forEach(radio => {
    if (radio.value === currentMode) {
      radio.checked = true;
    }
  });
  txtConfirm.value = "";
  chkOverride.checked = false;
  
  handleTargetModeChange();
  modalModeSwitch.classList.remove("hidden");
}

async function handleTargetModeChange() {
  const targetRadio = document.querySelector('input[name="target-mode"]:checked');
  const target = targetRadio ? targetRadio.value : "paper";

  if (target === "live") {
    preflightBox.classList.remove("hidden");
    confirmationInputBox.classList.remove("hidden");
    preflightList.innerHTML = "Checking preflight interlocks...";
    btnModalConfirm.disabled = true;

    // Load preflight checks status from API
    try {
      const res = await fetch("/api/mode/preflight");
      const data = await res.json();
      renderPreflight(data);
    } catch (e) {
      preflightList.innerHTML = `<span class="text-red-500">Error loading preflight data: ${e}</span>`;
    }
  } else {
    // Paper switch has no checkpoints
    preflightBox.classList.add("hidden");
    confirmationInputBox.classList.add("hidden");
    overrideBox.classList.add("hidden");
    btnModalConfirm.disabled = false;
  }
}

function renderPreflight(preflight) {
  preflightList.innerHTML = "";
  let hasKeyHistoryFail = false;
  
  preflight.checks.forEach(chk => {
    const div = document.createElement("div");
    div.className = "flex items-center justify-between";
    const okIcon = chk.ok ? `<span class="text-emerald-400">✓</span>` : `<span class="text-red-500">✗</span>`;
    div.innerHTML = `
      <span>${chk.name}</span>
      <span>${okIcon} ${chk.detail ? '<span class="text-slate-500">(' + chk.detail + ')</span>' : ''}</span>
    `;
    preflightList.appendChild(div);

    if (!chk.ok && chk.name.includes("history")) {
      hasKeyHistoryFail = true;
    }
  });

  // Check checklist features
  if (hasKeyHistoryFail) {
    overrideBox.classList.remove("hidden");
  } else {
    overrideBox.classList.add("hidden");
  }

  validateLiveConfirm(preflight);
}

function validateLiveConfirm(preflightSource) {
  const targetRadio = document.querySelector('input[name="target-mode"]:checked');
  const target = targetRadio ? targetRadio.value : "paper";
  if (target === "paper") {
    btnModalConfirm.disabled = false;
    return;
  }

  const confirmTextNormalized = txtConfirm.value.trim();
  const isTextMatch = confirmTextNormalized === "GO-LIVE";
  
  // We can either query the preflight state or check inputs
  const checksDivs = preflightList.querySelectorAll("span");
  let allPass = true;
  let historyFailed = false;

  // Simple query state or rely on DOM icon checks
  if (preflightList.innerHTML.includes("✗")) {
    allPass = false;
  }
  // Check override condition
  const isOverrideChecked = chkOverride.checked;
  
  // If only history check fails and override is checked, allow it
  const allowSwitch = isTextMatch && (allPass || (isOverrideChecked && !preflightList.innerHTML.replace("history", "").includes("✗")));
  btnModalConfirm.disabled = !allowSwitch;
}

// Request mode change submit on API
btnModalConfirm.addEventListener("click", async () => {
  const target = document.querySelector('input[name="target-mode"]:checked').value;
  const confirmText = txtConfirm.value;
  const isOverride = chkOverride.checked;

  try {
    const res = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: target,
        confirmation: confirmText,
        override: isOverride
      })
    });
    
    if (res.ok) {
      modalModeSwitch.classList.add("hidden");
      loadAllPanelData();
    } else {
      const data = await res.json();
      alert(`Model Switch Rejected: ${data.error}`);
    }
  } catch (e) {
    alert(`Network request error during mode transition: ${e}`);
  }
});

// Reset paper table values
async function resetPaperAccount() {
  if (!confirm("Are you sure you want to completely reset all paper positions, paper trades, paper equity snapshots, and set balance to the starting default?")) return;
  try {
    const res = await fetch("/api/paper/reset", { method: "POST" });
    if (res.ok) {
      loadAllPanelData();
      alert("Paper account reset successful.");
    } else {
      const data = await res.json();
      alert(`Reset failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Reset request error: ${e}`);
  }
}

// Fetch latest daily AI report
async function loadAIReport() {
  try {
    const res = await fetch("/api/report/latest");
    const data = await res.json();
    const tsEl = document.getElementById("report-timestamp");
    const textEl = document.getElementById("report-text");
    
    if (data && data.ts) {
      tsEl.textContent = `Report generated at: ${new Date(data.ts).toLocaleString()}`;
      textEl.textContent = data.text;
    } else {
      tsEl.textContent = "Report generated at: --";
      textEl.textContent = data.text || "No daily report generated yet.";
    }
  } catch (e) {
    console.error("Error loading daily report", e);
  }
}


function initPriceChart() {
  const container = document.getElementById("price-chart-container");
  if (!container) return;

  container.innerHTML = "";

  priceChart = LightweightCharts.createChart(container, {
    layout: {
      background: { type: 'solid', color: 'rgba(15, 23, 42, 0.45)' },
      textColor: '#94a3b8',
    },
    grid: {
      vertLines: { color: 'rgba(148, 163, 184, 0.05)' },
      horzLines: { color: 'rgba(148, 163, 184, 0.05)' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    timeScale: {
      borderColor: 'rgba(148, 163, 184, 0.1)',
      timeVisible: true,
      secondsVisible: false,
    },
  });

  // v5 API: addCandlestickSeries/addLineSeries were removed in favor of
  // addSeries(SeriesType, options).
  candlestickSeries = priceChart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#10b981',
    downColor: '#ef4444',
    borderVisible: false,
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444',
  });

  lineSeries = priceChart.addSeries(LightweightCharts.LineSeries, {
    color: '#3b82f6',
    lineWidth: 2,
  });

  // v5 API: series.setMarkers() was replaced by the createSeriesMarkers primitive.
  candleMarkersPrimitive = LightweightCharts.createSeriesMarkers(candlestickSeries, []);
  lineMarkersPrimitive = LightweightCharts.createSeriesMarkers(lineSeries, []);

  const resizeObserver = new ResizeObserver(entries => {
    if (entries.length === 0 || !entries[0].contentRect) return;
    const { width, height } = entries[0].contentRect;
    priceChart.resize(width, height);
  });
  resizeObserver.observe(container);

  const symbolSelector = document.getElementById("price-chart-symbol");
  if (symbolSelector) {
    symbolSelector.addEventListener("change", (e) => {
      currentChartSymbol = e.target.value;
      loadPriceChartData();
    });
  }

  const btnCandle = document.getElementById("btn-chart-view-candle");
  const btnLine = document.getElementById("btn-chart-view-line");

  if (btnCandle && btnLine) {
    btnCandle.addEventListener("click", () => {
      btnCandle.classList.add("bg-blue-600", "text-white");
      btnCandle.classList.remove("text-slate-400");
      btnLine.classList.remove("bg-blue-600", "text-white");
      btnLine.classList.add("text-slate-400");
      currentChartView = "candle";
      toggleSeriesVisibility();
    });

    btnLine.addEventListener("click", () => {
      btnLine.classList.add("bg-blue-600", "text-white");
      btnLine.classList.remove("text-slate-400");
      btnCandle.classList.remove("bg-blue-600", "text-white");
      btnCandle.classList.add("text-slate-400");
      currentChartView = "line";
      toggleSeriesVisibility();
    });
  }

  document.querySelectorAll(".btn-chart-range").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".btn-chart-range").forEach(b => b.classList.remove("bg-blue-600", "text-white"));
      e.target.classList.add("bg-blue-600", "text-white");
      currentChartRange = e.target.getAttribute("data-chart-range");
      loadPriceChartData();
    });
  });
}

function toggleSeriesVisibility() {
  if (currentChartView === "candle") {
    candlestickSeries.applyOptions({ visible: true });
    lineSeries.applyOptions({ visible: false });
  } else {
    candlestickSeries.applyOptions({ visible: false });
    lineSeries.applyOptions({ visible: true });
  }
}

async function loadPriceChartData() {
  if (!priceChart) return;
  try {
    const resCandles = await fetch(`/api/candles?symbol=${encodeURIComponent(currentChartSymbol)}&range=${currentChartRange}&timeframe=1h`);
    const candles = await resCandles.json();

    if (candles.length > 0) {
      candles.sort((a, b) => a.time - b.time);
      candlestickSeries.setData(candles);

      const lineData = candles.map(c => ({ time: c.time, value: c.close }));
      lineSeries.setData(lineData);

      lastCandle = candles[candles.length - 1];
    } else {
      candlestickSeries.setData([]);
      lineSeries.setData([]);
      lastCandle = null;
    }

    const resMarkers = await fetch(`/api/trades/markers?symbol=${encodeURIComponent(currentChartSymbol)}&mode=${currentMode}`);
    const markers = await resMarkers.json();

    const chartMarkers = [];
    markers.forEach(m => {
      chartMarkers.push({
        time: m.time,
        position: m.side === "buy" ? "belowBar" : "aboveBar",
        color: m.side === "buy" ? "#10b981" : "#ef4444",
        shape: m.side === "buy" ? "arrowUp" : "arrowDown",
        text: m.side === "buy" ? "Buy" : "Sell",
      });
    });

    candleMarkersPrimitive.setMarkers(chartMarkers);
    lineMarkersPrimitive.setMarkers(chartMarkers);

    toggleSeriesVisibility();
    priceChart.timeScale().fitContent();
  } catch (e) {
    console.error("Error loading price chart data", e);
  }
}
