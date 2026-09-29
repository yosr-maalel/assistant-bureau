
"""
tool_orchestrator.py — détecte les intentions "envoyer un email" /
"créer un événement" / "lister mes événements" et mène une PETITE
conversation pour récupérer les informations manquantes avant d'appeler
l'outil (slot-filling).
 
Ne modifie PAS llm.py : ce module fait son PROPRE appel direct à Ollama
(en mode JSON, pas via l'API tool-calling) uniquement pour classifier
l'intention et extraire les champs déjà donnés par l'utilisateur.
 
Pourquoi pas l'API tool-calling seule ? Avec un petit modèle comme
qwen2.5:3b, si l'utilisateur dit juste "Est-ce que tu peux envoyer un
email ?" (sans destinataire/sujet/corps), le modèle refuse souvent
d'appeler l'outil car les paramètres obligatoires manquent — et rien ne se
passe. Ici, on classifie l'intention même partielle, puis on redemande
nous-mêmes les champs manquants, tour après tour.
 
Intégration dans assistant.py (3 lignes, section 5 du guide) :
 
    from tool_orchestrator import try_handle_tool_intent
 
    tool_reply = try_handle_tool_intent(user_text)
    if tool_reply is not None:
        reply_text = tool_reply
    else:
        reply_text = self.llm.generate_response(user_text)
 
Note : l'état "en attente" (_pending) est global au module, ce qui convient
à un assistant de bureau mono-utilisateur / une seule conversation à la
fois. Si tu ajoutes un jour plusieurs sessions en parallèle, il faudra
passer cet état par session (dict indexé par session_id) plutôt que par
variable de module.
"""
import datetime
import difflib
import json
import logging
import re
import sys
import os
import unicodedata
 
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "integrations"))
 
import ollama  # noqa: E402
import config  # noqa: E402
from tools import email_tool, calendar_tool, weather_tool  # noqa: E402
 
_log = logging.getLogger("robot_assistant.tool_orchestrator")
 
# ---------------------------------------------------------------------------
# Heure / date : réponse LOCALE instantanée, sans appeler Ollama.
# Le LLM n'a pas d'horloge et ne peut de toute façon jamais répondre juste ;
# autant court-circuiter l'appel réseau (qui coûte plusieurs secondes pour
# rien) et répondre directement avec l'horloge système.
# ---------------------------------------------------------------------------
 
_TIME_KEYWORDS = [
    "quelle heure", "quelle est l'heure", "l'heure qu'il est",
    "heure est-il", "heure est il", "heure il est",
]
_DATE_KEYWORDS = [
    "quelle date", "quel jour sommes", "on est quel jour",
    "date d'aujourd'hui", "quel jour on est", "quel jour est-on",
    "quel jour est on",
]
_JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
]
 
 
def _try_local_time_date(text_lower: str) -> str | None:
    if any(k in text_lower for k in _TIME_KEYWORDS):
        now = datetime.datetime.now()
        return f"Il est {now.hour} heures {now.minute:02d}."
    if any(k in text_lower for k in _DATE_KEYWORDS):
        now = datetime.datetime.now()
        return (
            f"Nous sommes le {_JOURS_FR[now.weekday()]} {now.day} "
            f"{_MOIS_FR[now.month - 1]} {now.year}."
        )
    return None
 
 
# ---------------------------------------------------------------------------
# Météo : détection LOCALE (regex) de l'intention + de la ville éventuelle,
# sans appeler Ollama. Le résultat vient d'Open-Meteo (tools/weather_tool.py),
# donc une connexion internet est nécessaire, mais aucune latence LLM.
# ---------------------------------------------------------------------------
 
_WEATHER_KEYWORDS = [
    "météo", "meteo", "quel temps fait", "quel temps qu'il fait",
    "il fait quel temps", "quel temps il fait",
]
_WEATHER_CITY_PATTERN = re.compile(
    r"\b(?:à|a|sur|pour|de)\s+([a-zà-ÿ][a-zà-ÿ\-\s]{1,30})\s*[?.!]*$"
)
 
 
def _try_local_weather(text_lower: str) -> str | None:
    if not any(k in text_lower for k in _WEATHER_KEYWORDS):
        return None
    match = _WEATHER_CITY_PATTERN.search(text_lower)
    city = match.group(1).strip() if match else None
    return weather_tool.get_weather(city)
 
# ---------------------------------------------------------------------------
# Configuration des intentions
# ---------------------------------------------------------------------------
 
_REQUIRED_FIELDS = {
    "send_email": ["to", "subject", "body"],
    "create_calendar_event": ["title", "start_iso", "end_iso"],
    "list_upcoming_events": [],
}
 
