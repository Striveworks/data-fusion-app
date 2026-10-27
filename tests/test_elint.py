import json

from app.aggregate import evidence_identifiers
from app.elint import parse_elint_document
from app.processors.fusion import fusion_message

INTERCEPT = {
    "intercept_id": "EL-1",
    "timestamp": "2024-11-19T20:37:14Z",
    "emitter_status": "ACTIVE",
    "geolocation": {"latitude": 26.02, "longitude": 54.40},
    "signal_parametric_data": {"frequency_mhz": 9382.59},
    "emitter_identification": {
        "matched_elnot": "R-NAV-X01",
        "functional_class": "MARINE_NAVIGATION_RADAR",
        "frequency_band": "X_BAND",
        "confidence_score": 0.92,
    },
    "correlated_platform": {
        "platform_type": "VESSEL",
        "automatic_identification_system": {
            "mmsi": "431938000",
            "name": "HAKUSAN",
            "imo": "9535058",
            "heading_deg": 91,
        },
    },
}


def test_elint_collection_becomes_vessel_linked_samples():
    samples = parse_elint_document(json.dumps({"elint_intercept_collection": [INTERCEPT]}))
    assert len(samples) == 1
    sample = samples[0]
    assert sample["source_id"] == "431938000"
    assert sample["channel"] == "R-NAV-X01"
    assert sample["value"] == 9382.59
    assert sample["latitude"] == 26.02
    assert sample["details"]["vessel_name"] == "HAKUSAN"
    assert sample["details"]["imo"] == "9535058"
    assert sample["details"]["frequency_band"] == "X_BAND"


def test_flat_elint_feed_maps_platform_and_gmt_time():
    samples = parse_elint_document(
        json.dumps(
            [
                {
                    "INTERCEPT_ID": "EL-20261015-001",
                    "TSTAMP": "2026-10-15 00:05:12 GMT",
                    "ELINT_NOTATION": "ELNOT R1234",
                    "FREQUENCY_MHZ": "9410.0",
                    "PRI_MICROS": "1.000",
                    "PULSE_WIDTH_MICROS": "0.08",
                    "SCAN_TYPE": "CIRCULAR",
                    "SCAN_RATE_RPM": "24.0",
                    "SIGNAL_STRENGTH_DBM": "-68.5",
                    "LATITUDE": "54.81450",
                    "LONGITUDE": "13.22100",
                    "LOB_DEG": "172.4",
                    "EMITTER_CLASS": "SURFACE_SEARCH_RADAR",
                    "PLATFORM_CONFIDENCE": "PROBABLE_POLA_FEODOSIA",
                }
            ]
        )
    )
    sample = samples[0]
    assert sample["time"] == "2026-10-15 00:05:12"
    assert sample["source_id"] == "R1234"
    assert sample["channel"] == "R1234"
    assert sample["value"] == 9410.0
    assert sample["latitude"] == 54.8145
    assert sample["longitude"] == 13.221
    assert sample["details"]["vessel_name"] == "POLA FEODOSIA"
    assert sample["details"]["functional_class"] == "SURFACE_SEARCH_RADAR"
    assert sample["details"]["lob_deg"] == 172.4
    assert sample["details"]["signal_strength_dbm"] == -68.5
    assert sample["details"]["pulse_width_us"] == 0.08


def test_elint_evidence_identifiers_include_the_correlated_vessel():
    identifiers = evidence_identifiers(
        {
            "sample_mmsis": ["431938000"],
            "sample_imos": ["9535058"],
            "sample_vessel_names": ["HAKUSAN"],
            "intercepts": [{"mmsi": "431938000", "imo": "9535058", "vessel_name": "HAKUSAN"}],
        }
    )
    assert identifiers == {
        "imo": ["9535058"],
        "mmsi": ["431938000"],
        "vessel_name": ["HAKUSAN"],
    }


def test_fusion_message_uses_included_elint_intercepts():
    message = fusion_message(
        {
            "storage": "signal_samples",
            "intercepts": [{"vessel_name": "HAKUSAN", "elnot": "R-NAV-X01"}],
        }
    )
    assert "ELINT intercepts are included" in message
    assert "HAKUSAN" in message
