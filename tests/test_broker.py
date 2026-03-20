"""Tests du broker IBKR d'O.R.I.O.N."""

from orion.execution.broker import IBKRBroker, BrokerStatus


class TestIBKRBroker:
    def test_initial_state(self):
        broker = IBKRBroker()
        status = broker.get_status()
        assert status["status"] == "disconnected"
        assert status["port"] == 7497
        assert status["host"] == "127.0.0.1"
        assert broker.is_connected is False

    def test_connect_no_tws(self):
        """Tente une connexion quand TWS n'est pas lancé."""
        broker = IBKRBroker(host="127.0.0.1", port=19999)  # Port fermé
        broker.state.reconnect_enabled = False  # Désactiver auto-reconnect pour le test
        result = broker.connect()
        assert result["status"] in ("disconnected", "error")
        assert broker.is_connected is False

    def test_disconnect(self):
        broker = IBKRBroker()
        broker.state.reconnect_enabled = False
        result = broker.disconnect()
        assert result["status"] == "disconnected"
        assert broker.is_connected is False

    def test_custom_config(self):
        broker = IBKRBroker(host="192.168.1.100", port=7496, client_id=5)
        assert broker.state.host == "192.168.1.100"
        assert broker.state.port == 7496
        assert broker.state.client_id == 5

    def test_status_serialization(self):
        broker = IBKRBroker()
        status = broker.get_status()
        assert "status" in status
        assert "account_id" in status
        assert "host" in status
        assert "port" in status
        assert "reconnect_countdown" in status
        assert "last_error" in status

    def test_disconnect_stops_reconnect(self):
        broker = IBKRBroker()
        broker.state.reconnect_enabled = False
        broker.disconnect()
        assert broker.state.reconnect_countdown == 0
        assert broker.state.status == BrokerStatus.DISCONNECTED
