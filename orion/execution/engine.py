"""
Moteur d'exécution d'O.R.I.O.N.

Gère l'exécution automatique des ordres basés sur les signaux,
le suivi des positions, et le journal de trading.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from orion.core.config import OrionConfig
from orion.core.engine import BaseEngine
from orion.core.events import Event, EventBus, EventType

logger = logging.getLogger("orion.execution")


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Order:
    """Ordre de trading."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    signal_score: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fill_price: float = 0.0
    fill_timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value,
            "signal_score": self.signal_score,
            "timestamp": self.timestamp.isoformat(),
            "fill_price": self.fill_price,
            "fill_timestamp": self.fill_timestamp.isoformat() if self.fill_timestamp else None,
        }


@dataclass
class Position:
    """Position ouverte."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: PositionStatus = PositionStatus.OPEN
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0

    def update_pnl(self, current_price: float) -> None:
        self.current_price = current_price
        if self.side == OrderSide.BUY:
            self.pnl = (current_price - self.entry_price) * self.quantity
            self.pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 if self.entry_price else 0
        else:
            self.pnl = (self.entry_price - current_price) * self.quantity
            self.pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 if self.entry_price else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "entry_time": self.entry_time.isoformat(),
            "status": self.status.value,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 4),
        }


@dataclass
class TradeRecord:
    """Enregistrement d'un trade clôturé."""
    id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pnl: float = 0.0
    pnl_pct: float = 0.0
    signal_score: float = 0.0
    duration_hours: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 4),
            "signal_score": self.signal_score,
            "duration_hours": round(self.duration_hours, 1),
        }


