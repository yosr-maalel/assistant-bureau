"""
push_to_talk.py — enregistrement ET transcription 100% autonomes, au
clavier, SANS AUCUNE dépendance ni modification à stt.py.

Fonctionnement :
    - Appuie sur ENTRÉE pour DÉMARRER l'enregistrement.
    - Parle.
    - Appuie sur ESPACE pour ARRÊTER l'enregistrement et lancer la
      transcription.

Aucun VAD, aucun seuil de bruit — utile dans un environnement bruyant où
la détection automatique de silence se déclenche n'importe comment.

Ce module charge SON PROPRE modèle Whisper (faster-whisper), avec les
mêmes réglages que ceux vus dans tes logs (modele=small, device=cpu,
compute_type=int8, langue=fr), pour un résultat cohérent avec le reste de
l'assistant — mais géré entièrement ici, indépendamment de stt.py.

⚠️ Conséquence : deux modèles Whisper "small" existent en mémoire en
même temps (celui de stt.py + celui-ci), soit environ +500 Mo à 1 Go de
RAM en plus. C'est le compromis nécessaire pour ne toucher à AUCUNE ligne
de stt.py, comme demandé.

Dépendances :
    pip install keyboard sounddevice numpy faster-whisper

⚠️ Sous Windows, le paquet "keyboard" a besoin de droits administrateur
pour capter les touches globalement. Lance PowerShell "en tant
qu'administrateur" si l'écoute clavier ne réagit pas.
"""
import sys
import os
import threading
import numpy as np
import sounddevice as sd
import keyboard
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(__file__))
import config  # noqa: E402

_SAMPLE_RATE = getattr(config, "STT_SAMPLE_RATE", 16000)
_START_KEY = os.getenv("PUSH_TO_TALK_START_KEY", "enter")
_STOP_KEY = os.getenv("PUSH_TO_TALK_STOP_KEY", "space")

# Mêmes valeurs par défaut que celles vues dans tes logs STTEngine ; si tu
# as ces noms dans config.py ils seront utilisés automatiquement, sinon
# ces valeurs par défaut s'appliquent (identiques à ton stt.py actuel).
_MODEL_SIZE = getattr(config, "STT_MODEL", "small")
_DEVICE = getattr(config, "STT_DEVICE", "cpu")
_COMPUTE_TYPE = getattr(config, "STT_COMPUTE_TYPE", "int8")
_LANGUAGE = getattr(config, "STT_LANGUAGE", "fr")

_model = None  # chargé une seule fois, à la première utilisation

_frames = []
_is_recording = False
_lock = threading.Lock()


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print("[Push-to-talk] Chargement de son propre modèle Whisper "
              f"({_MODEL_SIZE}, {_DEVICE}, {_COMPUTE_TYPE})...")
        _model = WhisperModel(_MODEL_SIZE, device=_DEVICE, compute_type=_COMPUTE_TYPE)
    return _model


def _audio_callback(indata, frames, time_info, status):
    if _is_recording:
        with _lock:
            _frames.append(indata.copy())


def record_between_keys(start_key: str = _START_KEY, stop_key: str = _STOP_KEY) -> np.ndarray:
    """Attend `start_key` pour démarrer l'enregistrement, enregistre en
    tâche de fond (callback audio, indépendant du thread clavier) jusqu'à
    `stop_key`. Retourne l'audio (mono float32, _SAMPLE_RATE Hz)."""
    global _frames, _is_recording

    print(f"[Push-to-talk] Appuie sur [{start_key.upper()}] pour démarrer l'enregistrement...")
    keyboard.wait(start_key)

    with _lock:
        _frames = []
    _is_recording = True
    print(f"[Push-to-talk] 🔴 Enregistrement... Appuie sur [{stop_key.upper()}] pour arrêter.")

    stream = sd.InputStream(
        samplerate=_SAMPLE_RATE, channels=1, dtype="float32", callback=_audio_callback
    )
    with stream:
        keyboard.wait(stop_key)

    _is_recording = False
    print("[Push-to-talk] ⏹️ Enregistrement terminé.")

    with _lock:
        if not _frames:
            return np.array([], dtype="float32")
        return np.concatenate(_frames, axis=0).flatten()


def transcribe(audio: np.ndarray) -> str:
    """Transcrit un tableau audio en texte, avec le modèle Whisper propre
    à ce module (stt.py n'est jamais sollicité)."""
    if audio.size == 0:
        return ""
    model = _get_model()
    segments, _info = model.transcribe(audio, language=_LANGUAGE)
    return " ".join(seg.text.strip() for seg in segments).strip()


def listen_and_transcribe(start_key: str = _START_KEY, stop_key: str = _STOP_KEY) -> str:
    """Fonction tout-en-un à appeler depuis assistant.py à la place de
    l'écoute automatique existante : Entrée pour démarrer, Espace pour
    arrêter, puis transcription, puis retourne le texte."""
    audio = record_between_keys(start_key, stop_key)
    return transcribe(audio)


if __name__ == "__main__":
    texte = listen_and_transcribe()
    print("Texte reconnu :", texte)

