"""Chariot SDK gateway. Tests use a fake with the same method names."""

import json
import tempfile
from pathlib import Path

from app.config import Settings
from app.normalize import (
    inference_store_rows,
    model_id_from_watchbox,
    triage_event_row,
    watchbox_detection_row,
)
from app.timeutil import parse_time


class ChariotGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connected = False

    def connect(self) -> None:
        if self._connected:
            return
        from chariot.client import connect

        connect(credentials=self.settings.chariot_credentials_file)
        self._connected = True

    def detect(self, model_id: str, image_bytes: bytes, suffix: str = ".bin") -> dict:
        self.connect()
        from chariot.models.model import get_model_by_id

        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(image_bytes)
            handle.flush()
            model = get_model_by_id(model_id)
            result = model.infer("detect", sample=handle.name, return_inference_id=True)
        return _plain(result)

    def list_watchpoint_detections(
        self,
        watchpoint_id: str,
        time_start: str | None,
        time_end: str | None,
    ) -> list[dict]:
        self.connect()
        from chariot.watchbox import get_watchbox_detections

        rows = get_watchbox_detections(
            watchbox_id=watchpoint_id,
            time_of_emission_start=parse_time(time_start),
            time_of_emission_end=parse_time(time_end),
            limit=200,
        )
        return [watchbox_detection_row(row) for row in rows or []]

    def list_triage_events(
        self,
        project_id: str,
        watchpoint_id: str,
        time_start: str | None,
        time_end: str | None,
    ) -> list[dict]:
        self.connect()
        from chariot.watchbox.triage_event import get_triage_events

        rows = get_triage_events(
            project_id,
            watchbox_id=watchpoint_id,
            date_captured_start=parse_time(time_start),
            date_captured_end=parse_time(time_end),
            include_details=True,
            limit=200,
        )
        return [triage_event_row(row, watchpoint_id) for row in rows or []]

    def watchbox_model_id(self, watchpoint_id: str) -> str | None:
        self.connect()
        from chariot.watchbox import get_watchbox

        return model_id_from_watchbox(get_watchbox(watchpoint_id))

    def filter_inferences(self, model_id: str, request: dict) -> list[dict]:
        self.connect()
        from chariot.inference_store import models as store_models
        from chariot.inference_store.inference import filter_inferences

        body = store_models.NewGetInferencesRequest.model_validate(request)
        inferences = filter_inferences(model_id, body)
        rows: list[dict] = []
        for inference in inferences:
            rows.extend(inference_store_rows(inference))
        return rows

    def describe_image(self, model_id: str, image_bytes: bytes, prompt: str, suffix: str = ".bin") -> str:
        self.connect()
        from chariot.models.model import get_model_by_id

        model = get_model_by_id(model_id)
        action = _description_action(getattr(model, "actions", None))
        if action is None:
            actions = list(getattr(model, "actions", None) or [])
            raise DescriptionUnsupported(
                f"Model {model_id} does not support a description action; actions={actions}"
            )
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(image_bytes)
            handle.flush()
            sample = _description_sample(model, handle.name, prompt)
            result = model.infer(action, sample=sample, custom_metadata={"prompt": prompt})
        return _description_text(result)

    def run_workflow(self, workflow_id: str, agent_name: str, message: str, timeout_seconds: int) -> dict:
        import time

        self.connect()
        from chariot.awm.activity import get_activities, send_message

        activity = send_message(workflow_id, agent_name, {"message": message})
        session_id = activity.session_id
        after_sequence = activity.sequence
        deadline = time.monotonic() + timeout_seconds
        seen: set[str] = {activity.id}
        while time.monotonic() < deadline:
            activities = list(
                get_activities(
                    workflow_id,
                    session_id=session_id,
                    types=["agent_to_user_message", "error"],
                    sort_by="sequence",
                    after_sequence=after_sequence,
                    sort_order="asc",
                )
            )
            for item in activities:
                if item.id in seen:
                    continue
                seen.add(item.id)
                if item.type in {"agent_to_user_message", "error"} and item.final:
                    if item.type == "error":
                        raise RuntimeError(str(item.body))
                    return {"session_id": session_id, "body": item.body}
            time.sleep(2)
        raise TimeoutError(f"Fusion workflow {workflow_id} did not finish within {timeout_seconds}s")


class DescriptionUnsupported(RuntimeError):
    """The configured vision model can run detection but not a text description."""


def _description_sample(model, image_path: str, prompt: str):
    task = getattr(model, "task", None)
    task_name = getattr(task, "value", None) or str(task or "")
    if task_name in {"Image Text to Text", "image-text-to-text"}:
        return {"image": image_path, "prompts": [prompt]}
    return image_path


def _description_text(value) -> str:
    plain = _plain(value)
    text = _first_text(plain)
    if text:
        return text
    return _stringify(plain)


def _first_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_first_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("text", "generated_text", "content", "answer", "output", "response", "inference"):
            if value.get(key) not in (None, "", [], {}):
                found = _first_text(value[key])
                if found:
                    return found
    return ""


def _description_action(actions) -> str | None:
    available = set(actions or [])
    for name in ("query", "caption", "describe", "answer"):
        if name in available:
            return name
    return None


def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return json.loads(json.dumps(value, default=str))


def _stringify(value) -> str:
    plain = _plain(value)
    if isinstance(plain, str):
        return plain
    return json.dumps(plain, default=str)


def suffix_for(content_type: str | None, filename: str | None) -> str:
    if filename and Path(filename).suffix:
        return Path(filename).suffix
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/tiff": ".tif",
        "image/webp": ".webp",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/flac": ".flac",
    }
    return mapping.get(content_type or "", ".bin")
