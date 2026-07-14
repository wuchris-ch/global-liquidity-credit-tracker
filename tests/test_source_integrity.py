"""Offline checks for source identity, period dating, and availability timing."""

import pandas as pd
import pytest

from src.config import get_all_series, get_index_config
from src.data_sources.bis import BISClient
from src.data_sources.worldbank import WorldBankClient
from src.etl.fetcher import DataFetcher, SourceContractError
from src.indicators.factors import FeatureMatrixBuilder


class _FakeFredClient:
    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata
        self.info_calls = 0
        self.series_calls = 0

    def get_series_info(self, _series_id: str) -> dict:
        self.info_calls += 1
        return self.metadata.copy()

    def get_series(
        self,
        series_id: str,
        _start_date: str | None = None,
        _end_date: str | None = None,
    ) -> pd.DataFrame:
        self.series_calls += 1
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-01-31")],
                "value": [1.0],
                "source": ["fred"],
                "series_id": [series_id],
            }
        )


class _StaticFetcher:
    def __init__(self, data: pd.DataFrame) -> None:
        self.data = data

    def fetch_series(self, *_args, **_kwargs) -> pd.DataFrame:
        return self.data.copy()


def _boj_config(expected_units: str = "100 Million Yen") -> dict:
    return {
        "source": "fred",
        "source_id": "JPNASSETS",
        "country": "JP",
        "frequency": "monthly",
        "type": "stock",
        "unit": "hundred_millions_jpy",
        "source_contract": {
            "title": "Bank of Japan: Total Assets for Japan",
            "units": expected_units,
            "frequency": "Monthly, End of Period",
        },
    }


def _boj_metadata() -> dict:
    return {
        "title": "Bank of Japan: Total Assets for Japan",
        "units": "100 Million Yen",
        "frequency": "Monthly, End of Period",
    }


class TestConfiguredSourceIdentity:
    def test_boj_contract_and_conversion_match_published_units(self):
        series = get_all_series()
        boj = series["boj_total_assets"]

        assert boj["unit"] == "hundred_millions_jpy"
        assert boj["source_contract"] == _boj_config()["source_contract"]
        assert "boe_total_assets" not in series

        global_assets = get_index_config("global_cb_assets")
        boj_component = next(
            component
            for component in global_assets["components"]
            if component["series"] == "boj_total_assets"
        )
        assert boj_component["weight"] == pytest.approx(0.67)

    def test_slow_context_series_are_not_predictive_inputs(self):
        series = get_all_series()
        assert "wb_credit_gdp_us" in series
        assert "wb_credit_gdp_cn" in series

        glci = get_index_config("global_liquidity_credit_index")
        liquidity = {
            component["series"]
            for component in glci["pillars"]["liquidity"]["components"]
        }
        credit = {
            component["series"]
            for component in glci["pillars"]["credit"]["components"]
        }

        assert "boe_total_assets" not in liquidity
        assert not {"wb_credit_gdp_us", "wb_credit_gdp_cn"} & credit
        for series_id in (
            "bis_credit_us",
            "bis_credit_eu",
            "bis_credit_cn",
            "bis_credit_jp",
        ):
            assert series[series_id]["availability_lag_days"] == 90


class TestFredSourceContracts:
    def test_matching_contract_is_checked_once_and_data_is_returned(self, monkeypatch):
        monkeypatch.setattr(
            "src.etl.fetcher.get_series_config",
            lambda _series_id: _boj_config(),
        )
        client = _FakeFredClient(_boj_metadata())
        fetcher = DataFetcher(fred_api_key="offline-test-key")
        fetcher._clients["fred"] = client

        first = fetcher.fetch_series("boj_total_assets")
        second = fetcher.fetch_series("boj_total_assets")

        assert not first.empty
        assert not second.empty
        assert client.info_calls == 1
        assert client.series_calls == 2

    def test_metadata_mismatch_fails_before_observations_are_used(self, monkeypatch):
        monkeypatch.setattr(
            "src.etl.fetcher.get_series_config",
            lambda _series_id: _boj_config(expected_units="Millions of Yen"),
        )
        client = _FakeFredClient(_boj_metadata())
        fetcher = DataFetcher(fred_api_key="offline-test-key")
        fetcher._clients["fred"] = client

        with pytest.raises(SourceContractError, match="units: expected"):
            fetcher.fetch_series("boj_total_assets")

        assert client.info_calls == 1
        assert client.series_calls == 0


