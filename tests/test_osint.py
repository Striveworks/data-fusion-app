from app.osint import parse_osint_document

REPORT = """OSINT MARITIME MONITORING REPORT
Vessel Identified: MV POLA FEODOSIA (IMO: 9849461)
Event: Unreported Port Departure and Contextual Baltic Transit
Date of Event: October 15, 2026
Report Date: October 20, 2026

1. Executive Summary

On October 15, 2026, the Russian-flagged general cargo vessel POLA FEODOSIA (IMO: 9849461) was observed departing the commercial port of Wismar, Germany, bound for Kaliningrad, Russia. Ground-level photographic verification and commercial satellite imaging confirm that the vessel was heavily laden upon its departure.

2. Vessel Profile

• Vessel Name: POLA FEODOSIA
• IMO / MMSI: 9849461 / 273422380
• Flag / Type: Russia / General Cargo Ship
• Dimensions: Length Overall (LOA) x Breadth: 141m × 16.9m
• Reported Draught: 4.5 meters (Indicates partially to heavily laden status for this vessel class)

3. Port Departure Imagery & Observation Analysis

Commercial Satellite Imagery (GEOINT Cross-Reference)

• Acquisition Time: October 15, 2026, 09:12 UTC
• Coordinates: 55°09'28.8"N, 15°23'04.2"E (Northeast of Bornholm)

4. Track and Sensor Corroboration

• AIS Telemetry: The vessel broadcasted a destination header of RU KGD (Kaliningrad) with an Estimated Time of Arrival (ETA) of October 16 at 06:00 UTC.
"""


def test_narrative_osint_report_extracts_vessel_and_track():
    report = parse_osint_document(REPORT)[0]
    assert report["title"] == "OSINT MARITIME MONITORING REPORT"
    assert report["vessel_name"] == "POLA FEODOSIA"
    assert report["imo"] == "9849461"
    assert report["mmsi"] == "273422380"
    assert report["flag"] == "Russia"
    assert report["vessel_type"] == "General Cargo Ship"
    assert report["event"] == "Unreported Port Departure and Contextual Baltic Transit"
    assert report["event_date"] == "2026-10-15"
    assert report["report_date"] == "2026-10-20"
    assert report["origin"] == "Wismar"
    assert report["destination"] == "Kaliningrad"
    assert report["latitude"] == 55.158
    assert report["longitude"] == 15.3845
    assert "heavily laden" in report["summary"]
    assert report["details"]["draught_m"] == 4.5
    assert report["details"]["length_m"] == 141
    assert report["details"]["breadth_m"] == 16.9
    assert report["details"]["destination_code"] == "RU KGD"
    assert report["report_key"] == "9849461:2026-10-15:osint-maritime-monitoring-report"
