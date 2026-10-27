"""Track association over stored detections."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geo import haversine_meters
from app.models import Detection
from app.timeutil import parse_time


def associate_tracks(
    session: Session,
    *,
    label: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    max_meters: float = 500.0,
    max_seconds: float = 300.0,
) -> dict:
    query = select(Detection).where(Detection.latitude.is_not(None), Detection.longitude.is_not(None))
    if label:
        query = query.where(Detection.label == label)
    start = parse_time(time_start)
    end = parse_time(time_end)
    if start is not None:
        query = query.where(Detection.observed_at >= start)
    if end is not None:
        query = query.where(Detection.observed_at <= end)
    query = query.order_by(Detection.observed_at.asc().nullslast(), Detection.created_at.asc())
    detections = list(session.scalars(query))

    tracks: list[dict] = []
    for detection in detections:
        observed = detection.observed_at or detection.created_at
        matched = None
        if detection.latitude is None or detection.longitude is None or observed is None:
            continue
        for track in tracks:
            if track["label"] != detection.label:
                continue
            distance = haversine_meters(
                track["latitude"], track["longitude"], detection.latitude, detection.longitude
            )
            elapsed = abs((observed - track["observed_at"]).total_seconds())
            if distance <= max_meters and elapsed <= max_seconds:
                matched = track
                break
        if matched is None:
            matched = {
                "track_id": str(uuid.uuid4()),
                "label": detection.label,
                "latitude": detection.latitude,
                "longitude": detection.longitude,
                "observed_at": observed,
                "detection_ids": [],
            }
            tracks.append(matched)
        detection.track_id = matched["track_id"]
        matched["latitude"] = detection.latitude
        matched["longitude"] = detection.longitude
        matched["observed_at"] = observed
        matched["detection_ids"].append(str(detection.id))

    session.flush()
    return {
        "tracks": [
            {
                "track_id": track["track_id"],
                "label": track["label"],
                "detection_ids": track["detection_ids"],
            }
            for track in tracks
        ]
    }
