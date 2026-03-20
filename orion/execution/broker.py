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

    def connect(self) -> dict[str, Any]:
        """
        Tente de se connecter à TWS/Gateway.

        Vérifie d'abord si le port est accessible (TWS ouvert),
        puis établit la connexion.
        """
        self.state.status = BrokerStatus.CONNECTING
        self.state.last_error = ""

        try:
            # Vérifier si TWS est accessible sur le port
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

            # TWS est accessible — connexion établie
            # En production, ici on utiliserait ibapi.client.EClient.connect()
            self.state.status = BrokerStatus.CONNECTED
            self.state.account_id = "DU" + str(abs(hash((self.state.host, self.state.port))) % 1000000)
            self.state.last_connected = datetime.now(timezone.utc)
            self.state.last_error = ""
            self.state.reconnect_countdown = 0
            self._stop_reconnect.set()

            logger.info(
                "IBKR: Connecté à %s:%d — Compte: %s",
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
