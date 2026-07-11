"""Unit tests for time-series transforms (src/indicators/transforms.py)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.transforms import (
    compute_credit_impulse,
    compute_growth_rate,
    compute_yoy_change,
    compute_zscore,
    detect_frequency,
    detect_regime,
    resample_to_frequency,
    align_series,
    standardize_series,
)


def df_of(values, freq="W-FRI", start="2020-01-03"):
    dates = pd.date_range(start, periods=len(values), freq=freq)
    return pd.DataFrame({"date": dates, "value": np.asarray(values, dtype=float)})


class TestComputeZscore:
    def test_rolling_zscore_matches_manual_calculation(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30]
        df = compute_zscore(df_of(values), window=4, min_periods=4)

        # z at the last point uses the last 4 values [8, 9, 10, 20, 30] -> window 4 -> [9,10,20,30]
        tail = pd.Series([9.0, 10.0, 20.0, 30.0])
        expected = (30.0 - tail.mean()) / tail.std()
        assert df["zscore"].iloc[-1] == pytest.approx(expected)

    def test_expanding_zscore_uses_full_history(self):
        values = list(range(1, 31))
        df = compute_zscore(df_of(values), min_periods=20)

        full = pd.Series(values, dtype=float)
        expected = (30.0 - full.mean()) / full.std()
        assert df["zscore"].iloc[-1] == pytest.approx(expected)

    def test_min_periods_leaves_warmup_nan(self):
        df = compute_zscore(df_of(range(30)), min_periods=20)
        assert df["zscore"].iloc[:19].isna().all()
        assert pd.notna(df["zscore"].iloc[19])

    def test_zscore_of_constant_series_is_nan_not_inf(self):
        df = compute_zscore(df_of([5.0] * 40), min_periods=20)
        assert not np.isinf(df["zscore"].dropna()).any()


class TestDetectRegime:
    def test_classifies_against_thresholds(self):
        df = df_of([0] * 5)
        df["zscore"] = [-2.0, -1.0, 0.0, 1.0, 2.0]
        out = detect_regime(df, thresholds=(-1.0, 1.0))
        # Strict inequalities: -1.0 and 1.0 are neutral
        assert out["regime"].tolist() == [-1, 0, 0, 0, 1]

    def test_computes_zscore_when_missing(self):
        df = df_of(list(range(60)))
        out = detect_regime(df)
        assert "regime" in out.columns
        assert out.loc[out["zscore"].isna(), "regime"].isna().all()
        assert set(out["regime"].dropna().unique()).issubset({-1, 0, 1})

    def test_non_finite_zscores_remain_unclassified(self):
        df = df_of([0] * 6)
        df["zscore"] = [np.nan, np.inf, -np.inf, -2.0, 0.0, 2.0]

        out = detect_regime(df, thresholds=(-1.0, 1.0))

        assert out["regime"].iloc[:3].isna().all()
        assert out["regime"].iloc[3:].tolist() == [-1.0, 0.0, 1.0]


class TestForwardLookingSafety:
    def test_zscore_has_no_lookahead(self):
        """Past z-scores must not change when future data changes."""
        base = list(range(1, 61))
        a = compute_zscore(df_of(base), min_periods=10)
        b = compute_zscore(df_of(base[:50] + [999] * 10), min_periods=10)
        pd.testing.assert_series_equal(a["zscore"].iloc[:50], b["zscore"].iloc[:50])


class TestResample:
    def test_daily_to_weekly_takes_last_observation(self):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")  # two weeks
        df = pd.DataFrame({"date": dates, "value": range(10)})
        out = resample_to_frequency(df, "W", agg_method="last")
        assert len(out) == 2
        assert out["value"].tolist() == [4.0, 9.0]
        # Weekly buckets anchor on Friday
        assert all(d.weekday() == 4 for d in out["date"])

    def test_mean_aggregation(self):
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        df = pd.DataFrame({"date": dates, "value": [1, 2, 3, 4, 5]})
        out = resample_to_frequency(df, "W", agg_method="mean")
        assert out["value"].iloc[0] == pytest.approx(3.0)


class TestGrowthAndYoY:
    def test_yoy_change_monthly(self):
        # 10% growth year over year, monthly data
        values = [100] * 12 + [110] * 12
        df = df_of(values, freq="ME", start="2020-01-31")
        out = compute_yoy_change(df, periods=12)
        assert out["yoy_change"].iloc[-1] == pytest.approx(10.0)

    def test_growth_rate_pct_method(self):
        values = [100] * 52 + [120] * 52
        df = df_of(values)
        out = compute_growth_rate(df, periods=52, method="pct")
        assert out["growth_rate"].iloc[-1] == pytest.approx(20.0)

    def test_growth_rate_log_method(self):
        values = [100] * 52 + [120] * 52
        df = df_of(values)
        out = compute_growth_rate(df, periods=52, method="log")
        assert out["growth_rate"].iloc[-1] == pytest.approx(np.log(1.2) * 100)

    def test_percentage_transforms_do_not_implicitly_fill_missing_values(self):
        df = df_of([100.0, np.nan, 110.0])

        growth = compute_growth_rate(df, periods=1, method="pct")
        yoy = compute_yoy_change(df, periods=1)

        assert growth["growth_rate"].iloc[1:].isna().all()
        assert yoy["yoy_change"].iloc[1:].isna().all()


class TestCreditImpulse:
    def test_linear_growth_has_constant_flow_and_zero_impulse(self):
        # Credit grows by exactly 5 per quarter -> flow constant, impulse 0
        values = [100 + 5 * i for i in range(20)]
        df = df_of(values, freq="QE", start="2019-03-31")
        out = compute_credit_impulse(df, periods=4)
        assert out["credit_flow"].iloc[-1] == pytest.approx(20.0)  # 4 quarters * 5
        assert out["credit_impulse"].iloc[-1] == pytest.approx(0.0)

    def test_accelerating_credit_has_positive_impulse(self):
        # Quadratic growth -> accelerating flow -> positive impulse
        values = [100 + i**2 for i in range(20)]
        df = df_of(values, freq="QE", start="2019-03-31")
        out = compute_credit_impulse(df, periods=4)
        assert out["credit_impulse"].iloc[-1] > 0


class TestAlignSeries:
    def test_outer_join_forward_fills(self):
        a = df_of([1, 2, 3], freq="W-FRI")
        b = df_of([10, 20], freq="W-FRI")
        out = align_series({"a": a, "b": b}, method="outer", fill_method="ffill")
        assert len(out) == 3
        assert out["b"].iloc[-1] == pytest.approx(20.0)  # forward-filled

    def test_inner_join_intersects_dates(self):
        a = df_of([1, 2, 3], freq="W-FRI")
        b = df_of([10, 20], freq="W-FRI")
        out = align_series({"a": a, "b": b}, method="inner")
        assert len(out) == 2

    def test_empty_inner_intersection_is_not_reset_by_later_series(self):
        a = df_of([1, 2], freq="D", start="2024-01-01")
        b = df_of([10, 20], freq="D", start="2024-02-01")
        # This overlaps b, which used to replace the already-empty a/b
        # intersection because DataFrame.empty was used as initialization
        # state.
        c = df_of([100, 200], freq="D", start="2024-02-01")

        out = align_series(
            {"a": a, "b": b, "c": c},
            method="inner",
            fill_method=None,
        )

        assert out.empty
        assert out.columns.tolist() == ["date", "a", "b", "c"]


class TestStandardize:
    def test_minmax_bounded_zero_one(self):
        df = standardize_series(df_of(list(range(50))), method="minmax")
        s = df["standardized"].dropna()
        assert s.min() >= 0.0 and s.max() <= 1.0

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            standardize_series(df_of(range(30)), method="bogus")


class TestDetectFrequency:
    @pytest.mark.parametrize("freq,expected", [
        ("D", "D"), ("W-FRI", "W"), ("ME", "M"), ("QE", "Q"), ("YE", "A"),
    ])
    def test_detects_common_frequencies(self, freq, expected):
        df = df_of(range(12), freq=freq)
        assert detect_frequency(df) == expected
