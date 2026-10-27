"""Build compact, entity-linked context from the application's data holdings."""

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.knowledge import search_insights, statement_dict
from app.queries import search_ais, search_intel_reports, search_osint, search_vessel_ownership

_IMO = re.compile(r"(?<![A-Z0-9])IMO[\s_-]*[:#]?[\s_-]*(\d{7})(?!\d)", re.IGNORECASE)
_MMSI = re.compile(r"(?<![A-Z0-9])MMSI[\s_-]*[:#]?[\s_-]*(\d{9})(?!\d)", re.IGNORECASE)
_NAMED = re.compile(
    r"\b(?:named|name(?:d)?\s+is)\s+[\"']?([A-Z][A-Z0-9][A-Z0-9 .'-]{1,50})",
    re.IGNORECASE,
)


def evidence_identifiers(evidence: dict) -> dict[str, list[str]]:
    """Extract vessel identifiers suitable for exact or narrow database searches."""
    strings = [
        str(value)
        for value in (
            evidence.get("filename"),
            evidence.get("visual_description"),
            evidence.get("external_id"),
        )
        if value
    ]
    text = "\n".join(strings)
    imos = _unique(match.group(1) for match in _IMO.finditer(text))
    mmsis = _unique(
        [
            *(match.group(1) for match in _MMSI.finditer(text)),
            *(evidence.get("sample_mmsis") or []),
        ]
    )
    imos = _unique([*imos, *(evidence.get("sample_imos") or [])])
    names = _unique(
        [
            *(match.group(1).strip(" .'\"") for match in _NAMED.finditer(text)),
            *(evidence.get("sample_vessel_names") or []),
        ]
    )

    for observation in [*(evidence.get("observations") or []), *(evidence.get("intercepts") or [])]:
        if not isinstance(observation, dict):
            continue
        if observation.get("imo"):
            imos = _unique([*imos, observation["imo"]])
        if observation.get("mmsi"):
            mmsis = _unique([*mmsis, observation["mmsi"]])
        if observation.get("vessel_name"):
            names = _unique([*names, observation["vessel_name"]])

    filename = evidence.get("filename")
    generic_names = {"image", "imagery", "scene", "photo", "ais", "upload", "data", "file"}
    if filename:
        stem = Path(str(filename)).stem
        before_identifier = re.split(r"[_ -](?:IMO|MMSI)[_ -]", stem, maxsplit=1, flags=re.IGNORECASE)[0]
        candidate = re.sub(r"[_-]+", " ", before_identifier).strip()
        if len(candidate) >= 4 and candidate.lower() not in generic_names:
            names = _unique([candidate, *names])

    return {"imo": imos, "mmsi": mmsis, "vessel_name": names}


def aggregate_context(session: Session, evidence: dict) -> dict:
    """Search relevant holdings and return a bounded context for the fusion agent."""
    identifiers = evidence_identifiers(evidence)
    queries = _unique(
        [*identifiers["imo"], *identifiers["mmsi"], *identifiers["vessel_name"]]
    )
    context = {
        "identifiers": identifiers,
        "holdings_checked": [
            "active_insights",
            "vessel_ownership",
            "ais_reports",
            "osint_reports",
            "intel_reports",
        ],
        "ownership": {"status": "searched", "matches": []},
        "ais": {"status": "searched", "matches": []},
        "osint": {"status": "searched", "matches": []},
        "intel_reports": {"status": "searched", "matches": []},
        "prior_insights": [],
    }
    if not queries:
        context["ownership"]["status"] = "not_applicable_no_entity_identifier"
        context["ais"]["status"] = "not_applicable_no_entity_identifier"
        context["osint"]["status"] = "not_applicable_no_entity_identifier"
        context["intel_reports"]["status"] = "not_applicable_no_entity_identifier"
        return context

    ownership: dict[str, dict] = {}
    for query in queries:
        result = search_vessel_ownership(session, query, limit=10)
        for row in result["results"]:
            ownership[row["id"]] = row
    context["ownership"]["matches"] = list(ownership.values())[:10]

    ais: dict[str, dict] = {}
    for imo in identifiers["imo"]:
        for row in search_ais(session, imo=imo, limit=10):
            ais[row["id"]] = row
    for mmsi in identifiers["mmsi"]:
        for row in search_ais(session, mmsi=mmsi, limit=10):
            ais[row["id"]] = row
    for name in identifiers["vessel_name"]:
        for row in search_ais(session, vessel_name=name, limit=10):
            ais[row["id"]] = row
    context["ais"]["matches"] = list(ais.values())[:10]

    osint: dict[str, dict] = {}
    for query in queries:
        result = search_osint(session, query, limit=5)
        for row in result["results"]:
            osint[row["id"]] = row
    context["osint"]["matches"] = list(osint.values())[:5]

    intel: dict[str, dict] = {}
    for query in queries:
        result = search_intel_reports(session, query, limit=5)
        for row in result["results"]:
            intel[row["id"]] = row
    context["intel_reports"]["matches"] = list(intel.values())[:5]

    insights: dict[str, dict] = {}
    for query in queries:
        for row in search_insights(session, entity=query, limit=10):
            payload = statement_dict(row)
            insights[payload["id"]] = payload
    context["prior_insights"] = list(insights.values())[:10]
    return context


def _unique(values) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