# Champs acceptés par intention (requis + optionnels), pour ignorer tout
# ce que l'extraction JSON pourrait inventer en trop.
_ALLOWED_FIELDS = {
    "send_email": ["to", "subject", "body"],
    "create_calendar_event": ["title", "start_iso", "end_iso", "description"],
    "list_upcoming_events": [],
}
 
# ---------------------------------------------------------------------------
# Nettoyage d'une adresse email dictée à voix haute
# ---------------------------------------------------------------------------
# La transcription STT rend souvent une adresse email de façon imparfaite :
# espaces entre les mots, "arobase"/"at" au lieu de "@", "point"/"dot" au
# lieu de ".", majuscule de début de phrase, ponctuation finale ajoutée
# ("gmail.com." ou "gmail.com !"). On corrige ça avant de valider.
 
_EMAIL_WORD_REPLACEMENTS = [
    (r"\barobase\b", "@"),
    (r"\bà\s*robas?e?\b", "@"),  # "à Robas"/"arobas" : mauvaise transcription fréquente
    (r"\barobas\b", "@"),
    (r"\bat\b", "@"),
    (r"\bpoint\b", "."),
    (r"\bdot\b", "."),
    (r"\btiret du bas\b", "_"),
    (r"\bunderscore\b", "_"),
    (r"\btiret\b", "-"),
]
 
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
 
# Si le STT n'a pas du tout capté le symbole "@" (cas fréquent : "usur.mae.el.5.gmail.com"),
# on tente de le réinsérer automatiquement juste avant le nom de domaine reconnu.
_KNOWN_EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "gmail", "yahoo", "outlook", "hotmail", "icloud",
]
 
 
def _insert_missing_at(text: str) -> str:
    if "@" in text:
        return text
    for domain in _KNOWN_EMAIL_DOMAINS:
        idx = text.rfind(domain)
        if idx > 0:
            local = text[:idx].rstrip(".")
            rest = text[idx:]
            if "." not in rest:
                rest = rest + ".com"
            return f"{local}@{rest}"
    return text
 
 
# Domaines connus dont le TLD peut être coupé net si l'enregistrement
# s'arrête juste avant la fin (ex. "gmail.c" au lieu de "gmail.com").
_KNOWN_DOMAIN_ROOTS = ["gmail", "yahoo", "outlook", "hotmail", "icloud"]
 
 
def _repair_truncated_domain(text: str) -> str:
    """Si le domaine ressemble à un début de 'gmail.com' etc. coupé en
    plein milieu (ex. 'gmail.c', 'gmail.co'), complète en 'gmail.com'."""
    if "@" not in text:
        return text
    local, _, domain = text.partition("@")
    for root in _KNOWN_DOMAIN_ROOTS:
        prefix = root + "."
        if domain.startswith(prefix):
            tld = domain[len(prefix):]
            if tld and tld != "com" and "com".startswith(tld):
                domain = prefix + "com"
            break
    return f"{local}@{domain}"
 
 
def _normalize_spoken_email(raw_text: str) -> str:
    text = raw_text.strip().lower()
    text = text.rstrip(" .!?،")  # ponctuation finale ajoutée par le STT
    for pattern, replacement in _EMAIL_WORD_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", "", text)  # espaces entre les mots dictés
    text = text.strip(".")  # point final résiduel après nettoyage
    return text
 
 
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
 
 
def _fuzzy_contains_name(text: str, name: str, threshold: float = 0.72) -> bool:
    """Le nom d'un contact est-il présent dans le texte dicté ? Tolère :
    - une sous-chaîne directe ('yosr' dans 'envoie à yosr stp') ;
    - un nom épelé avec séparateurs ('y-o-s-r', 'y o s r') ;
    - une transcription approximative du STT ('aysr' proche de 'yosr').
    """
    if not name:
        return False
    if name in text:
        return True
    # Nom épelé lettre par lettre, avec tirets/espaces/points entre chaque
    # caractère : on retire ces séparateurs avant de chercher.
    compact = re.sub(r"[\s\-.]", "", text)
    if name in compact:
        return True
    # Comparaison floue mot par mot, pour rattraper une transcription
    # phonétiquement proche mais pas identique.
    for token in re.findall(r"[a-zà-ÿ']+", text):
        if len(token) < 3:
            continue
        if difflib.SequenceMatcher(None, token, name).ratio() >= threshold:
            return True
    return False
 
 
