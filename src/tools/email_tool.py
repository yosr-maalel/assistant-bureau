"""
email_tool.py — envoie des emails via l'API Gmail.

Test manuel :
    cd src
    python tools/email_tool.py
"""
import base64
import sys
import os
from email.mime.text import MIMEText
from googleapiclient.discovery import build

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integrations"))

import config  # noqa: E402
from google_auth import get_google_credentials  # noqa: E402


def _get_gmail_service():
    creds = get_google_credentials(config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH)
    return build("gmail", "v1", credentials=creds)


def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email. Retourne un message court destiné à être lu par le TTS."""
    try:
        service = _get_gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email envoyé à {to}."
    except FileNotFoundError as e:
        return f"Configuration Google manquante : {e}"
    except Exception as e:
        return f"Je n'ai pas pu envoyer l'email : {e}"


if __name__ == "__main__":
    dest = input("Destinataire : ").strip()
    subj = input("Sujet : ").strip()
    body = input("Message : ").strip()
    print(send_email(dest, subj, body))
