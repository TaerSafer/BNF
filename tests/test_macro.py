"""Tests du moteur macro-économique O.R.I.O.N."""

from datetime import datetime, timezone
from orion.macro.indicators import IndicatorPanel, IndicatorType
from orion.macro.regimes import RegimeDetector, EconomicRegime
from orion.macro.cycles import CycleAnalyzer, CycleType


class TestIndicatorPanel:
    def test_initialization(self):
        panel = IndicatorPanel()
        leading = panel.get_indicators_by_type(IndicatorType.LEADING)
        assert len(leading) > 0

    def test_update_and_signal(self):
        panel = IndicatorPanel()
        for i in range(12):
            panel.update_indicator("gdp_growth", 2.0 + i * 0.1)
        indicator = panel.get_indicator("gdp_growth")
        assert indicator is not None
        assert indicator.current_value > 2.0

    def test_composite_signal(self):
        panel = IndicatorPanel()
        composite = panel.get_composite_signal()
        assert "leading" in composite
        assert "coincident" in composite
        assert "lagging" in composite


class TestRegimeDetector:
    def test_detect_expansion(self):
        detector = RegimeDetector()
        state = detector.detect({
            "leading": 0.5,
            "coincident": 0.4,
            "lagging": -0.1,
        })
        assert state.regime == EconomicRegime.EARLY_EXPANSION

    def test_detect_crisis(self):
        detector = RegimeDetector()
        state = detector.detect({
            "leading": -0.8,
            "coincident": -0.7,
            "lagging": -0.5,
        })
        assert state.regime == EconomicRegime.CRISIS

    def test_asset_profile(self):
        detector = RegimeDetector()
        profile = detector.get_asset_profile(EconomicRegime.CRISIS)
        assert profile["equity"] == 0.0
        assert profile["volatility_long"] > 0

    def test_transition_probabilities(self):
        detector = RegimeDetector()
        detector.detect({"leading": 0.5, "coincident": 0.3, "lagging": 0.0})
        probs = detector.get_transition_probabilities()
        assert len(probs) > 0
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01


class TestCycleAnalyzer:
    def test_analyze_current(self):
        analyzer = CycleAnalyzer()
        snapshot = analyzer.analyze()
        assert len(snapshot.phases) == 5
        assert CycleType.KITCHIN in snapshot.phases
        assert CycleType.KONDRATIEV in snapshot.phases

    def test_composite_score_bounded(self):
        analyzer = CycleAnalyzer()
        snapshot = analyzer.analyze()
        assert -1.0 <= snapshot.composite_score <= 1.0

    def test_dominant_cycle(self):
        analyzer = CycleAnalyzer()
        snapshot = analyzer.analyze()
        dominant = analyzer.get_dominant_cycle(snapshot)
        assert dominant is not None
        assert 0.0 <= dominant.position <= 1.0

    def test_convergence_zones(self):
        analyzer = CycleAnalyzer()
        analyzer.analyze()
        zones = analyzer.get_convergence_zones()
        # May or may not have convergence, just verify structure
        for zone in zones:
            assert "type" in zone
            assert "strength" in zone
