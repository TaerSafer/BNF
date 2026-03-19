"""
Risk Engine d'O.R.I.O.N.

Moteur central de gestion des risques. Calcule en continu les métriques
de risque du portefeuille, détecte les breaches, et émet des alertes.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from orion.core.config import OrionConfig
from orion.core.engine import BaseEngine
from orion.core.events import Event, EventBus, EventType
from orion.risk.models import (
    VaRModel,
    CorrelationMatrix,
    StressTest,
    RiskMetrics,
)

logger = logging.getLogger("orion.risk")


class RiskEngine(BaseEngine):
    """
    Moteur de risque — Gardien de la discipline d'O.R.I.O.N.

    Le risque n'est pas une contrainte mais la matière première
    de la performance. Ce moteur transforme la complexité
    en mesure exploitable.
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("risk", config, event_bus)
        self._var_model = VaRModel(
            confidence=config.risk.var_confidence,
            horizon_days=1,
        )
        self._correlation = CorrelationMatrix(
            lookback=config.risk.correlation_lookback_days,
        )
        self._stress_test = StressTest()
        self._current_metrics = RiskMetrics()
        self._returns_cache: dict[str, list[float]] = {}
        self._portfolio_weights: dict[str, float] = {}
        self._peak_value: float = 0.0
        self._current_value: float = 0.0

    def initialize(self) -> None:
        """Initialise le moteur de risque."""
        self.logger.info(
            "Risk Engine initialisé — VaR confidence: %.1f%%, lookback: %d jours",
            self._var_model.confidence * 100,
            self._correlation.lookback,
        )

    def update_returns(self, symbol: str, returns: list[float]) -> None:
        """Met à jour les rendements pour un symbole."""
        self._returns_cache[symbol] = returns

    def update_portfolio(self, weights: dict[str, float], value: float) -> None:
        """Met à jour l'état du portefeuille."""
        self._portfolio_weights = weights
        self._current_value = value
        self._peak_value = max(self._peak_value, value)

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle complet d'évaluation des risques."""
        metrics = RiskMetrics(timestamp=datetime.now(timezone.utc))

        # 1. Calcul VaR du portefeuille
        portfolio_returns = self._compute_portfolio_returns()
        if portfolio_returns:
            metrics.portfolio_var = self._var_model.historical_var(portfolio_returns)
            metrics.portfolio_cvar = self._var_model.expected_shortfall(portfolio_returns)
            metrics.sharpe_ratio = self._compute_sharpe(portfolio_returns)
            metrics.sortino_ratio = self._compute_sortino(portfolio_returns)

        # 2. Drawdown
        if self._peak_value > 0:
            metrics.current_drawdown = (self._peak_value - self._current_value) / self._peak_value
            metrics.max_drawdown = max(metrics.max_drawdown, metrics.current_drawdown)

        # 3. Corrélations
        if self._returns_cache:
            self._correlation.compute(self._returns_cache)

        # 4. Concentration
        if self._portfolio_weights:
            metrics.concentration_index = self._herfindahl_index(self._portfolio_weights)

        # 5. Vérification des limites
        if not metrics.is_within_limits(
            self.config.risk.max_portfolio_var,
            self.config.risk.max_drawdown_threshold,
        ):
            self.event_bus.emit(Event(
                type=EventType.RISK_BREACH,
                source="risk",
                data=metrics.to_dict(),
                priority=10,
            ))

        self._current_metrics = metrics

        self.event_bus.emit(Event(
            type=EventType.RISK_RECALCULATED,
            source="risk",
            data=metrics.to_dict(),
        ))

        return metrics.to_dict()

    def run_stress_tests(self, portfolio_value: float = 0.0) -> dict[str, Any]:
        """Exécute tous les scénarios de stress."""
        value = portfolio_value or self._current_value
        return self._stress_test.run_all_scenarios(self._portfolio_weights, value)

    def get_correlation_matrix(self) -> dict[tuple[str, str], float]:
        """Retourne la matrice de corrélation courante."""
        return dict(self._correlation._matrix)

    def get_risk_decomposition(self) -> dict[str, float]:
        """Décomposition du risque par actif (contribution marginale)."""
        if not self._portfolio_weights or not self._returns_cache:
            return {}

        decomposition = {}
        portfolio_returns = self._compute_portfolio_returns()
        portfolio_var = self._var_model.historical_var(portfolio_returns) if portfolio_returns else 0.0

        for symbol, weight in self._portfolio_weights.items():
            if symbol in self._returns_cache and portfolio_var > 0:
                asset_returns = self._returns_cache[symbol]
                asset_var = self._var_model.historical_var(asset_returns)
                decomposition[symbol] = (weight * asset_var) / portfolio_var
            else:
                decomposition[symbol] = 0.0

        return decomposition

    def get_metrics(self) -> RiskMetrics:
        """Retourne les métriques de risque courantes."""
        return self._current_metrics

    def _compute_portfolio_returns(self) -> list[float]:
        """Calcule les rendements pondérés du portefeuille."""
        if not self._portfolio_weights or not self._returns_cache:
            return []

        min_len = min(
            (len(r) for s, r in self._returns_cache.items() if s in self._portfolio_weights),
            default=0,
        )
        if min_len == 0:
            return []

        portfolio_returns = []
        for i in range(min_len):
            ret = sum(
                self._portfolio_weights.get(s, 0) * self._returns_cache[s][i]
                for s in self._portfolio_weights
                if s in self._returns_cache and i < len(self._returns_cache[s])
            )
            portfolio_returns.append(ret)

        return portfolio_returns

    @staticmethod
    def _compute_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
        """Calcule le ratio de Sharpe."""
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns))
        if std == 0:
            return 0.0
        return (mean - risk_free / 252) / std * math.sqrt(252)

    @staticmethod
    def _compute_sortino(returns: list[float], risk_free: float = 0.0) -> float:
        """Calcule le ratio de Sortino (pénalise uniquement la volatilité baissière)."""
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return float("inf")
        downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        if downside_std == 0:
            return 0.0
        return (mean - risk_free / 252) / downside_std * math.sqrt(252)

    @staticmethod
    def _herfindahl_index(weights: dict[str, float]) -> float:
        """Indice de Herfindahl-Hirschman — mesure de concentration."""
        return sum(w ** 2 for w in weights.values())

    def shutdown(self) -> None:
        """Arrêt du moteur de risque."""
        self.logger.info("Risk Engine arrêté")
