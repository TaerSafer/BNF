"""
Modèles de volatilité d'O.R.I.O.N.

Implémente EWMA, GARCH simplifié, et la surface de volatilité
pour capturer la structure temporelle et cross-asset de la volatilité.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.volatility.models")


class VolatilityRegime(Enum):
    """Régimes de volatilité."""
    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class VolatilitySnapshot:
    """Instantané de volatilité pour un actif."""
    symbol: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    realized_vol: float = 0.0
    ewma_vol: float = 0.0
    vol_of_vol: float = 0.0
    regime: VolatilityRegime = VolatilityRegime.NORMAL
    percentile: float = 0.5
    term_structure: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "realized_vol": self.realized_vol,
            "ewma_vol": self.ewma_vol,
            "vol_of_vol": self.vol_of_vol,
            "regime": self.regime.value,
            "percentile": self.percentile,
        }


class VolatilityModel:
    """
    Modèle de volatilité multi-méthode.

    Calcule la volatilité réalisée, EWMA et des proxies GARCH
    pour chaque actif de l'univers.
    """

    # Seuils de régime (volatilité annualisée)
    REGIME_THRESHOLDS = {
        VolatilityRegime.LOW: 0.08,
        VolatilityRegime.NORMAL: 0.15,
        VolatilityRegime.ELEVATED: 0.25,
        VolatilityRegime.HIGH: 0.40,
        VolatilityRegime.EXTREME: float("inf"),
    }

    def __init__(self, ewma_lambda: float = 0.94) -> None:
        self.ewma_lambda = ewma_lambda
        self._history: dict[str, list[VolatilitySnapshot]] = {}

    def realized_volatility(
        self,
        returns: list[float],
        window: int = 21,
        annualize: bool = True,
    ) -> float:
        """Volatilité réalisée (écart-type des rendements)."""
        if len(returns) < 2:
            return 0.0
        data = returns[-window:]
        mean = sum(data) / len(data)
        variance = sum((r - mean) ** 2 for r in data) / (len(data) - 1)
        vol = math.sqrt(variance)
        return vol * math.sqrt(252) if annualize else vol

    def ewma_volatility(
        self,
        returns: list[float],
        annualize: bool = True,
    ) -> float:
        """Volatilité EWMA (Exponentially Weighted Moving Average)."""
        if len(returns) < 2:
            return 0.0

        variance = returns[0] ** 2
        for r in returns[1:]:
            variance = self.ewma_lambda * variance + (1 - self.ewma_lambda) * r ** 2

        vol = math.sqrt(variance)
        return vol * math.sqrt(252) if annualize else vol

    def volatility_of_volatility(
        self,
        returns: list[float],
        vol_window: int = 21,
        lookback: int = 252,
    ) -> float:
        """Volatilité de la volatilité — mesure l'instabilité du risque."""
        if len(returns) < vol_window + 10:
            return 0.0

        rolling_vols = []
        data = returns[-lookback:]
        for i in range(vol_window, len(data)):
            window_data = data[i - vol_window:i]
            mean = sum(window_data) / len(window_data)
            var = sum((r - mean) ** 2 for r in window_data) / len(window_data)
            rolling_vols.append(math.sqrt(var))

        if len(rolling_vols) < 2:
            return 0.0

        mean_vol = sum(rolling_vols) / len(rolling_vols)
        var_of_vol = sum((v - mean_vol) ** 2 for v in rolling_vols) / len(rolling_vols)
        return math.sqrt(var_of_vol)

    def classify_regime(self, volatility: float) -> VolatilityRegime:
        """Classifie le régime de volatilité."""
        for regime, threshold in self.REGIME_THRESHOLDS.items():
            if volatility < threshold:
                return regime
        return VolatilityRegime.EXTREME

    def compute_percentile(
        self,
        current_vol: float,
        historical_vols: list[float],
    ) -> float:
        """Calcule le percentile de la volatilité courante vs historique."""
        if not historical_vols:
            return 0.5
        count_below = sum(1 for v in historical_vols if v <= current_vol)
        return count_below / len(historical_vols)

    def compute_term_structure(
        self,
        returns: list[float],
        windows: list[int] | None = None,
    ) -> dict[int, float]:
        """Calcule la structure par terme de la volatilité."""
        windows = windows or [5, 10, 21, 63, 126, 252]
        structure = {}
        for w in windows:
            if len(returns) >= w:
                structure[w] = self.realized_volatility(returns, window=w)
        return structure

    def full_analysis(
        self,
        symbol: str,
        returns: list[float],
    ) -> VolatilitySnapshot:
        """Analyse complète de volatilité pour un actif."""
        realized = self.realized_volatility(returns)
        ewma = self.ewma_volatility(returns)
        vol_vol = self.volatility_of_volatility(returns)
        regime = self.classify_regime(ewma)
        term_structure = self.compute_term_structure(returns)

        # Calculer le percentile sur les volatilités historiques
        historical_vols = []
        for i in range(21, len(returns)):
            window = returns[i - 21:i]
            mean = sum(window) / len(window)
            var = sum((r - mean) ** 2 for r in window) / len(window)
            historical_vols.append(math.sqrt(var) * math.sqrt(252))

        percentile = self.compute_percentile(realized, historical_vols)

        snapshot = VolatilitySnapshot(
            symbol=symbol,
            realized_vol=realized,
            ewma_vol=ewma,
            vol_of_vol=vol_vol,
            regime=regime,
            percentile=percentile,
            term_structure=term_structure,
        )

        if symbol not in self._history:
            self._history[symbol] = []
        self._history[symbol].append(snapshot)

        return snapshot


class VolatilitySurface:
    """
    Surface de volatilité cross-asset.

    Cartographie la volatilité à travers les actifs et le temps
    pour identifier les dislocations et les opportunités.
    """

    def __init__(self) -> None:
        self._surface: dict[str, VolatilitySnapshot] = {}

    def update(self, snapshot: VolatilitySnapshot) -> None:
        """Met à jour la surface avec un nouveau snapshot."""
        self._surface[snapshot.symbol] = snapshot

    def get_regime_distribution(self) -> dict[VolatilityRegime, list[str]]:
        """Distribution des actifs par régime de volatilité."""
        distribution: dict[VolatilityRegime, list[str]] = {r: [] for r in VolatilityRegime}
        for symbol, snapshot in self._surface.items():
            distribution[snapshot.regime].append(symbol)
        return distribution

    def get_extreme_assets(self, percentile_threshold: float = 0.9) -> list[str]:
        """Identifie les actifs en volatilité extrême."""
        return [
            symbol for symbol, snap in self._surface.items()
            if snap.percentile >= percentile_threshold
        ]

    def get_mean_regime(self) -> VolatilityRegime:
        """Régime de volatilité moyen du portefeuille."""
        if not self._surface:
            return VolatilityRegime.NORMAL
        avg_vol = sum(s.ewma_vol for s in self._surface.values()) / len(self._surface)
        thresholds = VolatilityModel.REGIME_THRESHOLDS
        for regime, threshold in thresholds.items():
            if avg_vol < threshold:
                return regime
        return VolatilityRegime.EXTREME

    def get_snapshot(self, symbol: str) -> VolatilitySnapshot | None:
        return self._surface.get(symbol)

    def get_all_snapshots(self) -> dict[str, VolatilitySnapshot]:
        return dict(self._surface)
