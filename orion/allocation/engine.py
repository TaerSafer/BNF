"""
Allocation Engine d'O.R.I.O.N.

Moteur d'allocation adaptative. Orchestre l'optimisation du portefeuille
en intégrant les signaux du régime macro, les métriques de risque,
et les contraintes opérationnelles.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from orion.core.config import OrionConfig, AssetClass
from orion.core.engine import BaseEngine
from orion.core.events import Event, EventBus, EventType
from orion.allocation.optimizer import PortfolioOptimizer, AllocationResult

logger = logging.getLogger("orion.allocation")


class AllocationEngine(BaseEngine):
    """
    Moteur d'allocation — Le bras d'O.R.I.O.N.

    Transforme les analyses en décisions d'allocation concrètes.
    Orchestre la répartition du capital comme un organisme rationnel,
    discipliné et durable.
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("allocation", config, event_bus)
        self._optimizer = PortfolioOptimizer(
            min_weight=config.allocation.min_asset_weight,
            max_weight=config.allocation.max_asset_weight,
            turnover_penalty=config.allocation.turnover_penalty,
        )
        self._current_allocation: AllocationResult | None = None
        self._allocation_history: list[AllocationResult] = []
        self._regime_profile: dict[str, float] = {}
        self._volatilities: dict[str, float] = {}
        self._expected_returns: dict[str, float] = {}
        self._asset_classification: dict[str, str] = {}
        self._cycles_since_rebalance = 0

    def initialize(self) -> None:
        """Initialise le moteur d'allocation."""
        self._build_asset_classification()
        self.logger.info(
            "Allocation Engine initialisé — Méthode: %s, Rebalance: %d jours",
            self.config.allocation.optimization_method,
            self.config.allocation.rebalance_frequency_days,
        )

    def update_regime_profile(self, profile: dict[str, float]) -> None:
        """Met à jour le profil d'allocation basé sur le régime."""
        self._regime_profile = profile

    def update_volatilities(self, volatilities: dict[str, float]) -> None:
        """Met à jour les volatilités observées."""
        self._volatilities = volatilities

    def update_expected_returns(self, returns: dict[str, float]) -> None:
        """Met à jour les rendements attendus."""
        self._expected_returns = returns

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'allocation."""
        self._cycles_since_rebalance += 1

        # Vérifier si un rebalancement est nécessaire
        needs_rebalance = (
            self._current_allocation is None
            or self._cycles_since_rebalance >= self.config.allocation.rebalance_frequency_days
        )

        if not needs_rebalance and self._current_allocation:
            return self._current_allocation.to_dict()

        # Construire la liste d'actifs
        assets = self._get_active_universe()

        # Choisir la méthode d'optimisation
        method = self.config.allocation.optimization_method

        if method == "regime_adaptive" and self._regime_profile:
            result = self._optimizer.regime_adaptive(
                assets=assets,
                regime_profile=self._regime_profile,
                volatilities=self._volatilities,
                asset_classification=self._asset_classification,
                adaptation_speed=self.config.allocation.regime_adaptation_speed,
                current_weights=(
                    self._current_allocation.weights
                    if self._current_allocation else None
                ),
            )
        elif method == "risk_parity" and self._volatilities:
            result = self._optimizer.risk_parity(
                assets=assets,
                volatilities=self._volatilities,
            )
        elif method == "mean_variance" and self._expected_returns:
            result = self._optimizer.mean_variance(
                assets=assets,
                expected_returns=self._expected_returns,
                volatilities=self._volatilities,
            )
        else:
            result = self._optimizer.equal_weight(assets)

        self._current_allocation = result
        self._allocation_history.append(result)
        self._cycles_since_rebalance = 0

        self.event_bus.emit(Event(
            type=EventType.ALLOCATION_UPDATED,
            source="allocation",
            data=result.to_dict(),
        ))

        return result.to_dict()

    def get_current_allocation(self) -> AllocationResult | None:
        return self._current_allocation

    def get_allocation_history(self) -> list[AllocationResult]:
        return list(self._allocation_history)

    def _get_active_universe(self) -> list[str]:
        """Construit la liste des actifs actifs."""
        assets = []
        for asset_class, symbols in self.config.universe.items():
            assets.extend(symbols)
        return assets

    def _build_asset_classification(self) -> None:
        """Classifie chaque actif du universe dans sa catégorie."""
        for asset_class, symbols in self.config.universe.items():
            for symbol in symbols:
                self._asset_classification[symbol] = asset_class

    def shutdown(self) -> None:
        self.logger.info("Allocation Engine arrêté")
