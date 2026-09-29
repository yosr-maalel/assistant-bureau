"""
weather_tool.py — météo actuelle via Open-Meteo (API gratuite, sans clé,
sans inscription : https://open-meteo.com/).

Deux appels :
1. géocodage : nom de ville -> latitude/longitude
2. prévisions : latitude/longitude -> météo actuelle

Nécessite une connexion internet (comme Gmail/Calendar). Nécessite le
paquet "requests" (voir requirements_additions.txt).
"""
import sys
import os
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config  # noqa: E402

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Codes météo OMM (WMO weather code) -> description en français
_WMO_DESCRIPTIONS = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux",
    3: "couvert", 45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine modérée", 55: "bruine dense",
    61: "pluie légère", 63: "pluie modérée", 65: "forte pluie",
    66: "pluie verglaçante légère", 67: "pluie verglaçante forte",
    71: "chute de neige légère", 73: "chute de neige modérée",
    75: "forte chute de neige", 77: "neige en grains",
    80: "averses légères", 81: "averses modérées", 82: "averses violentes",
    85: "averses de neige légères", 86: "averses de neige fortes",
    95: "orage", 96: "orage avec grêle légère", 99: "orage avec grêle forte",
}


def _geocode(city: str):
    resp = requests.get(
        _GEOCODE_URL,
        params={"name": city, "count": 1, "language": "fr"},
        timeout=5,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return None
    top = results[0]
    return top["latitude"], top["longitude"], top.get("name", city)


def get_weather(city: str | None = None) -> str:
    """Retourne une phrase météo à faire lire par le TTS. Utilise
    config.DEFAULT_CITY si aucune ville n'est précisée dans la demande."""
    city = (city or getattr(config, "DEFAULT_CITY", "Tunis")).strip()
    try:
        geo = _geocode(city)
        if not geo:
            return f"Je n'ai pas trouvé la ville {city}."
        lat, lon, resolved_name = geo

        resp = requests.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=5,
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        wind = current.get("wind_speed_10m")
        description = _WMO_DESCRIPTIONS.get(code, "conditions variables")

        phrase = f"À {resolved_name}, il fait {round(temp)} degrés, {description}."
        if wind is not None:
            phrase += f" Vent à {round(wind)} kilomètres heure."
        return phrase
    except requests.RequestException:
        return "Je n'ai pas pu récupérer la météo : pas de connexion internet."
    except Exception as e:
        return f"Je n'ai pas pu récupérer la météo : {e}"


if __name__ == "__main__":
    print(get_weather())
    print(get_weather("Paris"))
