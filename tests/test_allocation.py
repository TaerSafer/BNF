"""Tests du moteur d'allocation O.R.I.O.N."""

import math
from orion.allocation.optimizer import PortfolioOptimizer


class TestPortfolioOptimizer:
    def setup_method(self):
        self.optimizer = PortfolioOptimizer(min_weight=0.0, max_weight=0.40)
        self.assets = ["SPX", "GOLD", "US10Y", "EUR/USD", "BTC/USD"]

    def test_equal_weight(self):
        result = self.optimizer.equal_weight(self.assets)
        assert result.is_valid
        assert abs(sum(result.weights.values()) - 1.0) < 1e-10
        for w in result.weights.values():
            assert abs(w - 0.2) < 1e-10

    def test_risk_parity(self):
        vols = {"SPX": 0.15, "GOLD": 0.12, "US10Y": 0.06, "EUR/USD": 0.08, "BTC/USD": 0.60}
        result = self.optimizer.risk_parity(self.assets, vols)
        assert result.is_valid
        # Less volatile assets should have higher weight
        assert result.weights["US10Y"] > result.weights["BTC/USD"]

    def test_mean_variance(self):
        returns = {"SPX": 0.10, "GOLD": 0.05, "US10Y": 0.03, "EUR/USD": 0.02, "BTC/USD": 0.20}
        vols = {"SPX": 0.15, "GOLD": 0.12, "US10Y": 0.06, "EUR/USD": 0.08, "BTC/USD": 0.60}
        result = self.optimizer.mean_variance(self.assets, returns, vols)
        assert result.is_valid
        assert result.expected_return != 0

    def test_regime_adaptive(self):
        regime_profile = {"equity": 0.30, "commodity": 0.20, "fixed_income": 0.30,
                          "forex": 0.10, "crypto": 0.10}
        vols = {"SPX": 0.15, "GOLD": 0.12, "US10Y": 0.06, "EUR/USD": 0.08, "BTC/USD": 0.60}
        classification = {"SPX": "equity", "GOLD": "commodity", "US10Y": "fixed_income",
                          "EUR/USD": "forex", "BTC/USD": "crypto"}
        result = self.optimizer.regime_adaptive(
            self.assets, regime_profile, vols, classification
        )
        assert result.is_valid

    def test_constraints_respected(self):
        vols = {"SPX": 0.01, "GOLD": 0.50, "US10Y": 0.50, "EUR/USD": 0.50, "BTC/USD": 0.50}
        result = self.optimizer.risk_parity(self.assets, vols)
        for w in result.weights.values():
            assert w <= self.optimizer.max_weight + 1e-10

    def test_empty_assets(self):
        result = self.optimizer.equal_weight([])
        assert result.weights == {}
