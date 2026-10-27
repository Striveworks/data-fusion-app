"""Import the Forge bundle into a Chariot project. Does not run unless invoked."""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "forge" / "data_fusion_config.yaml"


def load_config() -> dict:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    endpoint = os.environ.get("MCP_PUBLIC_URL")
    if endpoint:
        config.setdefault("parameters", {})["mcp_endpoint"] = endpoint
    return config


def _treat_missing_reference_as_not_found() -> None:
    # chariot 0.27.3 raises RuntimeError for missing components, but the importer only
    # catches NotFoundException, so a first import into an empty project would abort.
    from chariot import awm
    from chariot_api._openapi.awm.exceptions import NotFoundException

    lookup = awm.get_configuration_by_reference

    def wrapped(*args, **kwargs):
        try:
            return lookup(*args, **kwargs)
        except RuntimeError as exc:
            if "does not exist" in str(exc):
                raise NotFoundException(status=404, reason=str(exc)) from exc
            raise

    awm.get_configuration_by_reference = wrapped


def main() -> None:
    from chariot.awm.config_import import import_v2_configurations, print_import_result
    from chariot.client import connect

    _treat_missing_reference_as_not_found()

    credentials = os.environ.get("CHARIOT_CREDENTIALS_FILE", str(ROOT / "data-fusion-app.json"))
    project_id = os.environ.get("CHARIOT_PROJECT_ID", "")
    if not project_id:
        raise SystemExit("CHARIOT_PROJECT_ID is required")
    connect(credentials=credentials)
    result = import_v2_configurations(project_id, load_config(), version_changelog="data fusion import")
    print_import_result(result)
    if result.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
