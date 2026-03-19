"""Tests du moteur de volatilité O.R.I.O.N."""

import math
import random
from orion.volatility.models import VolatilityModel, VolatilitySurface, VolatilityRegime


class TestVolatilityModel:
    def setup_method(self):
        self.model = VolatilityModel()
        random.seed(42)
        self.returns = [random.gauss(0, 0.01) for _ in range(300)]

    def test_realized_vol(self):
        vol = self.model.realized_volatility(self.returns, window=21)
        assert vol > 0
        assert vol < 1.0  # Annualized vol should be reasonable

    def test_ewma_vol(self):
        vol = self.model.ewma_volatility(self.returns)
        assert vol > 0

    def test_vol_of_vol(self):
        vov = self.model.volatility_of_volatility(self.returns)
        assert vov >= 0

    def test_regime_classification(self):
        assert self.model.classify_regime(0.05) == VolatilityRegime.LOW
        assert self.model.classify_regime(0.12) == VolatilityRegime.NORMAL
        assert self.model.classify_regime(0.20) == VolatilityRegime.ELEVATED
        assert self.model.classify_regime(0.35) == VolatilityRegime.HIGH
        assert self.model.classify_regime(0.50) == VolatilityRegime.EXTREME

    def test_full_analysis(self):
        snapshot = self.model.full_analysis("TEST", self.returns)
        assert snapshot.symbol == "TEST"
        assert snapshot.realized_vol > 0
        assert snapshot.ewma_vol > 0
        assert snapshot.regime in VolatilityRegime

    def test_term_structure(self):
        ts = self.model.compute_term_structure(self.returns)
        assert 21 in ts
        assert 252 in ts
        # Longer windows should give more stable estimates
        assert ts[5] != ts[252]


class TestVolatilitySurface:
    def test_regime_distribution(self):
        model = VolatilityModel()
        surface = VolatilitySurface()

        random.seed(42)
        for symbol in ["A", "B", "C"]:
            returns = [random.gauss(0, 0.01) for _ in range(100)]
            snapshot = model.full_analysis(symbol, returns)
            surface.update(snapshot)

        dist = surface.get_regime_distribution()
        total = sum(len(v) for v in dist.values())
        assert total == 3

    def test_mean_regime(self):
        surface = VolatilitySurface()
        assert surface.get_mean_regime() == VolatilityRegime.NORMAL
