"""Streamable HTTP MCP server mounted on the API process."""

from mcp.server.fastmcp import FastMCP

from app import tools

TOOL_NAMES = [
    ("search_assets", tools.search_assets_tool),
    ("search_detections", tools.search_detections_tool),
    ("search_triage_events", tools.search_triage_events_tool),
    ("query_timeseries", tools.query_timeseries_tool),
    ("search_ais", tools.search_ais_tool),
    ("measure_distance", tools.measure_distance_tool),
    ("associate_tracks", tools.associate_tracks_tool),
    ("pattern_of_life", tools.pattern_of_life_tool),
    ("search_insights", tools.search_insights_tool),
    ("upsert_insight", tools.upsert_insight_tool),
    ("correct_insight", tools.correct_insight_tool),
    ("describe_imagery", tools.describe_imagery_tool),
    ("search_intel_reports", tools.search_intel_reports_tool),
    ("search_ownership", tools.search_ownership_tool),
    ("search_osint", tools.search_osint_tool),
]


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "data-fusion",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )
    for name, function in TOOL_NAMES:
        mcp.tool(name=name, description=function.__doc__)(function)
    return mcp
