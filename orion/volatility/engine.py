"""
Volatility Engine d'O.R.I.O.N.

Moteur de modélisation de la volatilité. Calcule en continu les volatilités
de chaque actif, maintient la surface de volatilité, et détecte les
dislocations cross-asset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from orion.core.config import OrionConfig
from orion.core.engine import BaseEngine
from orion.core.events import Event, EventBus, EventType
from orion.volatility.models import (
    VolatilityModel,
    VolatilitySurface,
    VolatilityRegime,
    VolatilitySnapshot,
)

logger = logging.getLogger("orion.volatility")


class VolatilityEngine(BaseEngine):
    """
    Moteur de volatilité — Le sens tactile d'O.R.I.O.N.

    La volatilité n'est pas du bruit : c'est un langage.
    Ce moteur le traduit en information exploitable.
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("volatility", config, event_bus)
        self._model = VolatilityModel()
        self._surface = VolatilitySurface()
        self._returns_cache: dict[str, list[float]] = {}
        self._previous_regimes: dict[str, VolatilityRegime] = {}

    def initialize(self) -> None:
        """Initialise le moteur de volatilité."""
        self.logger.info("Volatility Engine initialisé — EWMA λ=%.2f", self._model.ewma_lambda)

    def update_returns(self, symbol: str, returns: list[float]) -> None:
        """Met à jour les rendements d'un actif."""
        self._returns_cache[symbol] = returns

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'analyse de volatilité."""
        results: dict[str, Any] = {
            "snapshots": {},
            "regime_changes": [],
            "extreme_assets": [],
            "mean_regime": "normal",
        }

        for symbol, returns in self._returns_cache.items():
            if len(returns) < 5:
                continue

            snapshot = self._model.full_analysis(symbol, returns)
            self._surface.update(snapshot)
            results["snapshots"][symbol] = snapshot.to_dict()

            # Détecter les changements de régime de volatilité
            prev_regime = self._previous_regimes.get(symbol)
            if prev_regime and prev_regime != snapshot.regime:
                results["regime_changes"].append({
                    "symbol": symbol,
                    "previous": prev_regime.value,
                    "current": snapshot.regime.value,
                })

                # Spike de volatilité
                if snapshot.regime in (VolatilityRegime.HIGH, VolatilityRegime.EXTREME):
                    self.event_bus.emit(Event(
                        type=EventType.VOLATILITY_SPIKE,
                        source="volatility",
                        data={
                            "symbol": symbol,
                            "regime": snapshot.regime.value,
                            "ewma_vol": snapshot.ewma_vol,
                        },
                        priority=7,
                    ))

            self._previous_regimes[symbol] = snapshot.regime

        # Actifs extrêmes
        results["extreme_assets"] = self._surface.get_extreme_assets()
        results["mean_regime"] = self._surface.get_mean_regime().value

        return results

    def get_volatilities(self) -> dict[str, float]:
        """Retourne les volatilités EWMA de tous les actifs."""
        return {
            symbol: snap.ewma_vol
            for symbol, snap in self._surface.get_all_snapshots().items()
        }

    def get_surface(self) -> VolatilitySurface:
        return self._surface

    def get_snapshot(self, symbol: str) -> VolatilitySnapshot | None:
        return self._surface.get_snapshot(symbol)

    def shutdown(self) -> None:
        self.logger.info("Volatility Engine arrêté")
