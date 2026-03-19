"""
Macro Engine d'O.R.I.O.N.

Moteur d'analyse macro-économique. Orchestre la détection des régimes,
l'analyse des cycles, et la synthèse des indicateurs pour produire
une lecture unifiée de l'état du monde économique.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from orion.core.config import OrionConfig
from orion.core.engine import BaseEngine
from orion.core.events import Event, EventBus, EventType
from orion.macro.indicators import IndicatorPanel
from orion.macro.regimes import RegimeDetector, RegimeState, EconomicRegime
from orion.macro.cycles import CycleAnalyzer, CycleSnapshot

logger = logging.getLogger("orion.macro")


class MacroEngine(BaseEngine):
    """
    Moteur macro-économique — L'œil d'O.R.I.O.N.

    Observe l'économie mondiale dans sa totalité, modélise
    les dynamiques, et traduit chaque tension en signal lisible.
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("macro", config, event_bus)
        self._indicator_panel = IndicatorPanel()
        self._regime_detector = RegimeDetector(
            sensitivity=config.macro.regime_change_sensitivity,
        )
        self._cycle_analyzer = CycleAnalyzer()
        self._current_regime: RegimeState | None = None
        self._current_cycle: CycleSnapshot | None = None

    def initialize(self) -> None:
        """Initialise le moteur macro."""
        self.logger.info(
            "Macro Engine initialisé — Sensibilité régime: %.1f%%",
            self.config.macro.regime_change_sensitivity * 100,
        )

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'analyse macro-économique."""
        # 1. Signaux composites des indicateurs
        composite = self._indicator_panel.get_composite_signal()

        # 2. Détection du régime
        previous_regime = self._current_regime
        self._current_regime = self._regime_detector.detect(composite)

        # 3. Détection de changement de régime
        if previous_regime and previous_regime.regime != self._current_regime.regime:
            self.event_bus.emit(Event(
                type=EventType.REGIME_CHANGE,
                source="macro",
                data={
                    "previous": previous_regime.regime.value,
                    "current": self._current_regime.regime.value,
                    "confidence": self._current_regime.confidence,
                },
                priority=8,
            ))
            self.logger.info(
                "Changement de régime: %s → %s (confiance: %.0f%%)",
                previous_regime.regime.value,
                self._current_regime.regime.value,
                self._current_regime.confidence * 100,
            )

        # 4. Analyse des cycles
        self._current_cycle = self._cycle_analyzer.analyze()

        # 5. Zones de convergence
        convergences = self._cycle_analyzer.get_convergence_zones()

        return {
            "regime": self._current_regime.to_dict(),
            "cycle": self._current_cycle.to_dict(),
            "composite_signals": composite,
            "convergence_zones": convergences,
            "asset_profile": self._regime_detector.get_asset_profile(),
            "transition_probabilities": {
                r.value: p
                for r, p in self._regime_detector.get_transition_probabilities().items()
            },
        }

    def update_indicator(
        self,
        code: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Met à jour un indicateur macro-économique."""
        self._indicator_panel.update_indicator(code, value, timestamp)

    def get_regime(self) -> RegimeState | None:
        return self._current_regime

    def get_cycle_snapshot(self) -> CycleSnapshot | None:
        return self._current_cycle

    def get_asset_profile(self) -> dict[str, float]:
        """Retourne le profil d'allocation basé sur le régime courant."""
        return self._regime_detector.get_asset_profile()

    def get_all_signals(self) -> dict[str, float]:
        """Retourne tous les signaux des indicateurs."""
        return self._indicator_panel.get_all_signals()

    def shutdown(self) -> None:
        self.logger.info("Macro Engine arrêté")
