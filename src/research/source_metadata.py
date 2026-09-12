"""Admit source metadata only when it matches the declared series contract."""

FRED_UNITS = {
    "percent_qoq_saar": "Percent Change from Preceding Period",
    "millions USD": "Millions of U.S. Dollars",
    "billions USD": "Billions of US Dollars",
    "percent": "Percent",
}
FREQUENCY = {
    "daily": "D",
    "weekly": "W",
    "monthly": "M",
    "quarterly": "Q",
    "annual": "A",
}


def verify_fred(series, scope, transport):
    import os

    data, cap = transport.get(
        "https://api.stlouisfed.org/fred/series",
        {
            "series_id": series.source_id,
            "api_key": os.environ.get("FRED_API_KEY", ""),
            "file_type": "json",
            "realtime_start": str(scope.information_date),
            "realtime_end": str(scope.information_date),
        },
    )
    records = data["seriess"]
    if len(records) != 1 or records[0]["id"] != series.source_id:
        raise ValueError("FRED metadata returned an unexpected series")
    meta = records[0]
    expected = FRED_UNITS.get(series.unit, series.unit)
    if (
        meta["units"].replace(".", "").casefold()
        != expected.replace(".", "").casefold()
        or meta["frequency_short"] != FREQUENCY[series.frequency]
    ):
        raise ValueError(
            "FRED unit or frequency disagrees with the registered contract"
        )
    return cap


def verify_bis(series, structure, series_key):
    dimensions = structure["dimensions"]["series"]
    indexes = series_key.split(":")
    if len(dimensions) != len(indexes):
        raise ValueError("BIS dimension count changed")
    resolved = {d["id"]: d["values"][int(i)]["id"] for d, i in zip(dimensions, indexes)}
    if ".".join(resolved.values()) != series.source_id:
        raise ValueError("BIS full dimension key differs from request")
    expected = {k: v for k, v in series.dimensions.items() if k != "dataflow"}
    if not expected or any(resolved.get(k) != v for k, v in expected.items()):
        raise ValueError("BIS dimensions differ from registered contract")
    return resolved
