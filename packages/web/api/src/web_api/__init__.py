"""isitme Web API / BFF.

A thin local-first FastAPI service that fronts the Core Brain for the web app:
Google OAuth login + sessions, API-key management, an MCP-config generator, and
a read-only proxy over the brain for the dashboard visualizations.
"""

__version__ = "0.1.0"
