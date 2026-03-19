"""
Modèles de risque d'O.R.I.O.N.

Implémente les métriques fondamentales : Value at Risk, Expected Shortfall,
matrice de corrélation dynamique, stress testing et limites de risque.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orion.risk.models")


@dataclass
class RiskMetrics:
    """Métriques de risque agrégées pour un portefeuille."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    portfolio_var: float = 0.0
    portfolio_cvar: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    beta: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    concentration_index: float = 0.0
    liquidity_score: float = 1.0

    def is_within_limits(self, max_var: float, max_drawdown: float) -> bool:
        return self.portfolio_var <= max_var and self.current_drawdown <= max_drawdown

    def to_dict(self) -> dict[str, Any]:
        return {
            "var": self.portfolio_var,
            "cvar": self.portfolio_cvar,
            "max_drawdown": self.max_drawdown,
            "current_drawdown": self.current_drawdown,
            "sharpe": self.sharpe_ratio,
            "sortino": self.sortino_ratio,
            "calmar": self.calmar_ratio,
            "beta": self.beta,
            "concentration": self.concentration_index,
            "liquidity": self.liquidity_score,
        }


class VaRModel:
    """
    Modèle Value at Risk.

    Supporte trois méthodes :
    - Historique : basée sur la distribution empirique des rendements
    - Paramétrique : hypothèse de normalité (Gaussien)
    - Monte Carlo : simulation de trajectoires
    """

    def __init__(self, confidence: float = 0.99, horizon_days: int = 1) -> None:
        self.confidence = confidence
        self.horizon_days = horizon_days

    def historical_var(self, returns: list[float]) -> float:
        """VaR historique — percentile de la distribution empirique."""
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        index = int((1 - self.confidence) * len(sorted_returns))
        index = max(0, min(index, len(sorted_returns) - 1))
        var = -sorted_returns[index]
        return var * math.sqrt(self.horizon_days)

    def parametric_var(self, returns: list[float]) -> float:
        """VaR paramétrique (Gaussien)."""
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(variance)

        # Approximation du quantile normal
        z_scores = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}
        z = z_scores.get(self.confidence, 2.326)

        var = -(mean - z * std)
        return var * math.sqrt(self.horizon_days)

    def expected_shortfall(self, returns: list[float]) -> float:
        """Expected Shortfall (CVaR) — moyenne des pertes au-delà de la VaR."""
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        cutoff = int((1 - self.confidence) * len(sorted_returns))
        cutoff = max(1, cutoff)
        tail = sorted_returns[:cutoff]
        return -sum(tail) / len(tail) * math.sqrt(self.horizon_days)


