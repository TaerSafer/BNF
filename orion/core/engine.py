"""
Moteur principal d'O.R.I.O.N.

Orchestrateur central qui initialise, coordonne et supervise
tous les sous-systèmes de l'intelligence systémique.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from orion.core.config import OrionConfig
from orion.core.events import Event, EventBus, EventType
from orion.core.registry import ComponentRegistry

logger = logging.getLogger("orion.engine")


class EngineState(Enum):
    """États du moteur."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class BaseEngine(ABC):
    """Classe de base pour tous les moteurs O.R.I.O.N."""

    def __init__(self, name: str, config: OrionConfig, event_bus: EventBus) -> None:
        self.name = name
        self.config = config
        self.event_bus = event_bus
        self.state = EngineState.IDLE
        self.logger = logging.getLogger(f"orion.{name}")

    @abstractmethod
    def initialize(self) -> None:
        """Initialise le moteur."""

    @abstractmethod
    def run_cycle(self) -> dict[str, Any]:
        """Exécute un cycle d'analyse."""

    @abstractmethod
    def shutdown(self) -> None:
        """Arrête proprement le moteur."""

    def get_status(self) -> dict[str, Any]:
        """Retourne l'état du moteur."""
        return {
            "name": self.name,
            "state": self.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class OrionEngine:
    """
    Moteur principal — Orchestrateur d'O.R.I.O.N.

    Coordonne l'exécution séquentielle et parallèle des sous-moteurs,
    gère le flux de données entre les composants, et maintient
    la cohérence systémique de l'ensemble.
    """

    def __init__(self, config: OrionConfig | None = None) -> None:
        self.config = config or OrionConfig()
        self.event_bus = EventBus()
        self.registry = ComponentRegistry()
        self.state = EngineState.IDLE
        self._engines: dict[str, BaseEngine] = {}
        self._cycle_count = 0

        logger.info(
            "O.R.I.O.N. v%s — %s — Initialisation",
            self.config.version,
            self.config.institution,
        )

    def register_engine(self, engine: BaseEngine) -> None:
        """Enregistre un sous-moteur dans l'orchestrateur."""
        self._engines[engine.name] = engine
        self.registry.register(
            engine.name, engine, type="engine", state=engine.state.value
        )
        logger.info("Moteur enregistré: %s", engine.name)

    def initialize(self) -> None:
        """Initialise tous les sous-moteurs."""
        self.state = EngineState.INITIALIZING
        logger.info("Initialisation de %d moteurs...", len(self._engines))

        for name, engine in self._engines.items():
            try:
                engine.initialize()
                engine.state = EngineState.RUNNING
                logger.info("Moteur '%s' initialisé", name)
            except Exception:
                engine.state = EngineState.ERROR
                logger.exception("Erreur d'initialisation: %s", name)
                raise

        self.state = EngineState.RUNNING
        self.event_bus.emit(Event(
            type=EventType.ENGINE_STARTED,
            source="orion.master",
            data={"engines": list(self._engines.keys())},
        ))

    def run_cycle(self) -> dict[str, Any]:
        """
        Exécute un cycle complet d'analyse O.R.I.O.N.

        Ordre d'exécution :
        1. Data Engine — Ingestion et normalisation des données
        2. Macro Engine — Analyse des régimes et cycles
        3. Volatility Engine — Calcul des volatilités et corrélations
        4. Risk Engine — Évaluation des risques
        5. Allocation Engine — Optimisation de l'allocation
        """
        self._cycle_count += 1
        cycle_results: dict[str, Any] = {
            "cycle": self._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "engines": {},
        }

        execution_order = [
            "data", "macro", "volatility", "risk", "allocation"
        ]

        for engine_name in execution_order:
            if engine_name not in self._engines:
                continue
            engine = self._engines[engine_name]
            if engine.state != EngineState.RUNNING:
                logger.warning(
                    "Moteur '%s' non actif (état: %s), ignoré",
                    engine_name, engine.state.value,
                )
                continue

            try:
                result = engine.run_cycle()
                cycle_results["engines"][engine_name] = result
            except Exception:
                logger.exception("Erreur dans le cycle de '%s'", engine_name)
                cycle_results["engines"][engine_name] = {"error": True}

        self.event_bus.emit(Event(
            type=EventType.HEARTBEAT,
            source="orion.master",
            data={"cycle": self._cycle_count},
        ))

        return cycle_results

    def get_status(self) -> dict[str, Any]:
        """Retourne l'état complet du système."""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "institution": self.config.institution,
            "state": self.state.value,
            "cycle_count": self._cycle_count,
            "engines": {
                name: engine.get_status()
                for name, engine in self._engines.items()
            },
        }

    def shutdown(self) -> None:
        """Arrêt propre de tous les moteurs."""
        logger.info("Arrêt d'O.R.I.O.N....")
        for name, engine in reversed(list(self._engines.items())):
            try:
                engine.shutdown()
                engine.state = EngineState.SHUTDOWN
                logger.info("Moteur '%s' arrêté", name)
            except Exception:
                logger.exception("Erreur lors de l'arrêt de '%s'", name)

        self.state = EngineState.SHUTDOWN
        self.event_bus.emit(Event(
            type=EventType.ENGINE_STOPPED,
            source="orion.master",
        ))
