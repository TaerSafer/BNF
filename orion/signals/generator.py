"""
Générateur de signaux d'O.R.I.O.N.

Synthétise les outputs de tous les moteurs en signaux d'action
cohérents et mesurables. Chaque signal est pondéré, filtré
et contextualisé par le régime macro-économique.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.signals")


class SignalType(Enum):
    """Types de signaux."""
    OVERWEIGHT = "overweight"
    UNDERWEIGHT = "underweight"
    NEUTRAL = "neutral"
    HEDGE = "hedge"
    EXIT = "exit"


class SignalStrength(Enum):
    """Force du signal."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    CONVICTION = "conviction"


@dataclass
class Signal:
    """Signal d'O.R.I.O.N."""
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    score: float  # [-1, 1]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sources: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    confidence: float = 0.5
    time_horizon_days: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type": self.signal_type.value,
            "strength": self.strength.value,
            "score": self.score,
            "confidence": self.confidence,
            "sources": self.sources,
            "rationale": self.rationale,
            "horizon_days": self.time_horizon_days,
        }


class SignalGenerator:
    """
    Générateur de signaux multi-source.

    Agrège les informations des moteurs :
    - Macro : régime et profil d'allocation
    - Volatilité : régime et dislocations
    - Risque : contraintes et limites
    - Cycles : position et convergences

    Produit un signal pondéré pour chaque actif de l'univers.
    """

    # Poids des sources dans le signal final
    SOURCE_WEIGHTS = {
        "macro_regime": 0.30,
        "volatility": 0.25,
        "cycle_position": 0.20,
        "risk_budget": 0.15,
        "momentum": 0.10,
    }

    def __init__(self) -> None:
        self._signals: dict[str, Signal] = {}
        self._history: list[dict[str, Signal]] = []

    def generate(
        self,
        symbol: str,
        macro_score: float = 0.0,
        volatility_score: float = 0.0,
        cycle_score: float = 0.0,
        risk_score: float = 0.0,
        momentum_score: float = 0.0,
    ) -> Signal:
        """
        Génère un signal composite pour un actif.

        Chaque score d'entrée est dans [-1, 1] :
        - Positif = favorable (overweight)
        - Négatif = défavorable (underweight)
        """
        sources = {
            "macro_regime": macro_score,
            "volatility": volatility_score,
            "cycle_position": cycle_score,
            "risk_budget": risk_score,
            "momentum": momentum_score,
        }

        # Score composite pondéré
        composite = sum(
            self.SOURCE_WEIGHTS[key] * score
            for key, score in sources.items()
        )

        # Classifier le signal
        signal_type = self._classify_signal(composite)
        strength = self._classify_strength(composite)
        confidence = self._compute_confidence(sources)

        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            strength=strength,
            score=composite,
            sources=sources,
            confidence=confidence,
            rationale=self._build_rationale(symbol, sources, composite),
        )

        self._signals[symbol] = signal
        return signal

    def generate_all(
        self,
        assets: list[str],
        macro_scores: dict[str, float] | None = None,
        volatility_scores: dict[str, float] | None = None,
        cycle_score: float = 0.0,
        risk_scores: dict[str, float] | None = None,
    ) -> dict[str, Signal]:
        """Génère des signaux pour tous les actifs."""
        macro_scores = macro_scores or {}
        volatility_scores = volatility_scores or {}
        risk_scores = risk_scores or {}

        signals = {}
        for asset in assets:
            signals[asset] = self.generate(
                symbol=asset,
                macro_score=macro_scores.get(asset, 0.0),
                volatility_score=volatility_scores.get(asset, 0.0),
                cycle_score=cycle_score,
                risk_score=risk_scores.get(asset, 0.0),
            )

        self._history.append(dict(signals))
        return signals

    def get_top_signals(self, n: int = 10) -> list[Signal]:
        """Retourne les N signaux les plus forts (positifs)."""
        return sorted(
            self._signals.values(),
            key=lambda s: s.score,
            reverse=True,
        )[:n]

    def get_bottom_signals(self, n: int = 10) -> list[Signal]:
        """Retourne les N signaux les plus négatifs."""
        return sorted(
            self._signals.values(),
            key=lambda s: s.score,
        )[:n]

    @staticmethod
    def _classify_signal(score: float) -> SignalType:
        if score > 0.15:
            return SignalType.OVERWEIGHT
        if score < -0.15:
            return SignalType.UNDERWEIGHT
        return SignalType.NEUTRAL

    @staticmethod
    def _classify_strength(score: float) -> SignalStrength:
        abs_score = abs(score)
        if abs_score > 0.6:
            return SignalStrength.CONVICTION
        if abs_score > 0.4:
            return SignalStrength.STRONG
        if abs_score > 0.2:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @staticmethod
    def _compute_confidence(sources: dict[str, float]) -> float:
        """La confiance augmente quand les sources convergent."""
        values = list(sources.values())
        if not values:
            return 0.0
        all_positive = all(v >= 0 for v in values)
        all_negative = all(v <= 0 for v in values)
        if all_positive or all_negative:
            return min(1.0, sum(abs(v) for v in values) / len(values) + 0.3)
        return max(0.1, 0.5 - sum(abs(v) for v in values) / len(values) * 0.2)

    @staticmethod
    def _build_rationale(
        symbol: str,
        sources: dict[str, float],
        composite: float,
    ) -> str:
        """Construit une explication textuelle du signal."""
        direction = "haussier" if composite > 0 else "baissier"
        dominant = max(sources, key=lambda k: abs(sources[k]))
        return (
            f"{symbol}: Signal {direction} (score={composite:.2f}). "
            f"Source dominante: {dominant} ({sources[dominant]:+.2f})"
        )
