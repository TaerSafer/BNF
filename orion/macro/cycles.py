"""
Analyse des cycles économiques d'O.R.I.O.N.

Détecte et modélise les cycles d'expansion/contraction sur des horizons
multiples, des cycles de Kitchin (3-5 ans) aux cycles de Kondratiev (40-60 ans).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.macro.cycles")


class CycleType(Enum):
    """Types de cycles économiques."""
    KITCHIN = "kitchin"           # 3-5 ans — inventaires
    JUGLAR = "juglar"             # 7-11 ans — investissement
    KUZNETS = "kuznets"           # 15-25 ans — infrastructure
    KONDRATIEV = "kondratiev"     # 40-60 ans — technologie
    DEBT_SUPER = "debt_super"     # 75-100 ans — dette long terme


@dataclass
class CyclePhase:
    """Phase d'un cycle économique."""
    cycle_type: CycleType
    phase: str  # "expansion", "peak", "contraction", "trough"
    position: float  # 0.0 (trough) à 1.0 (peak)
    estimated_duration_months: int = 0
    months_into_phase: int = 0
    confidence: float = 0.5

    @property
    def is_rising(self) -> bool:
        return self.phase in ("expansion", "trough")

    @property
    def completion_pct(self) -> float:
        if self.estimated_duration_months == 0:
            return 0.0
        return min(1.0, self.months_into_phase / self.estimated_duration_months)


@dataclass
class CycleSnapshot:
    """Instantané multi-cycle à un moment donné."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    phases: dict[CycleType, CyclePhase] = field(default_factory=dict)
    composite_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "composite_score": self.composite_score,
            "cycles": {
                ct.value: {
                    "phase": cp.phase,
                    "position": cp.position,
                    "confidence": cp.confidence,
                }
                for ct, cp in self.phases.items()
            },
        }


class CycleAnalyzer:
    """
    Analyseur multi-cycle.

    Superpose les différents cycles économiques pour obtenir
    une lecture composite de la position dans le temps économique.

    L'objectif n'est pas de prévoir, mais de comprendre le mouvement
    du temps, les cycles d'expansion et de contraction.
    """

    # Durées moyennes des cycles (en mois)
    CYCLE_DURATIONS: dict[CycleType, int] = {
        CycleType.KITCHIN: 48,       # ~4 ans
        CycleType.JUGLAR: 108,       # ~9 ans
        CycleType.KUZNETS: 240,      # ~20 ans
        CycleType.KONDRATIEV: 600,   # ~50 ans
        CycleType.DEBT_SUPER: 900,   # ~75 ans
    }

    # Poids de chaque cycle dans le score composite
    CYCLE_WEIGHTS: dict[CycleType, float] = {
        CycleType.KITCHIN: 0.30,
        CycleType.JUGLAR: 0.30,
        CycleType.KUZNETS: 0.20,
        CycleType.KONDRATIEV: 0.15,
        CycleType.DEBT_SUPER: 0.05,
    }

    # Dates de référence des derniers creux (approximatifs)
    REFERENCE_TROUGHS: dict[CycleType, datetime] = {
        CycleType.KITCHIN: datetime(2023, 1, 1, tzinfo=timezone.utc),
        CycleType.JUGLAR: datetime(2020, 3, 1, tzinfo=timezone.utc),
        CycleType.KUZNETS: datetime(2009, 3, 1, tzinfo=timezone.utc),
        CycleType.KONDRATIEV: datetime(2009, 3, 1, tzinfo=timezone.utc),
        CycleType.DEBT_SUPER: datetime(1945, 1, 1, tzinfo=timezone.utc),
    }

    def __init__(self) -> None:
        self._history: list[CycleSnapshot] = []

    def analyze(self, as_of: datetime | None = None) -> CycleSnapshot:
        """
        Analyse la position dans tous les cycles à une date donnée.

        Utilise un modèle sinusoïdal calibré sur les durées historiques
        et les dates de référence des creux.
        """
        as_of = as_of or datetime.now(timezone.utc)
        snapshot = CycleSnapshot(timestamp=as_of)

        for cycle_type, duration in self.CYCLE_DURATIONS.items():
            trough = self.REFERENCE_TROUGHS[cycle_type]
            months_elapsed = (as_of.year - trough.year) * 12 + (as_of.month - trough.month)

            # Position sinusoïdale dans le cycle [0, 2π]
            cycle_position_rad = (2 * math.pi * months_elapsed) / duration
            # Normaliser en [0, 1] : 0 = trough, 0.5 = peak
            position = (math.sin(cycle_position_rad - math.pi / 2) + 1) / 2

            # Déterminer la phase
            normalized = (months_elapsed % duration) / duration
            if normalized < 0.25:
                phase = "expansion"
            elif normalized < 0.50:
                phase = "peak"
            elif normalized < 0.75:
                phase = "contraction"
            else:
                phase = "trough"

            phase_start = int(normalized * 4) / 4
            months_into = int((normalized - phase_start) * duration)

            snapshot.phases[cycle_type] = CyclePhase(
                cycle_type=cycle_type,
                phase=phase,
                position=position,
                estimated_duration_months=duration // 4,
                months_into_phase=months_into,
                confidence=0.6 if cycle_type in (CycleType.KITCHIN, CycleType.JUGLAR) else 0.4,
            )

        # Score composite pondéré
        snapshot.composite_score = sum(
            self.CYCLE_WEIGHTS[ct] * (phase.position * 2 - 1)
            for ct, phase in snapshot.phases.items()
        )

        self._history.append(snapshot)
        return snapshot

    def get_dominant_cycle(self, snapshot: CycleSnapshot | None = None) -> CyclePhase | None:
        """Identifie le cycle dominant (plus forte amplitude)."""
        snap = snapshot or (self._history[-1] if self._history else None)
        if not snap or not snap.phases:
            return None
        return max(
            snap.phases.values(),
            key=lambda p: abs(p.position - 0.5) * p.confidence,
        )

    def get_convergence_zones(self) -> list[dict[str, Any]]:
        """
        Identifie les zones de convergence multi-cycle.

        Quand plusieurs cycles sont en phase similaire, l'effet
        est amplifié — c'est la « résonance cyclique ».
        """
        if not self._history:
            return []

        latest = self._history[-1]
        rising = [ct for ct, p in latest.phases.items() if p.is_rising]
        falling = [ct for ct, p in latest.phases.items() if not p.is_rising]

        zones = []
        if len(rising) >= 3:
            zones.append({
                "type": "bullish_convergence",
                "cycles": [c.value for c in rising],
                "strength": len(rising) / len(latest.phases),
            })
        if len(falling) >= 3:
            zones.append({
                "type": "bearish_convergence",
                "cycles": [c.value for c in falling],
                "strength": len(falling) / len(latest.phases),
            })

        return zones

    def get_history(self) -> list[CycleSnapshot]:
        return list(self._history)
