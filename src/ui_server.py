"""ui_server.py — interface web Assistant Bureau. Pilote l'Assistant existant (STT->outils/LLM->TTS).
Lancer :  cd src && python ui_server.py   puis ouvrir http://127.0.0.1:8765"""
import json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import sounddevice as sd

import config
import tool_orchestrator
from assistant import Assistant
from stt import STTError, STTEmptyAudioError
from tts import speak

PORT = 8765
_dev = os.environ.get("MIC_DEVICE")
DEVICE = int(_dev) if _dev not in (None, "") else None  # None = micro par défaut de Windows
UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

lock = threading.Lock()
S = {"state": "LOADING", "level": 0.0, "history": [], "notice": ""}
frames, stream = [], None


def set_state(state, notice=""):
    with lock:
        S["state"], S["notice"] = state, notice


def add_msg(role, text):
    with lock:
        S["history"].append({"role": role, "text": text})


def speak_with_state(text):
    set_state("SPEAKING")
    speak(text)  # TTS existant, inchangé


assistant = Assistant(speak_fn=speak_with_state)


def _callback(indata, n, t, status):
    frames.append(indata.copy())
    rms = float(np.sqrt(np.mean(indata.astype("float32") ** 2)))
    S["level"] = min(1.0, rms / 6000)


def start_recording():
    global stream, frames
    with lock:
        if S["state"] != "READY":
            return
    frames = []
    stream = sd.InputStream(samplerate=config.STT_SAMPLE_RATE, channels=config.STT_CHANNELS,
                            dtype="int16", device=DEVICE, callback=_callback)
    stream.start()
    set_state("LISTENING")


def _prepare(audio):
    """Retire l'offset et remonte le volume (gain limité) pour une voix faible."""
    x = audio.astype("float32").flatten()
    x -= np.mean(x)
    peak = float(np.max(np.abs(x))) or 1.0
    x *= min(20.0, 20000.0 / peak)
    return x.astype("int16").reshape(-1, 1)


def stop_recording():
    global stream
    with lock:
        if S["state"] != "LISTENING":
            return
    stream.stop(); stream.close(); stream = None  # micro coupé immédiatement
    S["level"] = 0.0
    audio = np.concatenate(frames, axis=0) if frames else np.array([], dtype="int16")
    if audio.size < config.STT_SAMPLE_RATE * 0.3:
        set_state("READY", "Enregistrement trop court, réessayez.")
        return
    if float(np.max(np.abs(audio))) < 300:
        set_state("READY", "Micro trop faible : vérifiez le casque ou parlez plus près.")
        return
    audio = _prepare(audio)
    set_state("PROCESSING")
    threading.Thread(target=_process, args=(audio,), daemon=True).start()


def _process(audio):
    try:
        text = assistant.stt.transcribe_audio(audio)      # STT existant
        add_msg("user", text)
        keep_going, reply = assistant.handle_text(text)   # outils/LLM + TTS existants
        if reply:
            add_msg("assistant", reply)
        if not keep_going:  # "stop" : l'UI reste ouverte, on annule l'email/événement en cours
            tool_orchestrator._reset_pending()
        set_state("READY")
    except STTEmptyAudioError:
        set_state("READY", "Aucun son enregistré.")
    except STTError as exc:
        add_msg("assistant", config.ASSISTANT_ERROR_MESSAGE)
        assistant._safe_speak(config.ASSISTANT_ERROR_MESSAGE)
        set_state("READY", f"Erreur STT : {exc}")
    except Exception as exc:  # ne jamais bloquer l'UI
        set_state("READY", f"Erreur : {exc}")


def reset_conversation():
    with lock:
        if S["state"] != "READY":
            return
        S["history"] = []
        S["notice"] = ""
    try:
        assistant.llm.reset_history()      # mémoire du LLM (méthode existante de llm.py)
    except Exception:
        pass
    tool_orchestrator._reset_pending()     # annule un email/événement en cours


def _warm_llm():
    """Charge qwen dans Ollama en avance (n'affecte pas l'historique du LLMEngine)."""
    try:
        import ollama
        ollama.Client(host=config.OLLAMA_HOST).chat(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": "ok"}],
            keep_alive="30m",
        )
    except Exception:
        pass  # non bloquant


def _load():
    try:
        set_state("LOADING", "Chargement du modèle vocal…")
        assistant.stt._load_model_timed()
        try:  # échauffement : 1 s de silence, le résultat vide est ignoré
            assistant.stt.transcribe_audio(np.zeros(config.STT_SAMPLE_RATE, dtype="int16"))
        except Exception:
            pass
        set_state("READY")
    except Exception as exc:
        set_state("READY", f"Modèle STT : {exc}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/state":
            with lock:
                return self._send(200, json.dumps(S))
        with open(UI_FILE, "rb") as f:
            self._send(200, f.read(), "text/html")

    def do_POST(self):
        try:
            if self.path == "/api/start":
                start_recording()
            elif self.path == "/api/stop":
                stop_recording()
            elif self.path == "/api/reset":
                reset_conversation()
        except Exception as exc:
            set_state("READY", f"Erreur : {exc}")
        self._send(200, "{}")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=_load, daemon=True).start()
    threading.Thread(target=_warm_llm, daemon=True).start()
    print(f"Interface : http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()