def _lookup_contact(raw_text: str) -> str | None:
    """Cherche un nom de contact connu (tools/contacts.py) dans le texte
    dicté, ex. 'envoie un email à Yosr' -> adresse enregistrée pour 'yosr'.
    Sert de raccourci pratique, mais n'est jamais requis : toute adresse
    non enregistrée passe par le décodage ci-dessous.
    Insensible aux accents et tolérant aux petites erreurs de
    transcription (voir _fuzzy_contains_name)."""
    try:
        from tools import contacts as contacts_tool
    except Exception as e:
        _log.warning("Impossible de charger tools/contacts.py : %s", e)
        return None
 
    contacts = contacts_tool.load_contacts()
    if not contacts:
        _log.warning(
            "Carnet de contacts vide ou introuvable (CONTACTS_PATH=%s, "
            "chemin absolu résolu=%s). Aucun contact ne pourra être reconnu.",
            getattr(config, "CONTACTS_PATH", "?"),
            os.path.abspath(getattr(config, "CONTACTS_PATH", "credentials/contacts.json")),
        )
        return None
 
    text = _strip_accents(raw_text.strip().lower())
    for name, email in contacts.items():
        name_norm = _strip_accents(name)
        if _fuzzy_contains_name(text, name_norm):
            _log.info("Contact reconnu : '%s' -> %s (texte dicté : '%s')", name, email, raw_text)
            return email
 
    _log.info(
        "Aucun contact reconnu dans '%s' (contacts connus : %s)",
        raw_text, list(contacts.keys()),
    )
    return None
 
 
# ---------------------------------------------------------------------------
# Décodage d'une adresse ÉPELÉE lettre par lettre
# ---------------------------------------------------------------------------
# Whisper reconnaît beaucoup plus fiablement des lettres/chiffres/mots-clés
# isolés et bien détachés qu'une adresse dictée d'un bloc. On essaie donc
# systématiquement CE décodage en plus du nettoyage "normal" ci-dessus, pour
# n'importe quelle adresse (pas seulement celles d'un carnet de contacts).
 
_LETTER_NAMES = {
    "a": "a", "bé": "b", "be": "b", "cé": "c", "ce": "c", "dé": "d", "de": "d",
    "e": "e", "eu": "e", "effe": "f", "ef": "f", "gé": "g", "ge": "g",
    "hache": "h", "ash": "h", "i": "i", "ji": "j", "gi": "j", "ka": "k",
    "elle": "l", "aime": "m", "emme": "m", "enne": "n", "o": "o",
    "pé": "p", "pe": "p", "qu": "q", "ku": "q", "erre": "r", "esse": "s",
    "té": "t", "te": "t", "u": "u", "vé": "v", "ve": "v",
    "doublevé": "w", "iks": "x", "ix": "x", "igrec": "y", "zède": "z",
    "zede": "z",
}
 
_DIGIT_WORDS = {
    "zéro": "0", "zero": "0", "un": "1", "une": "1", "deux": "2",
    "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7",
    "huit": "8", "neuf": "9",
}
 
_SYMBOL_WORDS = {
    "arobase": "@", "at": "@", "point": ".", "dot": ".",
    "tiretdubas": "_", "underscore": "_", "tiret": "-",
}
 
 
def _decode_spelled_text(raw_text: str) -> str:
    """Interprète un texte comme une suite de lettres/chiffres/symboles
    dictés séparément, ex. 'y o s r point m a a l e l cinq arobase g m a i
    l point c o m' -> 'yosr.maalel5@gmail.com'. Les mots non reconnus comme
    lettre isolée sont gardés tels quels (utile si l'utilisateur mélange
    épellation et mots entiers, ex. 'y o s r point maalel cinq arobase
    gmail point com')."""
    text = raw_text.strip().lower()
    text = re.sub(r"[.,;:!?]+$", "", text)
    text = text.replace("tiret du bas", "tiretdubas")
    text = re.sub(r"double[\s-]?v[éeè]?", "doublevé", text)
    text = re.sub(r"i[\s-]?grec", "igrec", text)
 
    parts = []
    for token in text.split():
        tok = token.strip(".,;:!?")
        if not tok:
            continue
        if len(tok) == 1 and tok.isalpha():
            parts.append(tok)
        elif tok.isdigit():
            parts.append(tok)
        elif tok in _LETTER_NAMES:
            parts.append(_LETTER_NAMES[tok])
        elif tok in _DIGIT_WORDS:
            parts.append(_DIGIT_WORDS[tok])
        elif tok in _SYMBOL_WORDS:
            parts.append(_SYMBOL_WORDS[tok])
        else:
            parts.append(tok)  # mot entier gardé tel quel
    return "".join(parts)
 
 
