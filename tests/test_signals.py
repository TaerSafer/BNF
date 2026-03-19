"""Tests du générateur de signaux O.R.I.O.N."""

from orion.signals.generator import SignalGenerator, SignalType, SignalStrength


class TestSignalGenerator:
    def test_generate_bullish(self):
        gen = SignalGenerator()
        signal = gen.generate(
            "SPX",
            macro_score=0.5,
            volatility_score=0.3,
            cycle_score=0.4,
            risk_score=0.2,
            momentum_score=0.3,
        )
        assert signal.signal_type == SignalType.OVERWEIGHT
        assert signal.score > 0

    def test_generate_bearish(self):
        gen = SignalGenerator()
        signal = gen.generate(
            "SPX",
            macro_score=-0.5,
            volatility_score=-0.3,
            cycle_score=-0.4,
            risk_score=-0.2,
            momentum_score=-0.3,
        )
        assert signal.signal_type == SignalType.UNDERWEIGHT
        assert signal.score < 0

    def test_generate_neutral(self):
        gen = SignalGenerator()
        signal = gen.generate("SPX", macro_score=0.0)
        assert signal.signal_type == SignalType.NEUTRAL

    def test_generate_all(self):
        gen = SignalGenerator()
        assets = ["SPX", "GOLD", "EUR/USD"]
        macro = {"SPX": 0.5, "GOLD": -0.2, "EUR/USD": 0.1}
        signals = gen.generate_all(assets, macro_scores=macro)
        assert len(signals) == 3
        assert signals["SPX"].score > signals["GOLD"].score

    def test_top_and_bottom_signals(self):
        gen = SignalGenerator()
        gen.generate("A", macro_score=0.8)
        gen.generate("B", macro_score=-0.8)
        gen.generate("C", macro_score=0.0)

        top = gen.get_top_signals(2)
        bottom = gen.get_bottom_signals(2)
        assert top[0].symbol == "A"
        assert bottom[0].symbol == "B"

    def test_confidence_convergence(self):
        gen = SignalGenerator()
        # All sources agree
        signal_agree = gen.generate(
            "X", macro_score=0.5, volatility_score=0.3,
            cycle_score=0.4, risk_score=0.2, momentum_score=0.3,
        )
        # Sources disagree
        signal_disagree = gen.generate(
            "Y", macro_score=0.5, volatility_score=-0.5,
            cycle_score=0.3, risk_score=-0.3, momentum_score=0.1,
        )
        assert signal_agree.confidence > signal_disagree.confidence
