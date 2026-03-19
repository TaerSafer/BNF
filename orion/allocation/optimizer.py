"""
Optimisation de portefeuille d'O.R.I.O.N.

Implémente les méthodes d'optimisation adaptative : Mean-Variance,
Risk Parity, Black-Litterman, et l'allocation par régime.
Le modèle cherche non pas à battre le marché, mais à s'accorder
à sa structure profonde.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orion.allocation.optimizer")


@dataclass
class AllocationResult:
    """Résultat d'une optimisation d'allocation."""
    weights: dict[str, float]
    method: str
    expected_return: float = 0.0
    expected_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    turnover: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        total = sum(self.weights.values())
        return abs(total - 1.0) < 0.01

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": self.weights,
            "method": self.method,
            "expected_return": self.expected_return,
            "expected_volatility": self.expected_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "turnover": self.turnover,
            "timestamp": self.timestamp.isoformat(),
        }


class PortfolioOptimizer:
    """
    Optimiseur de portefeuille multi-méthode.

    Combine plusieurs approches d'optimisation pour produire
    une allocation robuste et adaptative :

    1. Equal Weight — Allocation équipondérée (benchmark)
    2. Risk Parity — Parité de risque (contribution égale à la volatilité)
    3. Mean-Variance — Markowitz optimisé
    4. Regime-Adaptive — Allocation guidée par le régime macro
    """

    def __init__(
        self,
        min_weight: float = 0.0,
        max_weight: float = 0.30,
        turnover_penalty: float = 0.001,
    ) -> None:
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.turnover_penalty = turnover_penalty

    def equal_weight(self, assets: list[str]) -> AllocationResult:
        """Allocation équipondérée."""
        if not assets:
            return AllocationResult(weights={}, method="equal_weight")
        w = 1.0 / len(assets)
        return AllocationResult(
            weights={a: w for a in assets},
            method="equal_weight",
        )

    def risk_parity(
        self,
        assets: list[str],
        volatilities: dict[str, float],
    ) -> AllocationResult:
        """
        Allocation Risk Parity.

        Chaque actif contribue de manière égale au risque total
        du portefeuille. Les actifs moins volatils reçoivent
        une pondération plus élevée.
        """
        if not assets or not volatilities:
            return AllocationResult(weights={}, method="risk_parity")

        inv_vols = {}
        for asset in assets:
            vol = volatilities.get(asset, 0.0)
            inv_vols[asset] = 1.0 / vol if vol > 0 else 0.0

        total_inv = sum(inv_vols.values())
        if total_inv == 0:
            return self.equal_weight(assets)

        weights = {a: v / total_inv for a, v in inv_vols.items()}
        weights = self._apply_constraints(weights)

        return AllocationResult(
            weights=weights,
            method="risk_parity",
        )

    def mean_variance(
        self,
        assets: list[str],
        expected_returns: dict[str, float],
        volatilities: dict[str, float],
        risk_aversion: float = 2.0,
    ) -> AllocationResult:
        """
        Allocation Mean-Variance (Markowitz simplifié).

        Maximise le ratio rendement/risque ajusté par le coefficient
        d'aversion au risque.
        """
        if not assets:
            return AllocationResult(weights={}, method="mean_variance")

        # Score d'utilité pour chaque actif : E[r] - λ/2 * σ²
        scores = {}
        for asset in assets:
            ret = expected_returns.get(asset, 0.0)
            vol = volatilities.get(asset, 0.01)
            scores[asset] = ret - (risk_aversion / 2) * vol ** 2

        # Normaliser les scores positifs en poids
        min_score = min(scores.values())
        shifted = {a: s - min_score + 0.01 for a, s in scores.items()}
        total = sum(shifted.values())

        weights = {a: s / total for a, s in shifted.items()} if total > 0 else {a: 1.0 / len(assets) for a in assets}
        weights = self._apply_constraints(weights)

        # Estimer les métriques du portefeuille
        port_return = sum(
            weights.get(a, 0) * expected_returns.get(a, 0) for a in assets
        )
        port_vol = math.sqrt(sum(
            (weights.get(a, 0) * volatilities.get(a, 0.01)) ** 2 for a in assets
        ))

        return AllocationResult(
            weights=weights,
            method="mean_variance",
            expected_return=port_return,
            expected_volatility=port_vol,
            sharpe_ratio=port_return / port_vol if port_vol > 0 else 0.0,
        )

    def regime_adaptive(
        self,
        assets: list[str],
        regime_profile: dict[str, float],
        volatilities: dict[str, float],
        asset_classification: dict[str, str],
        adaptation_speed: float = 0.3,
        current_weights: dict[str, float] | None = None,
    ) -> AllocationResult:
        """
        Allocation adaptative par régime.

        Combine le profil d'allocation optimal du régime macro-économique
        avec les volatilités observées et les poids actuels (inertie).
        """
        if not assets:
            return AllocationResult(weights={}, method="regime_adaptive")

        # Poids cibles basés sur le régime
        target_weights: dict[str, float] = {}
        for asset in assets:
            asset_type = asset_classification.get(asset, "equity")
            base_weight = regime_profile.get(asset_type, 0.0)
            # Distribuer le poids de la classe entre les actifs de cette classe
            same_class = [a for a in assets if asset_classification.get(a) == asset_type]
            target_weights[asset] = base_weight / len(same_class) if same_class else 0.0

        # Mélanger avec les poids actuels (inertie)
        if current_weights:
            for asset in assets:
                target = target_weights.get(asset, 0.0)
                current = current_weights.get(asset, 0.0)
                target_weights[asset] = (
                    adaptation_speed * target + (1 - adaptation_speed) * current
                )

        # Ajuster par volatilité inverse (risk parity overlay)
        if volatilities:
            for asset in assets:
                vol = volatilities.get(asset, 0.01)
                target_weights[asset] /= max(vol, 0.001)

        # Normaliser
        total = sum(target_weights.values())
        if total > 0:
            target_weights = {a: w / total for a, w in target_weights.items()}

        target_weights = self._apply_constraints(target_weights)

        # Calculer le turnover
        turnover = 0.0
        if current_weights:
            turnover = sum(
                abs(target_weights.get(a, 0) - current_weights.get(a, 0))
                for a in set(list(target_weights.keys()) + list(current_weights.keys()))
            ) / 2

        return AllocationResult(
            weights=target_weights,
            method="regime_adaptive",
            turnover=turnover,
        )

    def _apply_constraints(self, weights: dict[str, float]) -> dict[str, float]:
        """Applique les contraintes de poids min/max et renormalise itérativement."""
        constrained = dict(weights)
        for _ in range(20):
            clamped = {}
            overflow = 0.0
            free_total = 0.0

            for asset, w in constrained.items():
                if w > self.max_weight:
                    overflow += w - self.max_weight
                    clamped[asset] = self.max_weight
                elif w < self.min_weight:
                    overflow -= self.min_weight - w
                    clamped[asset] = self.min_weight
                else:
                    clamped[asset] = w
                    free_total += w

            if abs(overflow) < 1e-10:
                constrained = clamped
                break

            # Redistribute overflow to unclamped assets
            if free_total > 0:
                for asset in clamped:
                    if self.min_weight < clamped[asset] < self.max_weight:
                        clamped[asset] += overflow * (clamped[asset] / free_total)
            constrained = clamped

        # Final normalization
        total = sum(constrained.values())
        if total > 0:
            constrained = {a: w / total for a, w in constrained.items()}

        return constrained
