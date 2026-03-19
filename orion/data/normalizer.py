"""
Normalisation des données d'O.R.I.O.N.

Transforme les données brutes multi-source en un format unifié,
gère les valeurs manquantes, les outliers, et l'alignement temporel.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from orion.data.providers import MarketDataPoint, DataCategory

logger = logging.getLogger("orion.data.normalizer")


@dataclass
class NormalizationStats:
    """Statistiques de normalisation pour un symbole."""
    symbol: str
    mean: float
    std: float
    min_val: float
    max_val: float
    count: int
    missing_count: int
    outlier_count: int


class DataNormalizer:
    """
    Normalise et aligne les données multi-source.

    Gère :
    - Détection et interpolation des valeurs manquantes
    - Identification et traitement des outliers (méthode IQR/Z-score)
    - Alignement temporel cross-asset
    - Calcul des rendements (log-returns, simple returns)
    - Normalisation Z-score pour comparaison inter-actifs
    """

    def __init__(
        self,
        outlier_z_threshold: float = 3.5,
        interpolation_method: str = "linear",
    ) -> None:
        self.outlier_z_threshold = outlier_z_threshold
        self.interpolation_method = interpolation_method
        self._stats: dict[str, NormalizationStats] = {}

    def normalize_series(
        self,
        data: list[MarketDataPoint],
        field: str = "close",
    ) -> list[MarketDataPoint]:
        """Normalise une série de données (Z-score)."""
        if not data:
            return []

        values = [d.values.get(field, 0.0) for d in data]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 1.0

        normalized = []
        outlier_count = 0
        for point in data:
            val = point.values.get(field, 0.0)
            z_score = (val - mean) / std

            if abs(z_score) > self.outlier_z_threshold:
                outlier_count += 1
                z_score = max(-self.outlier_z_threshold,
                              min(self.outlier_z_threshold, z_score))

            new_values = dict(point.values)
            new_values[f"{field}_zscore"] = z_score
            new_values[f"{field}_normalized"] = (val - mean) / std

            normalized.append(MarketDataPoint(
                symbol=point.symbol,
                timestamp=point.timestamp,
                category=point.category,
                values=new_values,
                source=point.source,
                frequency=point.frequency,
                metadata=point.metadata,
            ))

        if data:
            self._stats[data[0].symbol] = NormalizationStats(
                symbol=data[0].symbol,
                mean=mean,
                std=std,
                min_val=min(values),
                max_val=max(values),
                count=len(values),
                missing_count=0,
                outlier_count=outlier_count,
            )

        return normalized

    def compute_returns(
        self,
        data: list[MarketDataPoint],
        field: str = "close",
        log_returns: bool = True,
    ) -> list[dict[str, Any]]:
        """Calcule les rendements d'une série."""
        if len(data) < 2:
            return []

        returns = []
        for i in range(1, len(data)):
            prev_val = data[i - 1].values.get(field, 0.0)
            curr_val = data[i].values.get(field, 0.0)

            if prev_val == 0:
                continue

            if log_returns:
                ret = math.log(curr_val / prev_val)
            else:
                ret = (curr_val - prev_val) / prev_val

            returns.append({
                "timestamp": data[i].timestamp,
                "symbol": data[i].symbol,
                "return": ret,
                "price": curr_val,
            })

        return returns

    def align_timestamps(
        self,
        series_map: dict[str, list[MarketDataPoint]],
    ) -> dict[str, list[MarketDataPoint]]:
        """
        Aligne temporellement plusieurs séries de données.
        Conserve uniquement les timestamps communs à toutes les séries.
        """
        if not series_map:
            return {}

        # Trouver les timestamps communs
        timestamp_sets = [
            {p.timestamp for p in series}
            for series in series_map.values()
            if series
        ]

        if not timestamp_sets:
            return {}

        common_timestamps = set.intersection(*timestamp_sets)

        aligned = {}
        for symbol, series in series_map.items():
            aligned[symbol] = sorted(
                [p for p in series if p.timestamp in common_timestamps],
                key=lambda p: p.timestamp,
            )

        logger.info(
            "Alignement: %d timestamps communs sur %d séries",
            len(common_timestamps),
            len(series_map),
        )

        return aligned

    def fill_missing(
        self,
        data: list[MarketDataPoint],
        field: str = "close",
    ) -> list[MarketDataPoint]:
        """Interpole les valeurs manquantes (forward fill)."""
        if not data:
            return []

        filled = []
        last_valid: float | None = None

        for point in data:
            val = point.values.get(field)
            if val is None or math.isnan(val):
                if last_valid is not None:
                    new_values = dict(point.values)
                    new_values[field] = last_valid
                    new_values["_interpolated"] = 1.0
                    filled.append(MarketDataPoint(
                        symbol=point.symbol,
                        timestamp=point.timestamp,
                        category=point.category,
                        values=new_values,
                        source=point.source,
                        frequency=point.frequency,
                        metadata=point.metadata,
                    ))
                continue

            last_valid = val
            filled.append(point)

        return filled

    def get_stats(self, symbol: str) -> NormalizationStats | None:
        """Retourne les statistiques de normalisation."""
        return self._stats.get(symbol)
