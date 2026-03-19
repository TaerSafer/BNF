"""Tests du moteur de risque O.R.I.O.N."""

import math
from orion.risk.models import VaRModel, CorrelationMatrix, StressTest, RiskMetrics


class TestVaRModel:
    def test_historical_var(self):
        model = VaRModel(confidence=0.95)
        returns = [-0.05, -0.03, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05,
                   0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.04, 0.02,
                   0.01, -0.01, 0.03, 0.02]
        var = model.historical_var(returns)
        assert var > 0

    def test_parametric_var(self):
        model = VaRModel(confidence=0.99)
        returns = [0.01, -0.01, 0.02, -0.02, 0.01, -0.01, 0.005, -0.005]
        var = model.parametric_var(returns)
        assert var > 0

    def test_expected_shortfall(self):
        model = VaRModel(confidence=0.95)
        returns = [-0.05, -0.03, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05,
                   0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.04, 0.02,
                   0.01, -0.01, 0.03, 0.02]
        cvar = model.expected_shortfall(returns)
        var = model.historical_var(returns)
        assert cvar >= var  # CVaR >= VaR by definition

    def test_empty_returns(self):
        model = VaRModel()
        assert model.historical_var([]) == 0.0
        assert model.parametric_var([]) == 0.0
        assert model.expected_shortfall([]) == 0.0


class TestCorrelationMatrix:
    def test_perfect_correlation(self):
        returns_a = [0.01, 0.02, 0.03, 0.04, 0.05]
        returns_b = [0.01, 0.02, 0.03, 0.04, 0.05]
        corr = CorrelationMatrix._pearson(returns_a, returns_b)
        assert abs(corr - 1.0) < 1e-10

    def test_negative_correlation(self):
        returns_a = [0.01, 0.02, 0.03, 0.04, 0.05]
        returns_b = [-0.01, -0.02, -0.03, -0.04, -0.05]
        corr = CorrelationMatrix._pearson(returns_a, returns_b)
        assert abs(corr - (-1.0)) < 1e-10

    def test_compute_matrix(self):
        matrix = CorrelationMatrix(lookback=10)
        returns = {
            "A": [0.01, 0.02, -0.01, 0.03, 0.01],
            "B": [-0.01, 0.01, 0.02, -0.01, 0.02],
        }
        result = matrix.compute(returns)
        assert ("A", "A") in result
        assert abs(result[("A", "A")] - 1.0) < 1e-10


class TestStressTest:
    def test_run_scenario(self):
        st = StressTest()
        weights = {"SPX": 0.5, "GOLD": 0.3, "US10Y": 0.2}
        result = st.run_scenario("2008_financial_crisis", weights, 1_000_000)
        assert result["total_impact_pct"] < 0
        assert result["surviving"]

    def test_run_all_scenarios(self):
        st = StressTest()
        weights = {"SPX": 0.4, "GOLD": 0.3, "US10Y": 0.3}
        results = st.run_all_scenarios(weights, 1_000_000)
        assert len(results) == len(StressTest.HISTORICAL_SCENARIOS)

    def test_worst_case(self):
        st = StressTest()
        weights = {"SPX": 0.5, "BTC/USD": 0.3, "WTI": 0.2}
        st.run_all_scenarios(weights, 1_000_000)
        worst = st.worst_case()
        assert worst is not None
        assert worst["total_impact_pct"] < 0


class TestRiskMetrics:
    def test_within_limits(self):
        metrics = RiskMetrics(portfolio_var=0.01, current_drawdown=0.05)
        assert metrics.is_within_limits(0.02, 0.10)
        assert not metrics.is_within_limits(0.005, 0.10)
