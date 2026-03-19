"""
Serveur API d'O.R.I.O.N.

Interface web REST + WebSocket pour accéder à l'intelligence systémique.
Comme Aladdin chez BlackRock, mais à ton échelle — RedRock Capital.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from orion.core.config import OrionConfig
from orion.core.engine import OrionEngine
from orion.data.engine import DataEngine
from orion.data.providers import YahooFinanceProvider, FREDProvider, ECBProvider
from orion.risk.engine import RiskEngine
from orion.macro.engine import MacroEngine
from orion.allocation.engine import AllocationEngine
from orion.volatility.engine import VolatilityEngine
from orion.volatility.models import VolatilityModel
from orion.execution.engine import ExecutionEngine, OrderSide
from orion.signals.generator import SignalGenerator
from orion.utils.logging import setup_logging

logger = logging.getLogger("orion.server")

# ─── État global du serveur ─────────────────────────────────────────────

engine: OrionEngine | None = None
execution: ExecutionEngine | None = None
signal_gen: SignalGenerator | None = None
macro_engine: MacroEngine | None = None
risk_engine: RiskEngine | None = None
vol_engine: VolatilityEngine | None = None
alloc_engine: AllocationEngine | None = None

connected_clients: list[WebSocket] = []
auto_cycle_task: asyncio.Task | None = None
cycle_interval: int = 10  # secondes entre les cycles auto

# Données simulées pour le mode paper trading
simulated_prices: dict[str, float] = {}
price_history: dict[str, list[dict[str, Any]]] = {}


def _init_simulated_prices(config: OrionConfig) -> None:
    """Initialise des prix simulés réalistes pour le paper trading."""
    base_prices = {
        # Forex
        "EUR/USD": 1.0850, "GBP/USD": 1.2650, "USD/JPY": 150.20,
        "USD/CHF": 0.8820, "AUD/USD": 0.6520, "USD/CAD": 1.3580,
        "NZD/USD": 0.6080, "EUR/GBP": 0.8580, "EUR/JPY": 163.00,
        "GBP/JPY": 190.00,
        # Equity indices
        "SPX": 5250.0, "NDX": 18500.0, "DJIA": 39800.0,
        "DAX": 18200.0, "FTSE100": 7850.0, "CAC40": 8100.0,
        "NIKKEI225": 40200.0, "HSI": 17500.0, "STOXX600": 510.0,
        # Fixed income (yield %)
        "US10Y": 4.25, "US2Y": 4.60, "DE10Y": 2.35,
        "JP10Y": 0.85, "GB10Y": 4.10, "US30Y": 4.45, "TIPS10Y": 2.10,
        # Commodities
        "GOLD": 2340.0, "SILVER": 28.50, "WTI": 78.50,
        "BRENT": 82.30, "NATGAS": 2.15, "COPPER": 4.25,
        "WHEAT": 580.0, "CORN": 445.0,
        # Crypto
        "BTC/USD": 68500.0, "ETH/USD": 3550.0, "SOL/USD": 145.0,
        # Volatility
        "VIX": 14.5, "VSTOXX": 15.2, "VDAX": 14.8, "MOVE": 95.0,
    }
    simulated_prices.update(base_prices)
    for symbol, price in base_prices.items():
        price_history[symbol] = [{"time": time.time(), "price": price}]


def _tick_prices() -> None:
    """Simule un tick de prix (random walk)."""
    for symbol in simulated_prices:
        price = simulated_prices[symbol]
        # Volatilité adaptée par asset class
        if "/" in symbol and "BTC" not in symbol and "ETH" not in symbol and "SOL" not in symbol:
            vol = 0.0002  # Forex
        elif symbol in ("VIX", "VSTOXX", "VDAX", "MOVE"):
            vol = 0.005  # Vol indices
        elif "BTC" in symbol or "ETH" in symbol or "SOL" in symbol:
            vol = 0.003  # Crypto
        elif symbol.endswith("Y"):
            vol = 0.001  # Bonds
        else:
            vol = 0.001  # Equities & commodities

        change = random.gauss(0, vol)
        new_price = price * (1 + change)
        simulated_prices[symbol] = round(new_price, 4)

        if symbol not in price_history:
            price_history[symbol] = []
        price_history[symbol].append({"time": time.time(), "price": new_price})
        # Garder 500 points max
        if len(price_history[symbol]) > 500:
            price_history[symbol] = price_history[symbol][-500:]


def _generate_returns(symbol: str, n: int = 252) -> list[float]:
    """Génère des rendements simulés pour un symbole."""
    history = price_history.get(symbol, [])
    if len(history) >= 2:
        returns = []
        for i in range(1, len(history)):
            prev = history[i - 1]["price"]
            curr = history[i]["price"]
            if prev > 0:
                returns.append(math.log(curr / prev))
        return returns[-n:]

    # Rendements synthétiques si pas assez d'historique
    random.seed(hash(symbol) % 2**32)
    base_vol = 0.01
    return [random.gauss(0.0002, base_vol) for _ in range(n)]


def _run_orion_cycle() -> dict[str, Any]:
    """Exécute un cycle complet O.R.I.O.N."""
    global engine, execution, signal_gen, macro_engine, risk_engine, vol_engine, alloc_engine

    _tick_prices()

    # 1. Macro analysis
    macro_result = macro_engine.run_cycle()
    regime = macro_engine.get_regime()

    # 2. Volatility analysis
    for symbol in simulated_prices:
        returns = _generate_returns(symbol)
        vol_engine.update_returns(symbol, returns)
    vol_result = vol_engine.run_cycle()
    volatilities = vol_engine.get_volatilities()

    # 3. Risk analysis
    for symbol in simulated_prices:
        returns = _generate_returns(symbol)
        risk_engine.update_returns(symbol, returns)
    if alloc_engine.get_current_allocation():
        weights = alloc_engine.get_current_allocation().weights
        risk_engine.update_portfolio(weights, execution._portfolio_value)
    risk_result = risk_engine.run_cycle()

    # 4. Allocation
    if regime:
        alloc_engine.update_regime_profile(macro_engine.get_asset_profile())
    alloc_engine.update_volatilities(volatilities)
    alloc_result = alloc_engine.run_cycle()

    # 5. Signals
    cycle_score = macro_result.get("cycle", {}).get("composite_score", 0.0)
    assets = list(simulated_prices.keys())

    # Compute macro scores per asset from regime profile
    macro_scores = {}
    regime_profile = macro_engine.get_asset_profile()
    for asset in assets:
        asset_class = _classify_asset_simple(asset)
        macro_scores[asset] = regime_profile.get(asset_class, 0.0) * 2 - 0.5

    # Volatility scores (inversé — haute vol = signal négatif)
    vol_scores = {}
    for asset in assets:
        snap = vol_engine.get_snapshot(asset)
        if snap:
            vol_scores[asset] = max(-1, min(1, 0.5 - snap.percentile))
        else:
            vol_scores[asset] = 0.0

    signals = signal_gen.generate_all(
        assets, macro_scores=macro_scores,
        volatility_scores=vol_scores, cycle_score=cycle_score,
    )

    # 6. Execution
    signal_data = {sym: sig.to_dict() | {"price": simulated_prices.get(sym, 100)} for sym, sig in signals.items()}
    new_orders = execution.process_signals(signal_data)

    # Check SL/TP
    sl_tp_orders = execution.check_stop_loss_take_profit(simulated_prices)

    # Update position PnLs
    for sym, pos in execution.get_positions().items():
        if sym in simulated_prices:
            pos.update_pnl(simulated_prices[sym])

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prices": dict(simulated_prices),
        "macro": macro_result,
        "volatility": vol_result,
        "risk": risk_result,
        "allocation": alloc_result,
        "signals": {sym: sig.to_dict() for sym, sig in signals.items()},
        "execution": execution.get_dashboard_data(),
        "new_orders": [o.to_dict() for o in new_orders + sl_tp_orders],
    }


def _classify_asset_simple(symbol: str) -> str:
    s = symbol.upper()
    if any(x in s for x in ["EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]) and "/" in s and "BTC" not in s:
        return "forex_carry"
    if any(x in s for x in ["SPX", "NDX", "DJIA", "DAX", "FTSE", "CAC", "NIKKEI", "HSI", "STOXX"]):
        return "equity"
    if any(x in s for x in ["10Y", "2Y", "30Y", "TIPS"]):
        return "fixed_income"
    if any(x in s for x in ["GOLD", "SILVER", "WTI", "BRENT", "NATGAS", "COPPER", "WHEAT", "CORN"]):
        return "commodity"
    if any(x in s for x in ["BTC", "ETH", "SOL"]):
        return "crypto"
    if any(x in s for x in ["VIX", "VSTOXX", "VDAX", "MOVE"]):
        return "volatility_long"
    return "equity"


# ─── Application FastAPI ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise O.R.I.O.N. au démarrage du serveur."""
    global engine, execution, signal_gen, macro_engine, risk_engine, vol_engine, alloc_engine

    setup_logging("INFO")
    logger.info("Démarrage du serveur O.R.I.O.N....")

    config_path = Path(__file__).parent.parent / "orion.config.json"
    if config_path.exists():
        config = OrionConfig.from_file(config_path)
    else:
        config = OrionConfig()

    # Build O.R.I.O.N.
    engine = OrionEngine(config)

    data_eng = DataEngine(config, engine.event_bus)
    data_eng.register_provider(YahooFinanceProvider())
    data_eng.register_provider(FREDProvider())
    data_eng.register_provider(ECBProvider())
    engine.register_engine(data_eng)

    macro_engine = MacroEngine(config, engine.event_bus)
    engine.register_engine(macro_engine)

    vol_engine = VolatilityEngine(config, engine.event_bus)
    engine.register_engine(vol_engine)

    risk_engine = RiskEngine(config, engine.event_bus)
    engine.register_engine(risk_engine)

    alloc_engine = AllocationEngine(config, engine.event_bus)
    engine.register_engine(alloc_engine)

    execution = ExecutionEngine(config, engine.event_bus)
    engine.register_engine(execution)

    signal_gen = SignalGenerator()

    engine.initialize()
    _init_simulated_prices(config)

    # Seed some macro data
    macro_engine.update_indicator("yield_curve_slope", 0.35)
    macro_engine.update_indicator("pmi_manufacturing", 52.1)
    macro_engine.update_indicator("gdp_growth", 2.4)
    macro_engine.update_indicator("cpi_inflation", 3.2)
    macro_engine.update_indicator("unemployment_rate", 3.8)
    macro_engine.update_indicator("fed_funds_rate", 5.25)
    macro_engine.update_indicator("consumer_expectations", 67.5)

    logger.info("O.R.I.O.N. opérationnel — accès via navigateur")

    yield

    engine.shutdown()
    logger.info("Serveur O.R.I.O.N. arrêté")


