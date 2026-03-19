"""
Fournisseurs de données d'O.R.I.O.N.

Abstraction des sources de données : marchés, macro-économie,
volatilité, flux institutionnels. Chaque provider implémente
l'interface commune pour une intégration transparente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DataFrequency(Enum):
    """Fréquences de données supportées."""
    TICK = "tick"
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    HOURLY = "1h"
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1m"


class DataCategory(Enum):
    """Catégories de données."""
    PRICE = "price"
    VOLUME = "volume"
    MACRO = "macro"
    SENTIMENT = "sentiment"
    FLOW = "flow"
    VOLATILITY = "volatility"
    RATE = "rate"


@dataclass
class MarketDataPoint:
    """Point de donnée de marché normalisé."""
    symbol: str
    timestamp: datetime
    category: DataCategory
    values: dict[str, float]
    source: str
    frequency: DataFrequency = DataFrequency.DAILY
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def price(self) -> float | None:
        return self.values.get("close") or self.values.get("value")

    @property
    def is_valid(self) -> bool:
        return bool(self.values) and self.timestamp is not None


@dataclass
class OHLCVData:
    """Données OHLCV standard."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = ""

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    def to_market_data(self) -> MarketDataPoint:
        return MarketDataPoint(
            symbol=self.symbol,
            timestamp=self.timestamp,
            category=DataCategory.PRICE,
            values={
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
            },
            source=self.source,
        )


class DataProvider(ABC):
    """Interface abstraite pour les fournisseurs de données."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Établit la connexion au fournisseur."""

    @abstractmethod
    def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.DAILY,
    ) -> list[MarketDataPoint]:
        """Récupère des données historiques."""

    @abstractmethod
    def fetch_latest(self, symbol: str) -> MarketDataPoint | None:
        """Récupère la dernière donnée disponible."""

    @abstractmethod
    def get_available_symbols(self) -> list[str]:
        """Liste les symboles disponibles."""

    def disconnect(self) -> None:
        """Ferme la connexion."""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class YahooFinanceProvider(DataProvider):
    """Provider Yahoo Finance pour données de marché."""

    def __init__(self) -> None:
        super().__init__("yahoo_finance")

    def connect(self) -> bool:
        # L'intégration réelle utilisera yfinance
        self._connected = True
        return True

    def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.DAILY,
    ) -> list[MarketDataPoint]:
        # Stub — implémentation avec yfinance à venir
        return []

    def fetch_latest(self, symbol: str) -> MarketDataPoint | None:
        return None

    def get_available_symbols(self) -> list[str]:
        return []


class FREDProvider(DataProvider):
    """Provider FRED (Federal Reserve Economic Data) pour données macro."""

    SERIES_MAP = {
        "GDP": "GDP",
        "CPI": "CPIAUCSL",
        "UNEMPLOYMENT": "UNRATE",
        "FED_FUNDS": "FEDFUNDS",
        "US10Y": "DGS10",
        "US2Y": "DGS2",
        "M2": "M2SL",
        "INDUSTRIAL_PROD": "INDPRO",
        "RETAIL_SALES": "RSAFS",
        "HOUSING_STARTS": "HOUST",
        "PMI": "MANEMP",
        "CONSUMER_SENTIMENT": "UMCSENT",
    }

    def __init__(self) -> None:
        super().__init__("fred")

    def connect(self) -> bool:
        self._connected = True
        return True

    def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.DAILY,
    ) -> list[MarketDataPoint]:
        # Stub — implémentation avec fredapi à venir
        return []

    def fetch_latest(self, symbol: str) -> MarketDataPoint | None:
        return None

    def get_available_symbols(self) -> list[str]:
        return list(self.SERIES_MAP.keys())


class ECBProvider(DataProvider):
    """Provider BCE pour données de taux et monétaires européennes."""

    def __init__(self) -> None:
        super().__init__("ecb")

    def connect(self) -> bool:
        self._connected = True
        return True

    def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.DAILY,
    ) -> list[MarketDataPoint]:
        return []

    def fetch_latest(self, symbol: str) -> MarketDataPoint | None:
        return None

    def get_available_symbols(self) -> list[str]:
        return ["EONIA", "EURIBOR_3M", "EURIBOR_6M", "ECB_MAIN_RATE"]
