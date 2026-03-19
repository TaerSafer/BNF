"""
O.R.I.O.N. — Point d'entrée principal.

Optimized Rational Intelligence for Orchestrated Navigation
RedRock Capital | Infrastructure d'Intelligence Systémique Intégrée

Lance l'infrastructure complète : initialise les moteurs,
exécute le cycle d'analyse et produit un rapport systémique.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from orion import __version__
from orion.core.config import OrionConfig
from orion.core.engine import OrionEngine
from orion.data.engine import DataEngine
from orion.data.providers import YahooFinanceProvider, FREDProvider, ECBProvider
from orion.risk.engine import RiskEngine
from orion.macro.engine import MacroEngine
from orion.allocation.engine import AllocationEngine
from orion.volatility.engine import VolatilityEngine
from orion.signals.generator import SignalGenerator
from orion.utils.logging import setup_logging

logger = logging.getLogger("orion.main")


BANNER = r"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗                  ║
    ║    ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║                  ║
    ║    ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║                  ║
    ║    ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║                  ║
    ║    ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║                  ║
    ║     ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝                  ║
    ║                                                              ║
    ║    Optimized Rational Intelligence for                       ║
    ║    Orchestrated Navigation                                   ║
    ║                                                              ║
    ║    RedRock Capital — Intelligence Systémique Intégrée        ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
"""


def build_orion(config: OrionConfig) -> OrionEngine:
    """Construit et assemble l'infrastructure O.R.I.O.N."""
    engine = OrionEngine(config)

    # Data Engine
    data_engine = DataEngine(config, engine.event_bus)
    data_engine.register_provider(YahooFinanceProvider())
    data_engine.register_provider(FREDProvider())
    data_engine.register_provider(ECBProvider())
    engine.register_engine(data_engine)

    # Macro Engine
    macro_engine = MacroEngine(config, engine.event_bus)
    engine.register_engine(macro_engine)

    # Volatility Engine
    vol_engine = VolatilityEngine(config, engine.event_bus)
    engine.register_engine(vol_engine)

    # Risk Engine
    risk_engine = RiskEngine(config, engine.event_bus)
    engine.register_engine(risk_engine)

    # Allocation Engine
    alloc_engine = AllocationEngine(config, engine.event_bus)
    engine.register_engine(alloc_engine)

    return engine


def run_diagnostic(engine: OrionEngine) -> dict:
    """Exécute un diagnostic complet du système."""
    status = engine.get_status()
    logger.info("=== Diagnostic O.R.I.O.N. ===")
    logger.info("Version: %s", status["version"])
    logger.info("État: %s", status["state"])
    logger.info("Moteurs enregistrés: %d", len(status["engines"]))
    for name, eng_status in status["engines"].items():
        logger.info("  - %s: %s", name, eng_status["state"])
    return status


def main() -> None:
    """Point d'entrée CLI d'O.R.I.O.N."""
    parser = argparse.ArgumentParser(
        description="O.R.I.O.N. — RedRock Capital Systemic Intelligence",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Chemin vers le fichier de configuration JSON",
    )
    parser.add_argument(
        "--log-level", "-l",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de logging",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Exécute un diagnostic système",
    )
    parser.add_argument(
        "--cycle",
        action="store_true",
        help="Exécute un cycle d'analyse complet",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Exporte les résultats en JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"O.R.I.O.N. v{__version__}",
    )

    args = parser.parse_args()

    # Setup
    setup_logging(level=args.log_level)
    print(BANNER)
    logger.info("O.R.I.O.N. v%s — Démarrage...", __version__)

    # Configuration
    if args.config:
        config = OrionConfig.from_file(args.config)
    else:
        config = OrionConfig()

    # Construction
    engine = build_orion(config)

    try:
        # Initialisation
        engine.initialize()

        if args.diagnostic:
            run_diagnostic(engine)
            return

        if args.cycle:
            logger.info("Exécution du cycle d'analyse...")
            results = engine.run_cycle()

            if args.export:
                with open(args.export, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                logger.info("Résultats exportés: %s", args.export)
            else:
                print(json.dumps(results, indent=2, default=str))
            return

        # Mode par défaut : diagnostic
        run_diagnostic(engine)

    except KeyboardInterrupt:
        logger.info("Interruption utilisateur")
    finally:
        engine.shutdown()
        logger.info("O.R.I.O.N. arrêté.")


if __name__ == "__main__":
    main()
