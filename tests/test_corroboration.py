from app.corroboration import probe_sources, search_source
from app.tools import describe_imagery_tool, search_intel_reports_tool


def test_unconfigured_sources_return_empty_results():
    result = search_source("intel_reports", "harbor")
    assert result["status"] in {"ok", "unconfigured"}
    assert isinstance(result["results"], list)
    assert result["query"] == "harbor"
    osint = search_source("osint", "harbor")
    assert osint["status"] in {"ok", "unconfigured"}
    assert isinstance(osint["results"], list)


def test_probe_lists_each_source():
    names = {item["source"] for item in probe_sources("entity")}
    assert names == {"intel_reports", "ownership", "osint"}
    by_name = {item["source"]: item for item in probe_sources("entity")}
    assert by_name["intel_reports"]["status"] in {"ok", "unconfigured"}
    assert isinstance(by_name["intel_reports"]["results"], list)
    assert by_name["osint"]["status"] in {"ok", "unconfigured"}
    assert isinstance(by_name["osint"]["results"], list)
    assert by_name["ownership"]["status"] in {"ok", "unconfigured"}


def test_intel_tool_reports_search_status():
    result = search_intel_reports_tool("convoy near the port")
    assert result["status"] in {"ok", "unconfigured"}
    assert isinstance(result["results"], list)


def test_vlm_tool_is_unconfigured_without_a_model(monkeypatch):
    monkeypatch.setenv("CHARIOT_VLM_MODEL_ID", "")
    from app.config import get_settings

    get_settings.cache_clear()
    result = describe_imagery_tool("00000000-0000-0000-0000-000000000000")
    assert result["status"] == "unconfigured"
    assert result["results"] == []
    get_settings.cache_clear()
