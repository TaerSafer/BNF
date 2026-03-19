"""Tests du moteur d'exécution O.R.I.O.N."""

from orion.core.config import OrionConfig
from orion.core.events import EventBus
from orion.execution.engine import ExecutionEngine, OrderSide, OrderStatus


class TestExecutionEngine:
    def setup_method(self):
        config = OrionConfig()
        bus = EventBus()
        self.engine = ExecutionEngine(config, bus)
        self.engine.initialize()

    def test_initial_state(self):
        data = self.engine.get_dashboard_data()
        assert data["portfolio_value"] == 100_000.0
        assert data["auto_trade"] is False
        assert len(data["open_positions"]) == 0

    def test_auto_trade_toggle(self):
        self.engine.auto_trade = True
        assert self.engine.auto_trade is True
        self.engine.auto_trade = False
        assert self.engine.auto_trade is False

    def test_process_signals_when_off(self):
        signals = {"SPX": {"score": 0.5, "type": "overweight", "price": 5000}}
        orders = self.engine.process_signals(signals)
        assert len(orders) == 0  # Auto trade is off

    def test_process_signals_when_on(self):
        self.engine.auto_trade = True
        signals = {"SPX": {"score": 0.5, "type": "overweight", "price": 5000}}
        orders = self.engine.process_signals(signals)
        assert len(orders) == 1
        assert orders[0].status == OrderStatus.FILLED
        assert "SPX" in self.engine.get_positions()

    def test_weak_signal_ignored(self):
        self.engine.auto_trade = True
        signals = {"SPX": {"score": 0.1, "type": "neutral", "price": 5000}}
        orders = self.engine.process_signals(signals)
        assert len(orders) == 0

    def test_close_position(self):
        self.engine.auto_trade = True
        self.engine.process_signals({"SPX": {"score": 0.5, "type": "overweight", "price": 5000}})
        assert "SPX" in self.engine.get_positions()

        order = self.engine._close_position("SPX", 5100)
        assert order is not None
        assert "SPX" not in self.engine.get_positions()
        assert len(self.engine.get_trade_history()) == 1

    def test_stop_loss(self):
        self.engine.auto_trade = True
        self.engine.process_signals({"SPX": {"score": 0.5, "type": "overweight", "price": 100}})
        pos = self.engine.get_positions()["SPX"]
        sl_price = pos.stop_loss

        orders = self.engine.check_stop_loss_take_profit({"SPX": sl_price - 1})
        assert len(orders) == 1
        assert "SPX" not in self.engine.get_positions()

    def test_trade_stats(self):
        self.engine.auto_trade = True
        # Open and close a winning trade
        self.engine.process_signals({"GOLD": {"score": 0.5, "type": "overweight", "price": 2000}})
        self.engine._close_position("GOLD", 2100)

        stats = self.engine._compute_stats()
        assert stats["total_trades"] == 1
        assert stats["win_rate"] == 100.0
