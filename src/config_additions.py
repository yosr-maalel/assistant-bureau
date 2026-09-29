# ---------------------------------------------------------------------------
# MCP / Google Workspace (Gmail + Calendar) — à coller à la fin de config.py
# N'écrase aucun réglage existant (LLM, STT, TTS restent inchangés).
# ---------------------------------------------------------------------------
import os

GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH", "credentials/google_credentials.json"
)
GOOGLE_TOKEN_PATH = os.getenv(
    "GOOGLE_TOKEN_PATH", "credentials/google_token.json"
)
GOOGLE_CALENDAR_TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Africa/Tunis")