class TestPeriodAndAvailabilityDates:
    def test_bis_quarter_is_dated_at_period_end(self):
        client = BISClient()

        assert client._parse_period("2024-Q1") == pd.Timestamp("2024-03-31")
        assert client._parse_period("2024-Q4") == pd.Timestamp("2024-12-31")

    def test_world_bank_year_is_dated_at_period_end(self):
        parsed = WorldBankClient()._parse_response(
            [
                {"page": 1},
                [
                    {
                        "date": "2023",
                        "value": 123.4,
                        "countryiso3code": "USA",
                    }
                ],
            ]
        )

        assert parsed.loc[0, "date"] == pd.Timestamp("2023-12-31")

    def test_quarterly_value_enters_only_after_lag_and_completed_week(self):
        raw = pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-03-31")],
                "value": [100.0],
            }
        )
        builder = FeatureMatrixBuilder()

        before = builder._regularize_series(
            raw,
            "quarterly",
            "W",
            availability_lag_days=90,
            as_of_date="2024-07-04",
        )
        after = builder._regularize_series(
            raw,
            "quarterly",
            "W",
            availability_lag_days=90,
            as_of_date="2024-07-06",
        )

        assert before.empty
        assert after.to_dict("records") == [
            {"date": pd.Timestamp("2024-07-05"), "value": 100.0}
        ]

    def test_monthly_first_day_label_cannot_enter_before_period_end(self):
        raw = pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-06-01")],
                "value": [100.0],
            }
        )
        builder = FeatureMatrixBuilder()

        before = builder._regularize_series(
            raw,
            "monthly",
            "W",
            as_of_date="2024-06-28",
        )
        after = builder._regularize_series(
            raw,
            "monthly",
            "W",
            as_of_date="2024-07-06",
        )

        assert before.empty
        assert after.to_dict("records") == [
            {"date": pd.Timestamp("2024-07-05"), "value": 100.0}
        ]

    def test_friday_runtime_does_not_publish_an_incomplete_friday_label(self):
        raw = pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-07-04")],
                "value": [100.0],
            }
        )
        builder = FeatureMatrixBuilder()

        friday_run = builder._regularize_series(
            raw,
            "daily",
            "W",
            as_of_date="2024-07-05",
        )
        saturday_run = builder._regularize_series(
            raw,
            "daily",
            "W",
            as_of_date="2024-07-06",
        )

        assert friday_run.empty
        assert saturday_run.to_dict("records") == [
            {"date": pd.Timestamp("2024-07-05"), "value": 100.0}
        ]

    def test_feature_metadata_keeps_raw_observation_date(self, monkeypatch):
        raw = pd.DataFrame(
            {
                "date": pd.date_range("2020-03-31", periods=16, freq="QE"),
                "value": range(100, 116),
            }
        )
        monkeypatch.setattr(
            "src.indicators.factors.get_index_config",
            lambda _index_id: {
                "pillars": {
                    "credit": {
                        "components": [
                            {
                                "series": "lagged_credit",
                                "transform": "level",
                            }
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(
            "src.indicators.factors.get_series_config",
            lambda _series_id: {
                "unit": "local_currency",
                "frequency": "quarterly",
                "availability_lag_days": 90,
            },
        )

        _matrix, metadata = FeatureMatrixBuilder(
            fetcher=_StaticFetcher(raw)
        ).build_feature_matrix(
            "test_index",
            end_date="2024-04-12",
            target_freq="W",
        )

        assert metadata[0].last_updated == "2023-12-31"
        assert metadata[0].availability_lag_days == 90
