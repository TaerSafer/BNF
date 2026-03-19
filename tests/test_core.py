"""Tests du noyau O.R.I.O.N."""

from orion.core.config import OrionConfig, AssetClass, RiskConfig, MacroConfig
from orion.core.events import EventBus, Event, EventType
from orion.core.registry import ComponentRegistry
from orion.core.engine import OrionEngine


class TestOrionConfig:
    def test_default_config(self):
        config = OrionConfig()
        assert config.name == "O.R.I.O.N."
        assert config.institution == "RedRock Capital"
        assert len(config.asset_classes) == len(AssetClass)
        assert "forex" in config.universe
        assert "equity" in config.universe
        assert "crypto" in config.universe

    def test_risk_config_defaults(self):
        config = OrionConfig()
        assert config.risk.var_confidence == 0.99
        assert config.risk.max_drawdown_threshold == 0.10

    def test_serialization(self):
        config = OrionConfig()
        data = config.to_dict()
        assert data["name"] == "O.R.I.O.N."
        assert "risk" in data
        assert "universe" in data

    def test_universe_multi_asset(self):
        config = OrionConfig()
        total_assets = sum(len(v) for v in config.universe.values())
        assert total_assets > 30


class TestEventBus:
    def test_emit_and_subscribe(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.DATA_UPDATED, handler)
        bus.emit(Event(type=EventType.DATA_UPDATED, source="test", data={"x": 1}))

        assert len(received) == 1
        assert received[0].source == "test"

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.DATA_UPDATED, handler)
        bus.unsubscribe(EventType.DATA_UPDATED, handler)
        bus.emit(Event(type=EventType.DATA_UPDATED, source="test"))

        assert len(received) == 0

    def test_history(self):
        bus = EventBus()
        bus.emit(Event(type=EventType.HEARTBEAT, source="test"))
        bus.emit(Event(type=EventType.HEARTBEAT, source="test"))

        history = bus.get_history(EventType.HEARTBEAT)
        assert len(history) == 2

    def test_error_in_handler_doesnt_crash(self):
        bus = EventBus()

        def bad_handler(event):
            raise ValueError("boom")

        bus.subscribe(EventType.DATA_UPDATED, bad_handler)
        # Should not raise
        bus.emit(Event(type=EventType.DATA_UPDATED, source="test"))


class TestComponentRegistry:
    def test_register_and_get(self):
        reg = ComponentRegistry()
        reg.register("test_component", {"value": 42})
        assert reg.get("test_component")["value"] == 42
        assert reg.has("test_component")

    def test_list_components(self):
        reg = ComponentRegistry()
        reg.register("a", 1)
        reg.register("b", 2)
        assert sorted(reg.list_components()) == ["a", "b"]


class TestOrionEngine:
    def test_engine_creation(self):
        engine = OrionEngine()
        assert engine.state.value == "idle"
        assert engine.config.name == "O.R.I.O.N."

    def test_status(self):
        engine = OrionEngine()
        status = engine.get_status()
        assert status["name"] == "O.R.I.O.N."
        assert status["state"] == "idle"
        assert status["cycle_count"] == 0
