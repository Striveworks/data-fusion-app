from app.intel import parse_intel_document

REPORT = """INTELLIGENCE ASSESSMENT
Source: Maritime Human Intelligence (HUMINT) & Cyber Signal Intercepts
Classification: Fictitious / Simulation
Subject: Captain Nikolai G. BORZOV – Master of MV POLA FEODOSIA (IMO: 9849461)
Status: PERSON OF INTEREST (POI) – Priority Tier 2 (Counter-Smuggling / Sanctions Evasion)

1. Target Profiling & Background

• Full Name: Nikolai Gennadyevich BORZOV
• Date of Birth: March 14, 1974 (Age 52)
• Nationality: Russian Federation (Passport Holder: 45-XX-XXXXXX)
• Credentials: Master Mariner Unlimited (RF Maritime Registry), issued by the Port of St. Petersburg.
• Association: Employee of OOO "Pola Raise" (Vessel Operator) since 2021.

2. Basis for Investigation (Nexus to Illicit Networks)

Captain Borzov has been designated a Person of Interest following a pattern of anomalous ship handling, cellular geolocations, and financial anomalies linked to entities under international sanctions.

A. Black Sea "Dark" Port Anomalies (2024–2025)

Prior to taking command of the Baltic route on the Pola Feodosia, Borzov was the Master of the sister ship Pola Anatolia.

B. Digital Footprint & Communications Intercepts

On October 12, 2026, while the Pola Feodosia was docked in Wismar, Germany, encrypted cellular communications from Borzov's personal device were localized.

4. Tactical Implications for the Current Transit

While the primary manifest lists 1,800 MT of industrial ammonium nitrate, Borzov’s recent communications raise the probability of secondary unmanifested freight.
"""


def test_intel_assessment_extracts_person_and_vessel():
    report = parse_intel_document(REPORT)[0]
    assert report["title"] == "INTELLIGENCE ASSESSMENT"
    assert report["classification"] == "Fictitious / Simulation"
    assert report["person_name"] == "Nikolai Gennadyevich BORZOV"
    assert report["vessel_name"] == "POLA FEODOSIA"
    assert report["imo"] == "9849461"
    assert report["status"].startswith("PERSON OF INTEREST")
    assert report["event_date"] == "2026-10-12"
    assert report["source"].startswith("Maritime Human Intelligence")
    assert "Person of Interest" in report["summary"]
    assert report["details"]["date_of_birth"] == "1974-03-14"
    assert report["details"]["nationality"] == "Russian Federation"
    assert report["details"]["operator"] == "Pola Raise"
    assert report["details"]["role"] == "Master"
    assert report["details"]["sister_vessel"] == "Pola Anatolia"
    assert report["details"]["cargo"] == "1,800 MT of industrial ammonium nitrate"
    assert report["report_key"] == "9849461:nikolai-gennadyevich-borzov:intelligence-assessment"
