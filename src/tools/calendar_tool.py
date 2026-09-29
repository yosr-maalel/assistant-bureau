"""
calendar_tool.py — crée et liste des événements Google Calendar.

Test manuel :
    cd src
    python tools/calendar_tool.py
"""
import sys
import os
import datetime
from googleapiclient.discovery import build

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integrations"))

import config  # noqa: E402
from google_auth import get_google_credentials  # noqa: E402


def _get_calendar_service():
    creds = get_google_credentials(config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH)
    return build("calendar", "v3", credentials=creds)


def create_event(
    title: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    timezone: str | None = None,
) -> str:
    """Crée un événement. Les dates doivent être au format ISO 8601,
    ex: '2026-09-26T10:00:00'."""
    try:
        service = _get_calendar_service()
        tz = timezone or getattr(config, "GOOGLE_CALENDAR_TIMEZONE", "Africa/Tunis")
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": tz},
            "end": {"dateTime": end_iso, "timeZone": tz},
        }
        service.events().insert(calendarId="primary", body=event).execute()
        return f"Événement '{title}' créé dans le calendrier."
    except FileNotFoundError as e:
        return f"Configuration Google manquante : {e}"
    except Exception as e:
        return f"Je n'ai pas pu créer l'événement : {e}"


def list_upcoming_events(max_results: int = 5) -> str:
    """Liste les prochains événements à venir."""
    try:
        service = _get_calendar_service()
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        if not events:
            return "Aucun événement à venir."
        lines = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date"))
            lines.append(f"{e.get('summary', 'Sans titre')} le {start}")
        return "Voici vos prochains événements : " + "; ".join(lines)
    except FileNotFoundError as e:
        return f"Configuration Google manquante : {e}"
    except Exception as e:
        return f"Je n'ai pas pu lire le calendrier : {e}"


if __name__ == "__main__":
    print(list_upcoming_events())
    print(
        create_event(
            "Test assistant",
            "2026-09-26T10:00:00",
            "2026-09-26T10:30:00",
            "Créé automatiquement pour test",
        )
    )
