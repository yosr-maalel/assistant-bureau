"""
google_auth.py — Authentification OAuth2 pour Gmail et Google Calendar.

Setup (une seule fois) :
1. https://console.cloud.google.com/ -> créer/choisir un projet
2. Activer "Gmail API" et "Google Calendar API"
3. "APIs & Services" -> "OAuth consent screen" -> type External, s'ajouter
   comme test user
4. "APIs & Services" -> "Credentials" -> "Create Credentials"
   -> OAuth client ID -> type "Desktop app"
5. Télécharger le JSON -> src/credentials/google_credentials.json

Au premier lancement, un navigateur s'ouvre pour autoriser l'accès ; le
token est ensuite mis en cache dans google_token.json (pas de nouvelle
connexion à chaque démarrage, sauf révocation/expiration).
"""
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Droits minimaux nécessaires : envoyer des emails + gérer le calendrier
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


def get_google_credentials(credentials_path: str, token_path: str) -> Credentials:
    """Retourne des credentials Google valides, en rafraîchissant ou en
    relançant le flux OAuth2 si nécessaire."""
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Fichier d'identifiants Google introuvable : {credentials_path}. "
                    "Voir INTEGRATION_GUIDE.md section 2."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds
