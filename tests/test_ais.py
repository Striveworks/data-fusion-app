import pytest

from app.ais import parse_ais, reports_from_body


def test_single_report_coerces_identifiers():
    reports = reports_from_body(
        {
            "mmsi": 211234560,
            "imo": 9432105,
            "timestamp": "2026-10-15T09:42:15Z",
            "heading_degrees": 266,
            "navigational_status_code": 0,
            "extra_source": "coast-station",
        }
    )
    assert reports[0]["mmsi"] == "211234560"
    assert reports[0]["imo"] == "9432105"
    assert reports[0]["navigational_status_code"] == 0
    assert reports[0]["heading_degrees"] == 266
    assert reports[0]["navigational_status"] == "Underway using engine"
    assert reports[0]["details"] == {"extra_source": "coast-station"}


def test_batch_wrapper_and_list():
    body = {"reports": [{"mmsi": "211234560", "timestamp": "2026-10-15T09:42:15Z"}]}
    assert len(reports_from_body(body)) == 1
    assert len(reports_from_body(body["reports"])) == 1


def test_missing_timestamp_is_rejected():
    with pytest.raises(ValueError, match="missing_timestamp"):
        reports_from_body({"mmsi": 211234560})


def test_standard_feed_row_allows_missing_fields():
    parsed = parse_ais(
        [
            {
                "MMSI": "257465900",
                "TSTAMP": "2024-11-19 20:28:06 GMT",
                "LATITUDE": "63.43565",
                "LONGITUDE": "10.39761",
                "COG": "137.6",
                "SOG": "0",
                "HEADING": "511",
                "NAVSTAT": "15",
                "IMO": "0",
                "NAME": "D/S HANSTEEN",
                "CALLSIGN": "LDQF",
                "TYPE": "60",
                "A": "20",
                "B": "10",
                "C": "3",
                "D": "2",
                "DRAUGHT": "0",
                "DEST": "",
                "ETA": "00-00 00:00",
            },
            {"NAME": "NO IDENTITY"},
            {"MMSI": "244850687", "SOG": "not-a-number"},
        ]
    )
    assert parsed.skipped == 2
    assert parsed.skip_reasons["missing_mmsi"] == 1
    assert parsed.skip_reasons["missing_timestamp"] == 1
    report = parsed.reports[0]
    assert report["mmsi"] == "257465900"
    assert report["vessel_name"] == "D/S HANSTEEN"
    assert report["call_sign"] == "LDQF"
    assert report["destination"] is None
    assert report["length"] == 30
    assert report["width"] == 5
    assert report["speed_over_ground_knots"] == 0
    assert report["navigational_status"] == "Not defined"
    assert report["observed_at"].startswith("2024-11-19T20:28:06")