class CorrelationMatrix:
    """
    Matrice de corrélation dynamique.

    Calcule les corrélations entre actifs sur des fenêtres glissantes
    pour capturer l'évolution des relations cross-asset.
    """

    def __init__(self, lookback: int = 252) -> None:
        self.lookback = lookback
        self._matrix: dict[tuple[str, str], float] = {}
        self._last_computed: datetime | None = None

    def compute(
        self,
        returns_map: dict[str, list[float]],
    ) -> dict[tuple[str, str], float]:
        """Calcule la matrice de corrélation complète."""
        symbols = list(returns_map.keys())
        self._matrix.clear()

        for i, sym_a in enumerate(symbols):
            for j, sym_b in enumerate(symbols):
                if i <= j:
                    corr = self._pearson(
                        returns_map[sym_a][-self.lookback:],
                        returns_map[sym_b][-self.lookback:],
                    )
                    self._matrix[(sym_a, sym_b)] = corr
                    self._matrix[(sym_b, sym_a)] = corr

        self._last_computed = datetime.now(timezone.utc)
        return dict(self._matrix)

    def get_correlation(self, symbol_a: str, symbol_b: str) -> float | None:
        """Retourne la corrélation entre deux actifs."""
        return self._matrix.get((symbol_a, symbol_b))

    def get_highly_correlated(self, threshold: float = 0.7) -> list[tuple[str, str, float]]:
        """Identifie les paires fortement corrélées."""
        pairs = []
        seen = set()
        for (a, b), corr in self._matrix.items():
            if a != b and (b, a) not in seen and abs(corr) >= threshold:
                pairs.append((a, b, corr))
                seen.add((a, b))
        return sorted(pairs, key=lambda x: abs(x[2]), reverse=True)

    @staticmethod
    def _pearson(x: list[float], y: list[float]) -> float:
        """Calcul du coefficient de corrélation de Pearson."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        x, y = x[:n], y[:n]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x) / n)
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y) / n)

        if std_x == 0 or std_y == 0:
            return 0.0

        return cov / (std_x * std_y)


class StressTest:
    """
    Moteur de stress testing.

    Simule des scénarios extrêmes (crise 2008, flash crash, COVID,
    choc de taux, choc pétrolier) et mesure l'impact sur le portefeuille.
    """

    # Scénarios historiques pré-définis (chocs en %)
    HISTORICAL_SCENARIOS: dict[str, dict[str, float]] = {
        "2008_financial_crisis": {
            "equity": -0.45, "fixed_income": 0.10, "commodity": -0.35,
            "forex_em": -0.25, "volatility": 3.0, "crypto": -0.60,
        },
        "2020_covid_crash": {
            "equity": -0.34, "fixed_income": 0.05, "commodity": -0.30,
            "forex_em": -0.15, "volatility": 4.0, "crypto": -0.50,
        },
        "2022_rate_shock": {
            "equity": -0.25, "fixed_income": -0.15, "commodity": 0.20,
            "forex_em": -0.10, "volatility": 1.5, "crypto": -0.65,
        },
        "oil_shock": {
            "equity": -0.15, "fixed_income": 0.02, "commodity": 0.40,
            "forex_em": -0.20, "volatility": 1.8, "crypto": -0.10,
        },
        "flash_crash": {
            "equity": -0.10, "fixed_income": 0.01, "commodity": -0.05,
            "forex_em": -0.03, "volatility": 2.5, "crypto": -0.20,
        },
        "sovereign_debt_crisis": {
            "equity": -0.20, "fixed_income": -0.08, "commodity": -0.10,
            "forex_em": -0.30, "volatility": 2.0, "crypto": -0.15,
        },
    }

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    def run_scenario(
        self,
        scenario_name: str,
        portfolio_weights: dict[str, float],
        portfolio_value: float,
    ) -> dict[str, Any]:
        """Exécute un scénario de stress sur le portefeuille."""
        scenario = self.HISTORICAL_SCENARIOS.get(scenario_name)
        if scenario is None:
            raise ValueError(f"Scénario inconnu: {scenario_name}")

        total_impact = 0.0
        asset_impacts = {}

        for asset, weight in portfolio_weights.items():
            asset_type = self._classify_asset(asset)
            shock = scenario.get(asset_type, 0.0)
            impact = weight * shock
            total_impact += impact
            asset_impacts[asset] = {
                "weight": weight,
                "shock": shock,
                "impact": impact,
            }

        result = {
            "scenario": scenario_name,
            "total_impact_pct": total_impact,
            "total_impact_value": portfolio_value * total_impact,
            "asset_impacts": asset_impacts,
            "surviving": total_impact > -1.0,
        }

        self._results[scenario_name] = result
        return result

    def run_all_scenarios(
        self,
        portfolio_weights: dict[str, float],
        portfolio_value: float,
    ) -> dict[str, dict[str, Any]]:
        """Exécute tous les scénarios de stress."""
        results = {}
        for name in self.HISTORICAL_SCENARIOS:
            results[name] = self.run_scenario(name, portfolio_weights, portfolio_value)
        return results

    def worst_case(self) -> dict[str, Any] | None:
        """Retourne le pire scénario."""
        if not self._results:
            return None
        return min(
            self._results.values(),
            key=lambda r: r["total_impact_pct"],
        )

    @staticmethod
    def _classify_asset(symbol: str) -> str:
        """Classifie un actif dans une catégorie de stress."""
        symbol_upper = symbol.upper()
        if any(fx in symbol_upper for fx in ["EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]):
            return "forex_em"
        if any(idx in symbol_upper for idx in ["SPX", "NDX", "DAX", "FTSE", "CAC", "NIKKEI", "HSI", "STOXX"]):
            return "equity"
        if any(bond in symbol_upper for bond in ["10Y", "2Y", "30Y", "TIPS"]):
            return "fixed_income"
        if any(cmd in symbol_upper for cmd in ["GOLD", "SILVER", "WTI", "BRENT", "NATGAS", "COPPER", "WHEAT", "CORN"]):
            return "commodity"
        if any(crypto in symbol_upper for crypto in ["BTC", "ETH", "SOL"]):
            return "crypto"
        if any(vol in symbol_upper for vol in ["VIX", "VSTOXX", "VDAX", "MOVE"]):
            return "volatility"
        return "equity"