class ExecutionEngine(BaseEngine):
    """
    Moteur d'exécution — Le bras armé d'O.R.I.O.N.

    Traduit les signaux en ordres, gère les positions ouvertes,
    applique les stop-loss/take-profit, et maintient le journal de trading.
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("execution", config, event_bus)
        self._orders: list[Order] = []
        self._positions: dict[str, Position] = {}
        self._trade_history: list[TradeRecord] = []
        self._portfolio_value: float = 100_000.0  # Capital initial
        self._cash: float = 100_000.0
        self._auto_trade: bool = False
        self._min_signal_strength: float = 0.3
        self._max_position_size_pct: float = 0.05
        self._default_stop_loss_pct: float = 0.02
        self._default_take_profit_pct: float = 0.04

    def initialize(self) -> None:
        self.logger.info(
            "Execution Engine initialisé — Capital: $%.2f, Auto-trade: %s",
            self._portfolio_value, self._auto_trade,
        )

    @property
    def auto_trade(self) -> bool:
        return self._auto_trade

    @auto_trade.setter
    def auto_trade(self, value: bool) -> None:
        self._auto_trade = value
        self.logger.info("Auto-trade %s", "activé" if value else "désactivé")

    def process_signals(self, signals: dict[str, dict[str, Any]]) -> list[Order]:
        """
        Traite les signaux et génère des ordres si auto_trade est actif.
        """
        if not self._auto_trade:
            return []

        orders = []
        for symbol, signal_data in signals.items():
            score = signal_data.get("score", 0.0)
            signal_type = signal_data.get("type", "neutral")

            # Ignorer les signaux faibles
            if abs(score) < self._min_signal_strength:
                continue

            # Vérifier si on a déjà une position
            if symbol in self._positions:
                pos = self._positions[symbol]
                # Signal inversé → fermer la position
                if (pos.side == OrderSide.BUY and score < -self._min_signal_strength) or \
                   (pos.side == OrderSide.SELL and score > self._min_signal_strength):
                    close_order = self._close_position(symbol)
                    if close_order:
                        orders.append(close_order)
                continue

            # Nouveau signal → ouvrir une position
            if signal_type in ("overweight", "underweight"):
                order = self._create_order_from_signal(symbol, score, signal_data)
                if order:
                    orders.append(order)

        return orders

    def _create_order_from_signal(
        self, symbol: str, score: float, signal_data: dict[str, Any]
    ) -> Order | None:
        """Crée un ordre basé sur un signal."""
        side = OrderSide.BUY if score > 0 else OrderSide.SELL
        # Position size basée sur la force du signal et le max
        size_pct = min(abs(score) * self._max_position_size_pct, self._max_position_size_pct)
        position_value = self._portfolio_value * size_pct

        # Prix simulé (en production, vient du feed de prix)
        price = signal_data.get("price", 100.0)
        quantity = position_value / price if price > 0 else 0

        if quantity <= 0:
            return None

        order = Order(
            symbol=symbol,
            side=side,
            quantity=round(quantity, 4),
            price=price,
            signal_score=score,
        )

        # Simuler le fill immédiat (mode paper)
        order.status = OrderStatus.FILLED
        order.fill_price = price
        order.fill_timestamp = datetime.now(timezone.utc)
        self._orders.append(order)

        # Créer la position
        stop_loss = price * (1 - self._default_stop_loss_pct) if side == OrderSide.BUY else price * (1 + self._default_stop_loss_pct)
        take_profit = price * (1 + self._default_take_profit_pct) if side == OrderSide.BUY else price * (1 - self._default_take_profit_pct)

        position = Position(
            symbol=symbol,
            side=side,
            quantity=order.quantity,
            entry_price=price,
            current_price=price,
            stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4),
        )
        self._positions[symbol] = position
        self._cash -= position_value

        self.logger.info(
            "ORDRE %s %s %.4f @ %.4f (signal: %.2f, SL: %.4f, TP: %.4f)",
            side.value.upper(), symbol, order.quantity, price,
            score, stop_loss, take_profit,
        )

        return order

    def _close_position(self, symbol: str, exit_price: float | None = None) -> Order | None:
        """Ferme une position."""
        if symbol not in self._positions:
            return None

        pos = self._positions[symbol]
        price = exit_price or pos.current_price

        # Créer l'ordre de fermeture
        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
        order = Order(
            symbol=symbol,
            side=close_side,
            quantity=pos.quantity,
            price=price,
            status=OrderStatus.FILLED,
            fill_price=price,
            fill_timestamp=datetime.now(timezone.utc),
        )
        self._orders.append(order)

        # Calculer PnL final
        pos.update_pnl(price)

        # Enregistrer dans l'historique
        now = datetime.now(timezone.utc)
        duration = (now - pos.entry_time).total_seconds() / 3600

        record = TradeRecord(
            id=pos.id,
            symbol=symbol,
            side=pos.side.value,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=price,
            entry_time=pos.entry_time,
            exit_time=now,
            pnl=pos.pnl,
            pnl_pct=pos.pnl_pct,
            duration_hours=duration,
        )
        self._trade_history.append(record)

        # Libérer le cash
        self._cash += pos.quantity * price
        self._portfolio_value += pos.pnl

        self.logger.info(
            "FERMETURE %s — PnL: $%.2f (%.2f%%)",
            symbol, pos.pnl, pos.pnl_pct,
        )

        # Retirer la position
        pos.status = PositionStatus.CLOSED
        del self._positions[symbol]

        return order

    def check_stop_loss_take_profit(self, prices: dict[str, float]) -> list[Order]:
        """Vérifie les SL/TP pour toutes les positions ouvertes."""
        orders = []
        for symbol in list(self._positions.keys()):
            pos = self._positions[symbol]
            price = prices.get(symbol, pos.current_price)
            pos.update_pnl(price)

            triggered = False
            if pos.side == OrderSide.BUY:
                if price <= pos.stop_loss or price >= pos.take_profit:
                    triggered = True
            else:
                if price >= pos.stop_loss or price <= pos.take_profit:
                    triggered = True

            if triggered:
                reason = "SL" if (
                    (pos.side == OrderSide.BUY and price <= pos.stop_loss) or
                    (pos.side == OrderSide.SELL and price >= pos.stop_loss)
                ) else "TP"
                self.logger.info("%s déclenché pour %s @ %.4f", reason, symbol, price)
                order = self._close_position(symbol, price)
                if order:
                    orders.append(order)

        return orders

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'exécution."""
        return self.get_dashboard_data()

    def get_dashboard_data(self) -> dict[str, Any]:
        """Retourne toutes les données pour le dashboard."""
        total_pnl = sum(pos.pnl for pos in self._positions.values())
        total_pnl += sum(t.pnl for t in self._trade_history)

        return {
            "portfolio_value": round(self._portfolio_value, 2),
            "cash": round(self._cash, 2),
            "total_pnl": round(total_pnl, 2),
            "auto_trade": self._auto_trade,
            "open_positions": {
                sym: pos.to_dict() for sym, pos in self._positions.items()
            },
            "recent_orders": [o.to_dict() for o in self._orders[-20:]],
            "trade_history": [t.to_dict() for t in self._trade_history[-50:]],
            "stats": self._compute_stats(),
        }

    def _compute_stats(self) -> dict[str, Any]:
        """Calcule les statistiques de trading."""
        if not self._trade_history:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "avg_pnl": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "profit_factor": 0,
                "avg_duration_hours": 0,
            }

        trades = self._trade_history
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total_profit = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))

        return {
            "total_trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "avg_pnl": round(sum(t.pnl for t in trades) / len(trades), 2),
            "best_trade": round(max(t.pnl for t in trades), 2) if trades else 0,
            "worst_trade": round(min(t.pnl for t in trades), 2) if trades else 0,
            "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else float("inf"),
            "avg_duration_hours": round(sum(t.duration_hours for t in trades) / len(trades), 1),
        }

    def get_positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def get_trade_history(self) -> list[TradeRecord]:
        return list(self._trade_history)

    def set_capital(self, value: float) -> None:
        self._portfolio_value = value
        self._cash = value

    def shutdown(self) -> None:
        self.logger.info(
            "Execution Engine arrêté — %d positions ouvertes, %d trades historiques",
            len(self._positions), len(self._trade_history),
        )
