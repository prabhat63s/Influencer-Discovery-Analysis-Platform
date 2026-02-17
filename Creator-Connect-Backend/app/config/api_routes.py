"""
Centralized Internal API Route Definitions.
Used to avoid hardcoding strings across the codebase and ensure consistency.
"""

# ==============================================================================
# ROUTE PREFIXES
# ==============================================================================
PREFIX_METRICS = "/api/metrics"
PREFIX_REPORTING = "/api"  # Root prefix usage in reports router
PREFIX_SEARCH = "/api"      # Root prefix usage in search router
PREFIX_AGENT = "/api/agent"       # Root prefix usage in agent router


# ==============================================================================
# ENDPOINT PATHS (Relative to Router Prefix)
# ==============================================================================

# Search
SEARCH_DYNAMIC_PROMPT = "/dynamic-search/prompt"
SEARCH_DEFAULTS = "/dynamic-search/defaults"
SEARCH_RESULTS_DYNAMIC = "/results/dynamic/prompt"
SEARCH_RESULTS_ALL = "/results/dynamic/prompt/all"
SEARCH_ANALYSIS = "/analysis/{conversation_id}"
SEARCH_PEERS_STATUS = "/results/profession-peers/status"
SEARCH_INDUSTRY_INSIGHTS = "/industry-comparison/insights"
SEARCH_AI_INSIGHT_TEST = "/ai-insight/test"
SEARCH_AI_INSIGHT = "/ai-insight"
SEARCH_INTERNAL_WEBHOOK = "/influencers/webhook" # Internal only

# Reports
REPORT_GENERATE_DYNAMIC = "/report/generate/dynamic"
REPORT_DOWNLOAD = "/report/download/{report_name}"

# Metrics
METRICS_SESSION = "/{conversation_id}"
METRICS_SESSION_ANALYSIS = "/{conversation_id}/analysis"
METRICS_ALL_SESSIONS = "/"
METRICS_EXPORT = "/{conversation_id}/export"
METRICS_COMPARE = "/compare/{conv_id_1}/{conv_id_2}"
METRICS_INTERNAL_INSIGHTS = "/internal-comparison/insights"
METRICS_SYSTEM = "/system/vitals"

# Agent
AGENT_CHAT = "/chat"
AGENT_HEALTH = "/health"

# System & Auth (Directly in main.py)
AUTH_LOGIN = "/api/auth/login"
SYSTEM_HEALTH = "/api/health"
