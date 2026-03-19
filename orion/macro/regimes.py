"""
Détection des régimes économiques d'O.R.I.O.N.

Identifie le régime macro-économique courant (expansion, contraction,
crise, reprise) à partir des signaux du panel d'indicateurs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.macro.regimes")


class EconomicRegime(Enum):
    """Régimes économiques fondamentaux."""
    EARLY_EXPANSION = "early_expansion"
    LATE_EXPANSION = "late_expansion"
    SLOWDOWN = "slowdown"
    CONTRACTION = "contraction"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    STAGNATION = "stagnation"
    REFLATION = "reflation"


@dataclass
class RegimeState:
    """État courant du régime détecté."""
    regime: EconomicRegime
    confidence: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signals: dict[str, float] = field(default_factory=dict)
    duration_months: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "duration_months": self.duration_months,
            "timestamp": self.timestamp.isoformat(),
        }


# Profils d'actifs optimaux par régime
REGIME_ASSET_PROFILES: dict[EconomicRegime, dict[str, float]] = {
    EconomicRegime.EARLY_EXPANSION: {
        "equity": 0.35, "fixed_income": 0.15, "commodity": 0.20,
        "forex_carry": 0.15, "crypto": 0.10, "volatility_short": 0.05,
    },
    EconomicRegime.LATE_EXPANSION: {
        "equity": 0.25, "fixed_income": 0.20, "commodity": 0.25,
        "forex_carry": 0.10, "crypto": 0.05, "volatility_short": 0.15,
    },
    EconomicRegime.SLOWDOWN: {
        "equity": 0.10, "fixed_income": 0.35, "commodity": 0.15,
        "forex_safe": 0.20, "crypto": 0.0, "volatility_long": 0.20,
    },
    EconomicRegime.CONTRACTION: {
        "equity": 0.05, "fixed_income": 0.40, "commodity": 0.05,
        "forex_safe": 0.25, "crypto": 0.0, "volatility_long": 0.25,
    },
    EconomicRegime.CRISIS: {
        "equity": 0.0, "fixed_income": 0.30, "commodity": 0.10,
        "forex_safe": 0.30, "crypto": 0.0, "volatility_long": 0.30,
    },
    EconomicRegime.RECOVERY: {
        "equity": 0.30, "fixed_income": 0.20, "commodity": 0.20,
        "forex_carry": 0.15, "crypto": 0.10, "volatility_short": 0.05,
    },
    EconomicRegime.STAGNATION: {
        "equity": 0.15, "fixed_income": 0.30, "commodity": 0.15,
        "forex_safe": 0.15, "crypto": 0.05, "volatility_long": 0.20,
    },
    EconomicRegime.REFLATION: {
        "equity": 0.25, "fixed_income": 0.10, "commodity": 0.30,
        "forex_carry": 0.15, "crypto": 0.10, "volatility_short": 0.10,
    },
}


class RegimeDetector:
    """
    Détecteur de régimes économiques.

    Utilise une combinaison de signaux macro-économiques pour
    identifier le régime courant et sa probabilité de transition.
    """

    # Seuils de classification
    THRESHOLDS = {
        "expansion_leading": 0.3,
        "contraction_leading": -0.3,
        "crisis_threshold": -0.6,
        "recovery_threshold": 0.2,
    }

    def __init__(self, sensitivity: float = 0.7) -> None:
        self.sensitivity = sensitivity
        self._current_state: RegimeState | None = None
        self._history: list[RegimeState] = []
        self._transition_matrix: dict[EconomicRegime, dict[EconomicRegime, float]] = (
            self._build_transition_matrix()
        )

    def detect(self, composite_signals: dict[str, float]) -> RegimeState:
        """
        Détecte le régime économique courant.

        Args:
            composite_signals: Signaux composites par type
                {"leading": float, "coincident": float, "lagging": float}
        """
        leading = composite_signals.get("leading", 0.0)
        coincident = composite_signals.get("coincident", 0.0)
        lagging = composite_signals.get("lagging", 0.0)

        regime, confidence = self._classify(leading, coincident, lagging)

        state = RegimeState(
            regime=regime,
            confidence=confidence,
            signals=composite_signals,
        )

        if self._current_state and self._current_state.regime == regime:
            state.duration_months = self._current_state.duration_months + 1
        else:
            state.duration_months = 1

        self._history.append(state)
        self._current_state = state

        return state

    def _classify(
        self,
        leading: float,
        coincident: float,
        lagging: float,
    ) -> tuple[EconomicRegime, float]:
        """Classifie le régime selon les signaux composites."""
        scores: dict[EconomicRegime, float] = {}

        # Crise : tous les signaux très négatifs
        if leading < -0.5 and coincident < -0.4:
            scores[EconomicRegime.CRISIS] = abs(leading + coincident)

        # Contraction : leading et coincident négatifs
        if leading < -0.2 and coincident < -0.1:
            scores[EconomicRegime.CONTRACTION] = abs(leading * 0.6 + coincident * 0.4)

        # Ralentissement : leading négatif, coincident encore positif
        if leading < 0 and coincident >= 0:
            scores[EconomicRegime.SLOWDOWN] = abs(leading) * 0.7

        # Expansion précoce : leading très positif, lagging encore bas
        if leading > 0.3 and lagging < 0:
            scores[EconomicRegime.EARLY_EXPANSION] = leading * 0.7

        # Expansion tardive : tous positifs, leading commence à baisser
        if leading > 0 and coincident > 0.2 and lagging > 0:
            scores[EconomicRegime.LATE_EXPANSION] = coincident * 0.5

        # Reprise : leading positif, coincident négatif mais en amélioration
        if leading > 0.2 and coincident < 0:
            scores[EconomicRegime.RECOVERY] = leading * 0.8

        # Stagnation : tout proche de zéro
        if abs(leading) < 0.15 and abs(coincident) < 0.15:
            scores[EconomicRegime.STAGNATION] = 1.0 - abs(leading + coincident)

        # Reflation : inflation en hausse, croissance modérée
        if lagging > 0.3 and coincident > 0:
            scores[EconomicRegime.REFLATION] = lagging * 0.5

        if not scores:
            return EconomicRegime.STAGNATION, 0.3

        best_regime = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = min(1.0, scores[best_regime] * self.sensitivity)

        return best_regime, confidence

    def get_asset_profile(self, regime: EconomicRegime | None = None) -> dict[str, float]:
        """Retourne le profil d'allocation optimal pour un régime."""
        regime = regime or (self._current_state.regime if self._current_state else EconomicRegime.STAGNATION)
        return REGIME_ASSET_PROFILES.get(regime, REGIME_ASSET_PROFILES[EconomicRegime.STAGNATION])

    def get_transition_probabilities(self) -> dict[EconomicRegime, float]:
        """Retourne les probabilités de transition depuis le régime courant."""
        if self._current_state is None:
            return {}
        return self._transition_matrix.get(self._current_state.regime, {})

    def get_history(self) -> list[RegimeState]:
        return list(self._history)

    @staticmethod
    def _build_transition_matrix() -> dict[EconomicRegime, dict[EconomicRegime, float]]:
        """Matrice de transition markovienne entre régimes (calibrée historiquement)."""
        return {
            EconomicRegime.EARLY_EXPANSION: {
                EconomicRegime.LATE_EXPANSION: 0.50,
                EconomicRegime.EARLY_EXPANSION: 0.35,
                EconomicRegime.SLOWDOWN: 0.10,
                EconomicRegime.STAGNATION: 0.05,
            },
            EconomicRegime.LATE_EXPANSION: {
                EconomicRegime.SLOWDOWN: 0.40,
                EconomicRegime.LATE_EXPANSION: 0.30,
                EconomicRegime.CONTRACTION: 0.15,
                EconomicRegime.REFLATION: 0.15,
            },
            EconomicRegime.SLOWDOWN: {
                EconomicRegime.CONTRACTION: 0.40,
                EconomicRegime.RECOVERY: 0.20,
                EconomicRegime.SLOWDOWN: 0.20,
                EconomicRegime.CRISIS: 0.10,
                EconomicRegime.STAGNATION: 0.10,
            },
            EconomicRegime.CONTRACTION: {
                EconomicRegime.CRISIS: 0.25,
                EconomicRegime.RECOVERY: 0.30,
                EconomicRegime.CONTRACTION: 0.25,
                EconomicRegime.STAGNATION: 0.20,
            },
            EconomicRegime.CRISIS: {
                EconomicRegime.RECOVERY: 0.45,
                EconomicRegime.CONTRACTION: 0.30,
                EconomicRegime.CRISIS: 0.15,
                EconomicRegime.STAGNATION: 0.10,
            },
            EconomicRegime.RECOVERY: {
                EconomicRegime.EARLY_EXPANSION: 0.50,
                EconomicRegime.RECOVERY: 0.25,
                EconomicRegime.STAGNATION: 0.15,
                EconomicRegime.SLOWDOWN: 0.10,
            },
            EconomicRegime.STAGNATION: {
                EconomicRegime.RECOVERY: 0.25,
                EconomicRegime.SLOWDOWN: 0.25,
                EconomicRegime.STAGNATION: 0.30,
                EconomicRegime.REFLATION: 0.20,
            },
            EconomicRegime.REFLATION: {
                EconomicRegime.LATE_EXPANSION: 0.30,
                EconomicRegime.SLOWDOWN: 0.30,
                EconomicRegime.REFLATION: 0.25,
                EconomicRegime.CONTRACTION: 0.15,
            },
        }
