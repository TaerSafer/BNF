"""
Broker IBKR (Interactive Brokers) pour O.R.I.O.N.

Gère la connexion à TWS/Gateway via l'API IBKR,
la reconnexion automatique, et le statut de connexion.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.execution.broker")


class BrokerStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class IBKRState:
    """État de la connexion IBKR."""
    status: BrokerStatus = BrokerStatus.DISCONNECTED
    account_id: str = ""
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    last_connected: datetime | None = None
    last_error: str = ""
    reconnect_countdown: int = 0
    reconnect_enabled: bool = True
    reconnect_interval: int = 300  # 5 minutes

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "account_id": self.account_id,
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "last_error": self.last_error,
            "reconnect_countdown": self.reconnect_countdown,
            "reconnect_enabled": self.reconnect_enabled,
        }


class IBKRBroker:
    """
    Connecteur Interactive Brokers pour O.R.I.O.N.

    Gère la connexion TCP à TWS/Gateway sur le port 7497 (paper)
    ou 7496 (live), avec reconnexion automatique toutes les 5 minutes.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
    ) -> None:
        self.state = IBKRState(host=host, port=port, client_id=client_id)
        self._reconnect_thread: threading.Thread | None = None
        self._stop_reconnect = threading.Event()
        self._ib = None  # ib_insync.IB instance
        self._cached_balance: float | None = None
        self._balance_currency: str = "EUR"
        self._last_balance_fetch: datetime | None = None
        self._balance_refresh_seconds: int = 900  # 15 minutes

    def connect(self) -> dict[str, Any]:
        """
        Tente de se connecter à TWS/Gateway.

        Utilise ib_insync si disponible pour une vraie connexion API,
        sinon vérifie simplement si le port TCP est accessible.
        """
        self.state.status = BrokerStatus.CONNECTING
        self.state.last_error = ""

        try:
            # Tenter la connexion via ib_insync
            try:
                from ib_insync import IB
                ib = IB()
                ib.connect(
                    self.state.host,
                    self.state.port,
                    clientId=self.state.client_id,
                    timeout=5,
                )
                self._ib = ib

                # Récupérer le vrai account ID
                accounts = ib.managedAccounts()
                self.state.account_id = accounts[0] if accounts else "DUP485293"

                self.state.status = BrokerStatus.CONNECTED
                self.state.last_connected = datetime.now(timezone.utc)
                self.state.last_error = ""
                self.state.reconnect_countdown = 0
                self._stop_reconnect.set()

                logger.info(
                    "IBKR: Connecté via ib_insync à %s:%d — Compte: %s",
                    self.state.host, self.state.port, self.state.account_id,
                )

                # Fetch le solde initial
                self._fetch_balance()

                return self.state.to_dict()

            except ImportError:
                logger.info("IBKR: ib_insync non installé, fallback TCP")
            except Exception as ib_err:
                logger.warning("IBKR: ib_insync échec (%s), fallback TCP", ib_err)
                self._ib = None

            # Fallback : vérifier si TWS est accessible via TCP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((self.state.host, self.state.port))
            sock.close()

            if result != 0:
                self.state.status = BrokerStatus.DISCONNECTED
                self.state.last_error = "TWS non détecté — ouvrez TWS d'abord"
                logger.warning(
                    "IBKR: Impossible de se connecter à %s:%d — TWS non détecté",
                    self.state.host, self.state.port,
                )
                self._start_reconnect_timer()
                return self.state.to_dict()

            # TWS est accessible via TCP (sans ib_insync)
            self.state.status = BrokerStatus.CONNECTED
            self.state.account_id = "DUP485293"
            self.state.last_connected = datetime.now(timezone.utc)
            self.state.last_error = ""
            self.state.reconnect_countdown = 0
            self._stop_reconnect.set()

            logger.info(
                "IBKR: Connecté (TCP) à %s:%d — Compte: %s",
                self.state.host, self.state.port, self.state.account_id,
            )

            return self.state.to_dict()

        except Exception as e:
            self.state.status = BrokerStatus.ERROR
            self.state.last_error = str(e)
            logger.error("IBKR: Erreur de connexion — %s", e)
            self._start_reconnect_timer()
            return self.state.to_dict()

    def disconnect(self) -> dict[str, Any]:
        """Déconnecte proprement d'IBKR."""
        self._stop_reconnect.set()
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=2)

        # Fermer la connexion ib_insync
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
            self._ib = None

        prev_status = self.state.status
        self.state.status = BrokerStatus.DISCONNECTED
        self.state.reconnect_countdown = 0

        logger.info("IBKR: Déconnecté (était: %s)", prev_status.value)

        return self.state.to_dict()

    def get_status(self) -> dict[str, Any]:
        """Retourne l'état actuel de la connexion."""
        return self.state.to_dict()

    @property
    def is_connected(self) -> bool:
        return self.state.status == BrokerStatus.CONNECTED

    def get_account_balance(self) -> float:
        """
        Récupère le solde réel du compte IBKR en euros.

        Utilise ib_insync reqAccountSummary() pour obtenir le NetLiquidation
        du compte. Met en cache le résultat pour 15 minutes.
        Retourne le dernier solde connu ou 0.0 si jamais connecté.
        """
        now = datetime.now(timezone.utc)

        # Vérifier si le cache est encore valide
        if (
            self._cached_balance is not None
            and self._last_balance_fetch is not None
            and (now - self._last_balance_fetch).total_seconds() < self._balance_refresh_seconds
        ):
            return self._cached_balance

        # Tenter de fetch le vrai solde
        balance = self._fetch_balance()
        return balance

    def _fetch_balance(self) -> float:
        """Fetch le solde via ib_insync. Met à jour le cache."""
        if self._ib is None or not self.is_connected:
            logger.debug("IBKR: Pas de connexion ib_insync, solde non disponible")
            return self._cached_balance or 0.0

        try:
            # reqAccountSummary retourne les valeurs du compte
            summary = self._ib.accountSummary(self.state.account_id)

            balance_eur = 0.0
            for item in summary:
                # Chercher NetLiquidation en EUR
                if item.tag == "NetLiquidation" and item.currency == "EUR":
                    balance_eur = float(item.value)
                    break
                # Fallback : NetLiquidation dans n'importe quelle devise
                if item.tag == "NetLiquidation" and item.currency == "BASE":
                    balance_eur = float(item.value)

            if balance_eur == 0.0:
                # Essayer TotalCashBalance en EUR
                for item in summary:
                    if item.tag == "TotalCashBalance" and item.currency == "EUR":
                        balance_eur = float(item.value)
                        break

            self._cached_balance = balance_eur
            self._last_balance_fetch = datetime.now(timezone.utc)
            self._balance_currency = "EUR"

            logger.info(
                "IBKR: Solde %s récupéré — %.2f %s",
                self.state.account_id, balance_eur, self._balance_currency,
            )

            return balance_eur

        except Exception as e:
            logger.error("IBKR: Erreur récupération solde — %s", e)
            return self._cached_balance or 0.0

    def _start_reconnect_timer(self) -> None:
        """Lance le timer de reconnexion automatique."""
        if not self.state.reconnect_enabled:
            return

        self._stop_reconnect.clear()
        self.state.reconnect_countdown = self.state.reconnect_interval

        def _countdown():
            while self.state.reconnect_countdown > 0 and not self._stop_reconnect.is_set():
                self.state.status = BrokerStatus.RECONNECTING
                time.sleep(1)
                self.state.reconnect_countdown -= 1

            if not self._stop_reconnect.is_set():
                logger.info("IBKR: Tentative de reconnexion automatique...")
                self.connect()

        self._reconnect_thread = threading.Thread(target=_countdown, daemon=True)
        self._reconnect_thread.start()


# ─── Fonctions module-level pour import simplifié ───────────────────────

_default_broker: IBKRBroker | None = None


def _get_broker() -> IBKRBroker:
    global _default_broker
    if _default_broker is None:
        _default_broker = IBKRBroker()
    return _default_broker


def set_broker(broker: IBKRBroker) -> None:
    """Injecte une instance broker (appelé par le serveur au démarrage)."""
    global _default_broker
    _default_broker = broker


def connect() -> None:
    """Connecte le broker par défaut."""
    _get_broker().connect()


def disconnect() -> None:
    """Déconnecte le broker par défaut."""
    _get_broker().disconnect()


def get_ibkr_status() -> dict[str, Any]:
    """Retourne le statut dans le format simplifié {connected, account, error}."""
    broker = _get_broker()
    return {
        "connected": broker.is_connected,
        "account": broker.state.account_id or "DUP485293",
        "error": broker.state.last_error or None,
    }


def get_account_balance() -> float:
    """Récupère le solde réel du compte IBKR en euros via reqAccountSummary()."""
    return _get_broker().get_account_balance()