app = FastAPI(
    title="O.R.I.O.N. — RedRock Capital",
    description="Intelligence Systémique Intégrée",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── Routes API ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Sert le dashboard principal."""
    html_path = static_dir / "index.html"
    return FileResponse(html_path)


@app.get("/api/status")
async def get_status():
    """État du système O.R.I.O.N."""
    return engine.get_status() if engine else {"error": "Engine not initialized"}


@app.get("/api/cycle")
async def run_cycle():
    """Exécute un cycle d'analyse et retourne les résultats."""
    return _run_orion_cycle()


@app.get("/api/prices")
async def get_prices():
    """Prix courants de tous les actifs."""
    return {"prices": simulated_prices, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/prices/{symbol}")
async def get_price_history(symbol: str):
    """Historique de prix d'un actif."""
    symbol = symbol.replace("-", "/")
    history = price_history.get(symbol, [])
    return {"symbol": symbol, "history": history[-100:]}


@app.get("/api/portfolio")
async def get_portfolio():
    """État du portefeuille."""
    if not execution:
        return {"error": "Execution engine not ready"}
    return execution.get_dashboard_data()


@app.get("/api/signals")
async def get_signals():
    """Derniers signaux générés."""
    if not signal_gen:
        return {"signals": {}}
    top = signal_gen.get_top_signals(20)
    bottom = signal_gen.get_bottom_signals(20)
    return {
        "top": [s.to_dict() for s in top],
        "bottom": [s.to_dict() for s in bottom],
    }


@app.get("/api/macro")
async def get_macro():
    """État macro-économique."""
    if not macro_engine:
        return {}
    regime = macro_engine.get_regime()
    cycle = macro_engine.get_cycle_snapshot()
    return {
        "regime": regime.to_dict() if regime else None,
        "cycle": cycle.to_dict() if cycle else None,
        "signals": macro_engine.get_all_signals(),
        "asset_profile": macro_engine.get_asset_profile(),
    }


@app.get("/api/risk")
async def get_risk():
    """Métriques de risque."""
    if not risk_engine:
        return {}
    metrics = risk_engine.get_metrics()
    return {
        "metrics": metrics.to_dict(),
        "stress_tests": risk_engine.run_stress_tests(execution._portfolio_value if execution else 100000),
    }


@app.get("/api/allocation")
async def get_allocation():
    """Allocation courante."""
    if not alloc_engine:
        return {}
    alloc = alloc_engine.get_current_allocation()
    return alloc.to_dict() if alloc else {"weights": {}, "method": "none"}


@app.post("/api/auto-trade/{action}")
async def toggle_auto_trade(action: str):
    """Active/désactive le trading automatique."""
    if not execution:
        return {"error": "Execution engine not ready"}
    if action == "start":
        execution.auto_trade = True
        return {"auto_trade": True, "message": "Trading automatique activé"}
    elif action == "stop":
        execution.auto_trade = False
        return {"auto_trade": False, "message": "Trading automatique désactivé"}
    return {"error": f"Action inconnue: {action}"}


@app.post("/api/close-position/{symbol}")
async def close_position(symbol: str):
    """Ferme manuellement une position."""
    symbol = symbol.replace("-", "/")
    if not execution:
        return {"error": "Execution engine not ready"}
    price = simulated_prices.get(symbol, 0)
    order = execution._close_position(symbol, price)
    if order:
        return {"success": True, "order": order.to_dict()}
    return {"error": f"Pas de position ouverte sur {symbol}"}


@app.post("/api/capital/{amount}")
async def set_capital(amount: float):
    """Définit le capital initial."""
    if not execution:
        return {"error": "Execution engine not ready"}
    execution.set_capital(amount)
    return {"capital": amount}


# ─── WebSocket pour temps réel ──────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket pour les mises à jour en temps réel."""
    await ws.accept()
    connected_clients.append(ws)
    logger.info("Client WebSocket connecté (%d total)", len(connected_clients))

    try:
        while True:
            # Recevoir les commandes du client
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=cycle_interval)
                msg = json.loads(data)
                cmd = msg.get("command")

                if cmd == "toggle_auto_trade":
                    execution.auto_trade = not execution.auto_trade
                elif cmd == "run_cycle":
                    pass  # Le cycle tourne en continu
                elif cmd == "close_position":
                    symbol = msg.get("symbol", "")
                    price = simulated_prices.get(symbol, 0)
                    execution._close_position(symbol, price)
            except asyncio.TimeoutError:
                pass

            # Exécuter un cycle et envoyer les résultats
            try:
                result = _run_orion_cycle()
                await ws.send_text(json.dumps(result, default=str))
            except Exception as e:
                logger.error("Erreur cycle WebSocket: %s", e)

    except WebSocketDisconnect:
        connected_clients.remove(ws)
        logger.info("Client WebSocket déconnecté (%d restants)", len(connected_clients))
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


# ─── Point d'entrée ────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Démarre le serveur O.R.I.O.N."""
    import uvicorn
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║     O.R.I.O.N. — RedRock Capital                     ║
    ║     Intelligence Systémique Intégrée                 ║
    ║                                                      ║
    ║     Dashboard: http://{host}:{port}                    ║
    ║     API:       http://{host}:{port}/api/status          ║
    ║     WebSocket: ws://{host}:{port}/ws                    ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
