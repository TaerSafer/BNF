"""
Data Engine d'O.R.I.O.N.

Moteur d'ingestion et de gestion des données. Orchestre les providers,
normalise les flux, maintient le cache et alimente les autres moteurs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from orion.core.config import OrionConfig
from orion.core.engine import BaseEngine, EngineState
from orion.core.events import Event, EventBus, EventType
from orion.data.normalizer import DataNormalizer
from orion.data.providers import (
    DataProvider,
    MarketDataPoint,
    DataFrequency,
    DataCategory,
)

logger = logging.getLogger("orion.data")


class DataEngine(BaseEngine):
    """
    Moteur de données — Cœur informatif d'O.R.I.O.N.

    Responsabilités :
    - Agrégation multi-source (marchés, macro, volatilité)
    - Normalisation et alignement temporel
    - Cache intelligent et gestion de l'historique
    - Alimentation des moteurs en aval
    """

    def __init__(self, config: OrionConfig, event_bus: EventBus) -> None:
        super().__init__("data", config, event_bus)
        self._providers: dict[str, DataProvider] = {}
        self._normalizer = DataNormalizer()
        self._cache: dict[str, list[MarketDataPoint]] = {}
        self._last_update: dict[str, datetime] = {}

    def register_provider(self, provider: DataProvider) -> None:
        """Enregistre un fournisseur de données."""
        self._providers[provider.name] = provider
        self.logger.info("Provider enregistré: %s", provider.name)

    def initialize(self) -> None:
        """Connecte tous les providers."""
        for name, provider in self._providers.items():
            try:
                provider.connect()
                self.logger.info("Provider '%s' connecté", name)
            except Exception:
                self.logger.exception("Échec de connexion: %s", name)

        self.state = EngineState.RUNNING

    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'ingestion de données."""
        results: dict[str, Any] = {
            "updated_symbols": [],
            "errors": [],
            "cache_size": len(self._cache),
        }

        for asset_class, symbols in self.config.universe.items():
            for symbol in symbols:
                try:
                    data = self._fetch_symbol(symbol)
                    if data:
                        self._cache[symbol] = data
                        self._last_update[symbol] = datetime.now(timezone.utc)
                        results["updated_symbols"].append(symbol)
                except Exception as e:
                    results["errors"].append({"symbol": symbol, "error": str(e)})

        self.event_bus.emit(Event(
            type=EventType.DATA_UPDATED,
            source="data",
            data={"symbols_updated": len(results["updated_symbols"])},
        ))

        return results

    def _fetch_symbol(self, symbol: str) -> list[MarketDataPoint]:
        """Récupère les données pour un symbole depuis les providers disponibles."""
        for provider in self._providers.values():
            if not provider.is_connected:
                continue
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=self.config.data.history_depth_years * 365)
            data = provider.fetch_historical(symbol, start, end)
            if data:
                return self._normalizer.normalize_series(data)
        return []

    def get_data(self, symbol: str) -> list[MarketDataPoint]:
        """Récupère les données en cache pour un symbole."""
        return self._cache.get(symbol, [])

    def get_latest(self, symbol: str) -> MarketDataPoint | None:
        """Récupère le dernier point de données."""
        data = self._cache.get(symbol, [])
        return data[-1] if data else None

    def get_returns(
        self,
        symbol: str,
        log_returns: bool = True,
    ) -> list[dict[str, Any]]:
        """Calcule les rendements pour un symbole."""
        data = self._cache.get(symbol, [])
        return self._normalizer.compute_returns(data, log_returns=log_returns)

    def get_aligned_data(
        self,
        symbols: list[str],
    ) -> dict[str, list[MarketDataPoint]]:
        """Récupère des données alignées pour plusieurs symboles."""
        series = {s: self._cache.get(s, []) for s in symbols if s in self._cache}
        return self._normalizer.align_timestamps(series)

    def shutdown(self) -> None:
        """Déconnecte tous les providers."""
        for provider in self._providers.values():
            provider.disconnect()
        self.state = EngineState.SHUTDOWN
