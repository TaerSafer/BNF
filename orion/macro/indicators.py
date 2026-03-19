"""
Indicateurs macro-économiques d'O.R.I.O.N.

Panel d'indicateurs avancés, coïncidents et retardés pour
la lecture systémique de l'état de l'économie mondiale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class IndicatorType(Enum):
    """Classification des indicateurs."""
    LEADING = "leading"          # Avancés — prédictifs
    COINCIDENT = "coincident"    # Coïncidents — temps réel
    LAGGING = "lagging"          # Retardés — confirmatifs


class IndicatorRegion(Enum):
    """Régions économiques."""
    US = "us"
    EU = "eu"
    UK = "uk"
    JP = "jp"
    CN = "cn"
    GLOBAL = "global"


@dataclass
class MacroIndicator:
    """Un indicateur macro-économique."""
    name: str
    code: str
    indicator_type: IndicatorType
    region: IndicatorRegion
    current_value: float = 0.0
    previous_value: float = 0.0
    historical: list[tuple[datetime, float]] = field(default_factory=list)
    unit: str = ""
    description: str = ""

    @property
    def change(self) -> float:
        if self.previous_value == 0:
            return 0.0
        return (self.current_value - self.previous_value) / abs(self.previous_value)

    @property
    def trend(self) -> str:
        if len(self.historical) < 3:
            return "insufficient_data"
        recent = [v for _, v in self.historical[-6:]]
        if all(recent[i] >= recent[i - 1] for i in range(1, len(recent))):
            return "rising"
        if all(recent[i] <= recent[i - 1] for i in range(1, len(recent))):
            return "falling"
        return "mixed"

    @property
    def signal(self) -> float:
        """Signal normalisé [-1, 1] basé sur la dynamique de l'indicateur."""
        if len(self.historical) < 6:
            return 0.0
        values = [v for _, v in self.historical[-12:]]
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        deviation = (self.current_value - mean) / abs(mean)
        return max(-1.0, min(1.0, deviation))


class IndicatorPanel:
    """
    Panel d'indicateurs macro-économiques.

    Agrège les signaux de multiples indicateurs pour produire
    une lecture unifiée de l'état économique.
    """

    # Catalogue des indicateurs clés
    INDICATOR_CATALOG: dict[str, dict[str, Any]] = {
        # Leading indicators (avancés)
        "yield_curve_slope": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.US,
            "description": "Pente de la courbe des taux (10Y - 2Y)",
            "unit": "bps",
        },
        "pmi_manufacturing": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.GLOBAL,
            "description": "PMI manufacturier global",
            "unit": "index",
        },
        "building_permits": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.US,
            "description": "Permis de construire",
            "unit": "thousands",
        },
        "consumer_expectations": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.US,
            "description": "Attentes des consommateurs",
            "unit": "index",
        },
        "credit_spreads": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.US,
            "description": "Spreads de crédit HY vs IG",
            "unit": "bps",
        },
        "m2_money_supply": {
            "type": IndicatorType.LEADING,
            "region": IndicatorRegion.US,
            "description": "Masse monétaire M2 (variation annuelle)",
            "unit": "pct",
        },

        # Coincident indicators (coïncidents)
        "gdp_growth": {
            "type": IndicatorType.COINCIDENT,
            "region": IndicatorRegion.US,
            "description": "Croissance du PIB (annualisée)",
            "unit": "pct",
        },
        "industrial_production": {
            "type": IndicatorType.COINCIDENT,
            "region": IndicatorRegion.US,
            "description": "Production industrielle",
            "unit": "index",
        },
        "nonfarm_payrolls": {
            "type": IndicatorType.COINCIDENT,
            "region": IndicatorRegion.US,
            "description": "Créations d'emplois non-agricoles",
            "unit": "thousands",
        },
        "retail_sales": {
            "type": IndicatorType.COINCIDENT,
            "region": IndicatorRegion.US,
            "description": "Ventes au détail",
            "unit": "pct_change",
        },

        # Lagging indicators (retardés)
        "unemployment_rate": {
            "type": IndicatorType.LAGGING,
            "region": IndicatorRegion.US,
            "description": "Taux de chômage",
            "unit": "pct",
        },
        "cpi_inflation": {
            "type": IndicatorType.LAGGING,
            "region": IndicatorRegion.US,
            "description": "Inflation CPI (YoY)",
            "unit": "pct",
        },
        "core_pce": {
            "type": IndicatorType.LAGGING,
            "region": IndicatorRegion.US,
            "description": "Core PCE (YoY)",
            "unit": "pct",
        },
        "fed_funds_rate": {
            "type": IndicatorType.LAGGING,
            "region": IndicatorRegion.US,
            "description": "Taux directeur de la Fed",
            "unit": "pct",
        },
    }

    def __init__(self) -> None:
        self._indicators: dict[str, MacroIndicator] = {}
        self._initialize_catalog()

    def _initialize_catalog(self) -> None:
        """Initialise les indicateurs depuis le catalogue."""
        for code, meta in self.INDICATOR_CATALOG.items():
            self._indicators[code] = MacroIndicator(
                name=meta["description"],
                code=code,
                indicator_type=meta["type"],
                region=meta["region"],
                unit=meta.get("unit", ""),
                description=meta["description"],
            )

    def update_indicator(
        self,
        code: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Met à jour la valeur d'un indicateur."""
        if code not in self._indicators:
            return
        indicator = self._indicators[code]
        indicator.previous_value = indicator.current_value
        indicator.current_value = value
        ts = timestamp or datetime.now(timezone.utc)
        indicator.historical.append((ts, value))

    def get_composite_signal(self) -> dict[str, float]:
        """
        Calcule un signal composite par type d'indicateur.

        Retourne un score [-1, 1] pour chaque catégorie :
        - leading : signal avancé (prédictif)
        - coincident : signal temps réel
        - lagging : signal de confirmation
        """
        signals: dict[str, list[float]] = {
            "leading": [],
            "coincident": [],
            "lagging": [],
        }

        for indicator in self._indicators.values():
            sig = indicator.signal
            if sig != 0.0:
                signals[indicator.indicator_type.value].append(sig)

        composite = {}
        for category, sigs in signals.items():
            composite[category] = sum(sigs) / len(sigs) if sigs else 0.0

        return composite

    def get_indicators_by_type(self, indicator_type: IndicatorType) -> list[MacroIndicator]:
        """Retourne les indicateurs d'un type donné."""
        return [
            ind for ind in self._indicators.values()
            if ind.indicator_type == indicator_type
        ]

    def get_indicator(self, code: str) -> MacroIndicator | None:
        return self._indicators.get(code)

    def get_all_signals(self) -> dict[str, float]:
        """Retourne le signal de chaque indicateur."""
        return {code: ind.signal for code, ind in self._indicators.items()}
