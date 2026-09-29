"""
contacts.py — petit carnet d'adresses local pour dire "envoie un email à
Yosr" au lieu de dicter une adresse email lettre par lettre au STT (peu
fiable : symboles "@", chiffres, noms rares mal reconnus).

Format de credentials/contacts.json (à créer toi-même, pas fourni ici) :

{
    "yosr": "yosr.maalel5@gmail.com",
    "rami": "rami.example@gmail.com"
}

- Les clés sont en minuscules.
- Elles sont recherchées comme sous-chaîne dans ce que dit l'utilisateur :
  "envoie un email à Yosr, sujet réunion" contient "yosr" -> trouvé.
- Si le fichier n'existe pas encore, le carnet est simplement vide (aucune
  erreur) : l'assistant redemande alors l'adresse à dicter normalement.
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config  # noqa: E402

_log = logging.getLogger("robot_assistant.contacts")
_cache: dict | None = None


def load_contacts() -> dict:
    """Charge (et met en cache) le carnet de contacts depuis
    config.CONTACTS_PATH. Retourne {} si le fichier est absent ou invalide.
    N'est mis en cache qu'un chargement RÉUSSI : si le fichier est absent,
    on réessaie à chaque appel (utile si le fichier est créé après le
    démarrage de l'assistant, sans avoir à le redémarrer)."""
    global _cache
    if _cache is not None:
        return _cache

    path = getattr(config, "CONTACTS_PATH", "credentials/contacts.json")
    if not os.path.exists(path):
        _log.warning(
            "Fichier de contacts introuvable : '%s' (chemin absolu : '%s'). "
            "Vérifie CONTACTS_PATH dans config.py et le dossier d'où tu "
            "lances python assistant.py.",
            path, os.path.abspath(path),
        )
        return {}  # pas de mise en cache : on réessaiera au prochain appel

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        _cache = {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
        _log.info("Carnet de contacts chargé : %d contact(s) depuis '%s'.", len(_cache), path)
    except Exception as e:
        _log.warning("Erreur de lecture de '%s' : %s", path, e)
        return {}  # pas de mise en cache non plus ici : fichier peut-être en cours d'écriture
    return _cache


def reload_contacts() -> dict:
    """Force le rechargement du fichier (utile après une modification à
    chaud sans redémarrer l'assistant)."""
    global _cache
    _cache = None
    return load_contacts()
