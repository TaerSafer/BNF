"""
Configuration centrale d'O.R.I.O.N.

Gère tous les paramètres système : sources de données, seuils de risque,
univers d'actifs, régimes de marché et paramètres d'allocation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AssetClass(Enum):
    """Classes d'actifs supportées par O.R.I.O.N."""
    FX = "forex"
    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    VOLATILITY = "volatility"


class MarketRegime(Enum):
    """Régimes de marché identifiables."""
    EXPANSION = "expansion"
    CONTRACTION = "contraction"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    STAGNATION = "stagnation"
    EUPHORIA = "euphoria"


@dataclass
class RiskConfig:
    """Paramètres du moteur de risque."""
    max_portfolio_var: float = 0.02
    max_single_position: float = 0.05
    correlation_lookback_days: int = 252
    var_confidence: float = 0.99
    stress_test_scenarios: int = 1000
    max_drawdown_threshold: float = 0.10
    liquidity_buffer: float = 0.15
    rebalance_threshold: float = 0.05


@dataclass
class MacroConfig:
    """Paramètres du moteur macro-économique."""
    cycle_detection_window: int = 60
    regime_lookback_months: int = 36
    leading_indicators_weight: float = 0.4
    coincident_indicators_weight: float = 0.35
    lagging_indicators_weight: float = 0.25
    regime_change_sensitivity: float = 0.7


@dataclass
class AllocationConfig:
    """Paramètres du moteur d'allocation adaptative."""
    optimization_method: str = "mean_variance"
    risk_parity_target: bool = True
    min_asset_weight: float = 0.0
    max_asset_weight: float = 0.30
    turnover_penalty: float = 0.001
    rebalance_frequency_days: int = 5
    regime_adaptation_speed: float = 0.3


@dataclass
class DataConfig:
    """Configuration des sources de données."""
    cache_directory: str = ".orion_cache"
    history_depth_years: int = 20
    update_frequency_minutes: int = 15
    supported_providers: list[str] = field(
        default_factory=lambda: ["yahoo", "fred", "ecb", "bis"]
    )


@dataclass
class OrionConfig:
    """Configuration maîtresse d'O.R.I.O.N."""

    # Identité
    name: str = "O.R.I.O.N."
    version: str = "0.1.0"
    institution: str = "RedRock Capital"

    # Univers d'actifs
    asset_classes: list[AssetClass] = field(
        default_factory=lambda: list(AssetClass)
    )

    # Sous-configurations
    risk: RiskConfig = field(default_factory=RiskConfig)
    macro: MacroConfig = field(default_factory=MacroConfig)
    allocation: AllocationConfig = field(default_factory=AllocationConfig)
    data: DataConfig = field(default_factory=DataConfig)

    # Univers par défaut
    universe: dict[str, list[str]] = field(default_factory=lambda: {
        "forex": [
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
            "AUD/USD", "USD/CAD", "NZD/USD", "EUR/GBP",
            "EUR/JPY", "GBP/JPY"
        ],
        "equity": [
            "SPX", "NDX", "DJIA", "DAX", "FTSE100",
            "CAC40", "NIKKEI225", "HSI", "STOXX600"
        ],
        "fixed_income": [
            "US10Y", "US2Y", "DE10Y", "JP10Y", "GB10Y",
            "US30Y", "TIPS10Y"
        ],
        "commodity": [
            "GOLD", "SILVER", "WTI", "BRENT", "NATGAS",
            "COPPER", "WHEAT", "CORN"
        ],
        "crypto": [
            "BTC/USD", "ETH/USD", "SOL/USD"
        ],
        "volatility": [
            "VIX", "VSTOXX", "VDAX", "MOVE"
        ]
    })

    @classmethod
    def from_file(cls, path: str | Path) -> OrionConfig:
        """Charge la configuration depuis un fichier JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> OrionConfig:
        config = cls()
        if "risk" in data:
            config.risk = RiskConfig(**data["risk"])
        if "macro" in data:
            config.macro = MacroConfig(**data["macro"])
        if "allocation" in data:
            config.allocation = AllocationConfig(**data["allocation"])
        if "data" in data:
            config.data = DataConfig(**data["data"])
        if "universe" in data:
            config.universe = data["universe"]
        return config

    def to_dict(self) -> dict[str, Any]:
        """Sérialise la configuration."""
        from dataclasses import asdict
        return {
            "name": self.name,
            "version": self.version,
            "institution": self.institution,
            "risk": asdict(self.risk),
            "macro": asdict(self.macro),
            "allocation": asdict(self.allocation),
            "data": asdict(self.data),
            "universe": self.universe,
        }

    def save(self, path: str | Path) -> None:
        """Sauvegarde la configuration."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
