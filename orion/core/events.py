"""
Système d'événements d'O.R.I.O.N.

Bus événementiel pour la communication asynchrone entre les moteurs.
Chaque module peut émettre et écouter des événements sans couplage direct.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("orion.events")


class EventType(Enum):
    """Types d'événements système."""
    # Données
    DATA_UPDATED = "data.updated"
    DATA_ERROR = "data.error"

    # Risque
    RISK_BREACH = "risk.breach"
    RISK_WARNING = "risk.warning"
    RISK_RECALCULATED = "risk.recalculated"

    # Macro
    REGIME_CHANGE = "macro.regime_change"
    CYCLE_SHIFT = "macro.cycle_shift"
    INDICATOR_ALERT = "macro.indicator_alert"

    # Allocation
    REBALANCE_TRIGGERED = "allocation.rebalance_triggered"
    ALLOCATION_UPDATED = "allocation.updated"
    WEIGHT_DRIFT = "allocation.weight_drift"

    # Volatilité
    VOLATILITY_SPIKE = "volatility.spike"
    CORRELATION_BREAK = "volatility.correlation_break"

    # Système
    ENGINE_STARTED = "system.engine_started"
    ENGINE_STOPPED = "system.engine_stopped"
    HEARTBEAT = "system.heartbeat"


@dataclass
class Event:
    """Événement système."""
    type: EventType
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 0

    def __repr__(self) -> str:
        return f"Event({self.type.value}, source={self.source}, priority={self.priority})"


class EventBus:
    """Bus événementiel central d'O.R.I.O.N."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 10_000

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Abonne un handler à un type d'événement."""
        self._handlers[event_type].append(handler)
        logger.debug("Handler inscrit pour %s", event_type.value)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Désabonne un handler."""
        self._handlers[event_type] = [
            h for h in self._handlers[event_type] if h != handler
        ]

    def emit(self, event: Event) -> None:
        """Émet un événement vers tous les handlers abonnés."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Erreur dans le handler pour %s", event.type.value
                )

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Retourne l'historique des événements."""
        events = self._history
        if event_type is not None:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

    def clear(self) -> None:
        """Réinitialise le bus."""
        self._handlers.clear()
        self._history.clear()