def _set_field(intent: str, field: str, raw_value: str) -> bool:
    """Nettoie et valide une valeur avant de la stocker dans _pending.
    Retourne False si la valeur doit être redemandée à l'utilisateur.
 
    Pour le champ "to", on essaie dans l'ordre :
    1. un contact enregistré (raccourci pratique) ;
    2. le nettoyage "adresse dictée normalement" ;
    3. le décodage "adresse épelée lettre par lettre" —
       ceci fonctionne pour N'IMPORTE QUELLE adresse, pas seulement celles
       d'un carnet de contacts.
    """
    value = (raw_value or "").strip()
    if not value:
        return False
 
    if intent == "send_email" and field == "to":
        contact_email = _lookup_contact(value)
        if contact_email:
            _pending["args"][field] = contact_email
            # Un contact enregistré est fiable par définition : pas besoin
            # de faire relire/confirmer l'adresse, on passe directement à
            # la question suivante (sujet du message).
            _pending["to_confirmed"] = True
            return True
 
        candidate = _repair_truncated_domain(_insert_missing_at(_normalize_spoken_email(value)))
        if _EMAIL_REGEX.match(candidate):
            _pending["args"][field] = candidate
            return True
 
        spelled = _repair_truncated_domain(_insert_missing_at(_decode_spelled_text(value)))
        if _EMAIL_REGEX.match(spelled):
            _pending["args"][field] = spelled
            return True
 
        return False
 
    _pending["args"][field] = value
    return True
 
_FIELD_QUESTIONS = {
    ("send_email", "to"): (
        "À quelle adresse veux-tu envoyer l'email ? "
        "Tu peux aussi donner le nom d'un contact enregistré."
    ),
    ("send_email", "subject"): "Quel est le sujet de l'email ?",
    ("send_email", "body"): "Quel message veux-tu envoyer ?",
    ("create_calendar_event", "title"): "Quel est le titre de l'événement ?",
    ("create_calendar_event", "start_iso"): "À quelle date et heure commence l'événement ?",
    ("create_calendar_event", "end_iso"): "À quelle heure se termine l'événement ?",
}
 
_DISPATCH = {
    "send_email": lambda a: email_tool.send_email(
        to=a.get("to", ""), subject=a.get("subject", ""), body=a.get("body", "")
    ),
    "create_calendar_event": lambda a: calendar_tool.create_event(
        title=a.get("title", ""),
        start_iso=a.get("start_iso", ""),
        end_iso=a.get("end_iso", ""),
        description=a.get("description", ""),
    ),
    "list_upcoming_events": lambda a: calendar_tool.list_upcoming_events(
        max_results=a.get("max_results", 5)
    ),
}
 
_CANCEL_WORDS = {"annule", "annuler", "laisse tomber", "stop", "oublie ça", "oublie ca"}
_YES_WORDS = {"oui", "ouais", "yes", "exact", "correct", "c'est ça", "c'est ca", "affirmatif"}
_NO_WORDS = {"non", "no", "faux", "incorrect", "pas correct", "pas ça", "pas ca"}
 
_CLASSIFY_SYSTEM_PROMPT = """Tu es un module d'extraction d'intention pour un assistant vocal.
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte autour, au format exact :
{"intent": "send_email" | "create_calendar_event" | "list_upcoming_events" | "none", "args": {}}
 
Règles :
- "send_email" : champs possibles dans "args" -> to, subject, body
- "create_calendar_event" : champs possibles -> title, start_iso (ISO 8601), end_iso (ISO 8601), description
- "list_upcoming_events" : "args" reste vide {}
- Si l'utilisateur ne parle ni d'email ni de calendrier, retourne {"intent": "none", "args": {}}
- N'inclus dans "args" QUE les informations explicitement données par l'utilisateur dans ce message.
  Ne devine jamais une adresse, un sujet ou une date qui ne sont pas mentionnés.
"""
 
# ---------------------------------------------------------------------------
# État de la conversation en cours (slot-filling)
# ---------------------------------------------------------------------------
 
_pending = {"intent": None, "args": {}, "awaiting": None, "to_confirmed": False}
 
 
def _reset_pending():
    _pending["intent"] = None
    _pending["args"] = {}
    _pending["awaiting"] = None
    _pending["to_confirmed"] = False
 
 
def _missing_fields(intent: str) -> list[str]:
    required = _REQUIRED_FIELDS.get(intent, [])
    return [f for f in required if not _pending["args"].get(f)]
 
 
def _advance() -> str | None:
    """Renvoie soit une confirmation d'adresse, soit une question pour le
    champ manquant suivant, soit exécute l'outil si tout est prêt."""
    intent = _pending["intent"]
 
    # Avant d'aller plus loin, on fait confirmer l'adresse email par
    # l'utilisateur (le STT se trompe souvent sur les adresses dictées).
    if (
        intent == "send_email"
        and _pending["args"].get("to")
        and not _pending["to_confirmed"]
    ):
        _pending["awaiting"] = "confirm_to"
        return (
            f"J'ai compris l'adresse {_pending['args']['to']}. "
            "C'est correct ? Dis oui ou non."
        )
 
    missing = _missing_fields(intent)
    if missing:
        field = missing[0]
        return _FIELD_QUESTIONS.get((intent, field), f"Peux-tu préciser : {field} ?")
 
    handler = _DISPATCH.get(intent)
    args = dict(_pending["args"])
    _reset_pending()
    if not handler:
        return None
    return handler(args)
 
 
def _classify_intent(user_text: str):
    """Appel direct à Ollama (mode JSON) pour extraire intention + champs
    déjà présents dans le texte. Renvoie (intent, args) ou (None, {})."""
    try:
        client = ollama.Client(host=config.OLLAMA_HOST)
        response = client.chat(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            format="json",
        )
        message = response.get("message", {}) if isinstance(response, dict) else getattr(
            response, "message", {}
        )
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        data = json.loads(content)
        return data.get("intent"), (data.get("args") or {})
    except Exception:
        # Ollama injoignable, JSON invalide, modèle non installé, etc.
        return None, {}
 
 
# ---------------------------------------------------------------------------
# Point d'entrée utilisé par assistant.py
# ---------------------------------------------------------------------------
 
def try_handle_tool_intent(user_text: str) -> str | None:
    """Renvoie une réponse à faire lire par le TTS (confirmation, ou question
    de relance) si l'échange concerne un email/calendrier, sinon None
    (l'appelant doit alors utiliser le flux LLM normal :
    self.llm.generate_response(user_text))."""
    if not user_text or not user_text.strip():
        return None
 
    text_lower = user_text.strip().lower()
 
    # Heure/date/météo : réponse locale, sans appeler Ollama, sauf si on est
    # déjà en train de remplir un email/événement (peu probable mais on
    # évite d'interrompre une conversation en cours).
    if not _pending["intent"]:
        local_reply = _try_local_time_date(text_lower)
        if local_reply is not None:
            return local_reply
        weather_reply = _try_local_weather(text_lower)
        if weather_reply is not None:
            return weather_reply
 
    # Une confirmation d'adresse email est en attente.
    if _pending["intent"] and _pending.get("awaiting") == "confirm_to":
        if any(word in text_lower for word in _NO_WORDS):
            _pending["args"].pop("to", None)
            _pending["to_confirmed"] = False
            _pending["awaiting"] = None
            return _advance()
        if any(word in text_lower for word in _YES_WORDS):
            _pending["to_confirmed"] = True
            _pending["awaiting"] = None
            return _advance()
        return "Dis simplement oui ou non : l'adresse est-elle correcte ?"
 
    # Conversation déjà en cours : ce message répond à la question posée,
    # ou l'annule.
    if _pending["intent"]:
        if any(word in text_lower for word in _CANCEL_WORDS):
            _reset_pending()
            return "D'accord, j'annule."
        intent = _pending["intent"]
        field = _missing_fields(intent)[0]
        if not _set_field(intent, field, user_text):
            if field == "to":
                return (
                    "Cette adresse ne semble pas valide. Essaie de l'épeler "
                    "lettre par lettre, doucement : par exemple y, o, s, r, "
                    "point, m, a, a, l, e, l, cinq, arobase, g, m, a, i, l, "
                    "point, c, o, m."
                )
            return _FIELD_QUESTIONS.get((intent, field), f"Peux-tu répéter : {field} ?")
        return _advance()
 
    # Nouvelle demande : on classifie l'intention.
    intent, extracted_args = _classify_intent(user_text)
    if not intent or intent == "none":
        return None
 
    _pending["intent"] = intent
    _pending["args"] = {}
    allowed = _ALLOWED_FIELDS.get(intent, [])
    for field, value in (extracted_args or {}).items():
        if field in allowed and isinstance(value, str):
            # Si la valeur extraite d'emblée est invalide (ex. adresse mal
            # transcrite dans la même phrase), on l'ignore : elle sera
            # simplement redemandée par _advance().
            _set_field(intent, field, value)
    return _advance()
 
