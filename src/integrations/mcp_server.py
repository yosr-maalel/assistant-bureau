"""
mcp_server.py — expose email_tool et calendar_tool comme serveur MCP (stdio).

Optionnel : ce serveur permet de connecter les MÊMES outils
(envoi d'email, gestion du calendrier) à n'importe quel client MCP
(Claude Desktop, etc.), indépendamment de la boucle vocale de l'assistant.
Il n'est PAS requis pour que l'assistant vocal fonctionne (voir
tool_orchestrator.py, qui appelle les outils directement).

Lancer :
    cd src
    python integrations/mcp_server.py

Puis déclarer ce serveur dans la config MCP de ton client
(ex. claude_desktop_config.json) avec la commande :
    python /chemin/vers/src/integrations/mcp_server.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from tools import email_tool, calendar_tool  # noqa: E402

mcp = FastMCP("ai-assistant-tools")


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email via Gmail."""
    return email_tool.send_email(to, subject, body)


@mcp.tool()
def create_calendar_event(
    title: str, start_iso: str, end_iso: str, description: str = ""
) -> str:
    """Crée un événement Google Calendar.
    Dates au format ISO 8601, ex: 2026-09-26T10:00:00."""
    return calendar_tool.create_event(title, start_iso, end_iso, description)


@mcp.tool()
def list_upcoming_events(max_results: int = 5) -> str:
    """Liste les prochains événements du calendrier."""
    return calendar_tool.list_upcoming_events(max_results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
