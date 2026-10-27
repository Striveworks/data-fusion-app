import json

from app.aggregate import aggregate_context
from app.processors.imagery import JobContext


def fusion_message(evidence: dict) -> str:
    inspection = ""
    if evidence.get("storage") == "metadata.ais_reports" and evidence.get("observations"):
        inspection = (
            "The AIS observations are included in this evidence. Write the insight from those "
            "rows together with any ownership, prior-insight, AIS, OSINT, and intel-report matches in aggregate_context. "
            "Call search_ais only when you need history beyond the included rows.\n\n"
        )
    elif evidence.get("storage") == "signal_samples" and evidence.get("intercepts"):
        inspection = (
            "The ELINT intercepts are included in this evidence. Each row is a stored signal "
            "sample correlated to a vessel. Compare the emitter, position, and time with "
            "ownership, prior insights, AIS, OSINT, and intel-report matches in aggregate_context. Use "
            "query_timeseries with the MMSI, IMO, or vessel name only when you need rows "
            "beyond this message.\n\n"
        )
    elif evidence.get("storage") == "metadata.ais_reports":
        inspection = (
            "This is an AIS database locator summary, not the observations themselves. "
            "Inspect the stored reports with pattern_of_life and narrow search_ais calls. "
            "Do not infer vessel behavior from counts or samples in this message alone, "
            "and do not retrieve the entire AIS dataset into context.\n\n"
        )
    if evidence.get("detections") or evidence.get("visual_description"):
        inspection += (
            "This imagery evidence already contains the detection-model outputs"
            + (
                " and the vision-model description."
                if evidence.get("visual_description")
                else "."
            )
            + " Write an insight that names the detected objects, their counts, and the "
            "image place or time when those fields are present. Use these outputs directly "
            "and attach the asset_ids and detection_ids. Do not discard the image because "
            "a later search returns no rows.\n\n"
        )
    if evidence.get("visual_description_status") == "detection_only":
        inspection += (
            "The configured vision model only supports detection, so there is no separate "
            "text description. Do not ask for another visual description.\n\n"
        )
    if evidence.get("aggregate_context"):
        inspection += (
            "Aggregate context contains deterministic searches across prior insights, vessel "
            "ownership, AIS holdings, stored OSINT reports, and intel reports using identifiers "
            "extracted from this evidence. Reason over every non-empty match. Include material "
            "ownership, vessel identity, sanctions, AIS facts, OSINT findings, and intel-report "
            "findings in the insight, clearly distinguishing stored registry, open-source, and "
            "intel reports from direct observations. "
            "If a prior active insight covers the same "
            "entity, call correct_insight to enrich it instead of creating a duplicate. "
            "An empty match list means that holding was searched and returned no match. "
            "When calling upsert_insight, pass subject as its own argument.\n\n"
        )
    return (
        "New evidence has been stored. Search existing insights for the same entities, "
        "places, and time ranges before you write. Correct an insight when the new evidence "
        "contradicts it. Do not invent corroboration when a tool reports status unconfigured.\n\n"
        f"{inspection}"
        f"Evidence:\n{json.dumps(evidence, default=str)}"
    )


def process_fusion(ctx: JobContext) -> dict:
    workflow_id = ctx.settings.chariot_workflow_id
    if not workflow_id:
        raise RuntimeError("CHARIOT_WORKFLOW_ID is unset")
    evidence = dict(ctx.payload.get("evidence") or {})
    evidence["aggregate_context"] = aggregate_context(ctx.session, evidence)
    message = fusion_message(evidence)
    result = ctx.chariot.run_workflow(
        workflow_id,
        ctx.settings.chariot_fusion_agent,
        message,
        ctx.settings.fusion_timeout_seconds,
    )
    return {"session_id": result.get("session_id"), "body": result.get("body")}
