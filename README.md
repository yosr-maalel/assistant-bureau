# **Assistant Bureau**

A local, offline-first **voice AI desk assistant** (STT → LLM/tools → TTS) built in
Python, with a modern web interface and push-to-talk **START / STOP** buttons.

---

## **1. Overview**

Assistant Bureau listens through a microphone, transcribes speech, decides whether
the request is a tool action (email, calendar, weather, time) or a normal
conversation, generates a reply with a local language model, and speaks it out loud.
The speech and language models run locally; only the tools (Gmail, Google Calendar,
Open-Meteo weather) need internet.

You talk to it in two ways:

- **Web interface (recommended):** a dark, animated page with a central orb, a live
  waveform, clear state indicators and a conversation log. You press **START TALKING**,
  speak, then press **STOP TALKING**. Nothing is cut off by automatic silence
  detection, which makes it usable in a noisy room and with a headset.
- **Terminal (original mode):** continuous listening with automatic voice-activity
  detection (`python assistant.py`).

Both modes use **the same pipeline**. The interface controls the existing assistant;
it never replaces the STT, LLM, TTS or tools.

## **2. Features**

- 🎙️ **Push-to-talk web UI** with START / STOP buttons (and the Space key).
- 🚦 **Clear states:** `READY`, `🔴 LISTENING`, `⚙️ PROCESSING`, `🔊 SPEAKING`, plus `CHARGEMENT` while models load.
- 📈 **Live waveform** while recording and a colour-changing orb per state.
- 💬 **Conversation log** with distinct user / assistant bubbles and a **New conversation** button (clears history, LLM memory and any half-finished email).
- 🗣️ **Local speech-to-text** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- 🧠 **Local LLM** through [Ollama](https://ollama.com) (default `qwen2.5:3b`).
- 🔊 **Local text-to-speech** with [Piper](https://github.com/rhasspy/piper).
- 🛠️ **Voice tools** (`tool_orchestrator.py`):
  - send an email (Gmail), with step-by-step questions for missing fields,
    spoken-address decoding, letter-by-letter spelling and a contacts book;
  - create a Google Calendar event / list upcoming events;
  - weather (Open-Meteo) and current time/date (answered locally, instantly).
- 🔌 **Optional MCP server** (`integrations/mcp_server.py`) exposing the email and calendar tools to any MCP client.
- 🎧 **Headset support:** choose the microphone with `MIC_DEVICE`; recordings are volume-normalised before transcription.
- ⚡ **Faster start:** Whisper and the Ollama model are warmed up in the background at launch.
- 🛡️ Defensive error handling: a failing tool, model or microphone never crashes the assistant.
- 🧪 Automated unit tests with mocked hardware and network.

## **3. Architecture**

```
Web page (browser)
   │  START / STOP / NEW CONVERSATION (HTTP, localhost)
   ▼
ui_server.py ──► records the microphone (sounddevice)
   │
   ▼
Assistant.stt.transcribe_audio()      ← existing STT (faster-whisper)
   │
   ▼
Assistant.handle_text()               ← existing pipeline
   ├─ stop word?          → goodbye
   ├─ tool_orchestrator   → email / calendar / weather / time
   └─ LLM (Ollama)        → normal conversation
   │
   ▼
tts.speak()                           ← existing TTS (Piper)
```

The page is only a front end: it shows the state and sends button clicks.
Speech recognition, the LLM, the tools and the voice all run in Python.

## **4. How it works**

1. **START TALKING** — `ui_server.py` opens the microphone (16 kHz, mono) and the state becomes `LISTENING`.
2. **STOP TALKING** — recording stops immediately. Recordings that are too short (< 0.3 s) or almost silent are rejected with a message.
3. The audio is volume-normalised and passed to the existing `STTEngine.transcribe_audio()`.
4. `Assistant.handle_text()` checks for a stop word, then tries the tools, then falls back to the LLM.
5. The reply is spoken with Piper (`SPEAKING`) and shown in the log; the state returns to `READY`.

Tool conversations are multi-turn: "send an email" → the assistant asks for the
address, confirms it, asks for the subject and the message. Each answer is one
START / STOP press.

## **5. Repository structure**

```
assistant-bureau/
├── README.md
├── requirements.txt
├── .gitignore
├── lancer_assistant.bat        <- optional Windows one-click launcher
└── src/
    ├── assistant.py            <- pipeline: run_one_turn() and handle_text()
    ├── ui_server.py            <- local web server + microphone recording
    ├── ui/
    │   └── index.html          <- the interface
    ├── stt.py                  <- faster-whisper + webrtcvad (unchanged)
    ├── llm.py                  <- Ollama conversation (unchanged)
    ├── tts.py                  <- Piper (unchanged)
    ├── tool_orchestrator.py    <- email / calendar / weather / time intents
    ├── push_to_talk.py         <- old standalone keyboard recorder (not used by the UI)
    ├── config.py               <- all configuration
    ├── tools/                  <- email_tool, calendar_tool, weather_tool, contacts
    ├── integrations/
    │   └── mcp_server.py       <- optional MCP server (stdio)
    ├── credentials/            <- Google credentials, token, contacts (NOT committed)
    ├── models/                 <- Piper voice + Whisper cache (NOT committed)
    └── tests/                  <- unit tests, one file per module
```

> The `tools/`, `integrations/` and `credentials/` layout is the one used by the
> imports in `tool_orchestrator.py` and `mcp_server.py`. Adjust this tree if your
> folders differ.

## **6. Requirements**

- Windows 10/11 (developed and tested), or Linux
- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- A microphone (a headset works well) and speakers
- About 2 GB of free RAM for Whisper `small` + `qwen2.5:3b` + Piper
- For email/calendar: a Google Cloud project with the Gmail and Calendar APIs enabled
- Linux only: `libportaudio2` and `alsa-utils` (or `pulseaudio-utils`)

## **7. Installation (Windows / PowerShell)**

```powershell
git clone https://github.com/<your-user>/assistant-bureau.git
cd assistant-bureau

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

ollama pull qwen2.5:3b
```

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Piper voice** — download the `.onnx` file once into `src/models/`:

```powershell
cd src\models
curl.exe -L -o fr_FR-siwis-medium.onnx "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
cd ..\..
```

The Whisper model downloads itself into `src/models/whisper/` the first time you run
the assistant (internet needed once).

**Google credentials** — put `google_credentials.json` in `src/credentials/`.
A `token.json` is created on the first authorised use. Optionally create
`src/credentials/contacts.json` (`{"yosr": "yosr@example.com"}`) to send emails by name.

## **8. Running**

### **Web interface**

```powershell
cd assistant-bureau
.\venv\Scripts\Activate.ps1
cd src
$env:MIC_DEVICE="8"      # optional, see section 9
python ui_server.py
```

Then open **http://127.0.0.1:8765**. Wait until the state changes from
`CHARGEMENT` to `READY`, press **START TALKING**, speak, press **STOP TALKING**.

### **Terminal mode**

```powershell
cd src
python assistant.py
```

Say **"stop"** or **"arrêt"** (or press Ctrl+C) to quit.

### **One-click launcher (optional)**

`lancer_assistant.bat` at the project root:

```bat
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
cd src
start "" http://127.0.0.1:8765
python ui_server.py
pause
```

## **9. Using a headset / choosing the microphone**

List the input devices:

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Pick a line that matches your headset with `in` greater than 0, then set its number.
Prefer the **MME** or **DirectSound** entry; WASAPI and WDM-KS often reject 16 kHz.

```powershell
$env:MIC_DEVICE="8"
python ui_server.py
```

Without `MIC_DEVICE`, the Windows default input device is used (Settings → System →
Sound → Input). Bluetooth headsets switch to a lower-quality "hands-free" mode when
the microphone is active; a wired or USB headset transcribes better in noise.

## **10. Interface states**

| State | Meaning |
| ----- | ------- |
| `⏳ CHARGEMENT…` | Models are loading (first start takes longer) |
| `READY` | Waiting for you; START is enabled |
| `🔴 LISTENING…` | Microphone active, waveform moving; STOP is enabled |
| `⚙️ PROCESSING` | Transcribing and thinking |
| `🔊 SPEAKING` | The assistant is talking |

Small local API used by the page (all on `127.0.0.1`): `GET /api/state`,
`POST /api/start`, `POST /api/stop`, `POST /api/reset`.

## **11. Configuration**

All settings live in `src/config.py` and can be overridden with environment variables.

| Group | Examples |
| ----- | -------- |
| LLM | `OLLAMA_HOST`, `LLM_MODEL`, `LLM_TIMEOUT`, `MAX_HISTORY`, `SYSTEM_PROMPT` |
| TTS | `TTS_VOICE_NAME`, `TTS_MODELS_DIR`, `TTS_PLAYER_CMD` |
| STT | `STT_MODEL`, `STT_DEVICE`, `STT_LANGUAGE`, `STT_MODEL_DIR` |
| VAD (terminal mode) | `STT_VAD_MODE`, `STT_SILENCE_DURATION` |
| Assistant | `ASSISTANT_STOP_WORDS`, `ASSISTANT_ERROR_MESSAGE` |
| UI | `MIC_DEVICE` (read by `ui_server.py`) |
| Google | credentials paths under `src/credentials/`, `CONTACTS_PATH` |

## **12. Testing**

```powershell
cd src
python -m py_compile assistant.py ui_server.py
python -m unittest discover -v
```

Tests mock the microphone, speaker, Whisper and Ollama, so they run anywhere.
Integration tests are skipped unless `RUN_INTEGRATION=1` is set. The `pkg_resources`
warning printed by `webrtcvad` is harmless, and the tracebacks in the STT tests are
simulated failures.

Manual checklist for the interface: START turns the orb red and moves the waveform;
STOP goes `PROCESSING → SPEAKING → READY`; "quelle heure est-il", "quelle est la météo à Tunis",
"envoie un email" and "quels sont mes prochains événements" all trigger their tools;
"stop" says goodbye and leaves the page open; **New conversation** clears the log.

## **13. Troubleshooting**

| Problem | Cause | Solution |
| ------- | ----- | -------- |
| `ModuleNotFoundError: No module named 'numpy'` | Virtual environment not activated | `.\venv\Scripts\Activate.ps1`, or run `..\venv\Scripts\python.exe ui_server.py` |
| Page stuck on `CHARGEMENT` | Whisper still loading, or the model is downloading | Open `/api/state`; watch the server terminal; check `STT_MODEL` is not set to an undownloaded model |
| Page shows old conversation | The server keeps history in memory | Use **New conversation**, or restart `ui_server.py` |
| New conversation button does nothing | Old `ui_server.py` still running, or missing `/api/reset` | Stop the server (Ctrl+C), update the files, restart, then Ctrl+F5 |
| "Micro trop faible" | Wrong device or muted headset | Set `MIC_DEVICE` to the right number; speak closer |
| `Invalid sample rate` | Device rejects 16 kHz | Choose an MME or DirectSound entry |
| "Le modele n'a reconnu aucun texte" | No audible speech in the recording | Wait half a second after START; press STOP right after speaking |
| Ollama unreachable / model not found | Ollama not running or model missing | Start Ollama; `ollama pull qwen2.5:3b` |
| Piper model not found | `.onnx` file missing | Download it into `src/models/` |
| Gmail / Calendar errors | Missing or expired credentials | Check `src/credentials/`; delete `token.json` to re-authorise |
| `python -m unittest` finds 0 tests | Wrong folder | Run from `src/` |

## **14. `push_to_talk.py`**

This was an earlier standalone keyboard recorder (Enter to start, Space to stop). It is
**not used** by the interface: it loads its own second Whisper model (extra RAM),
needs global keyboard hooks (administrator rights on Windows) and records `float32`
audio while `stt.py` expects `int16`. It can stay in the repository or be removed.

## **15. MCP server (optional)**

`src/integrations/mcp_server.py` exposes `send_email`, `create_calendar_event` and
`list_upcoming_events` to any MCP client (for example Claude Desktop). The voice
assistant does **not** need it: `tool_orchestrator.py` calls the tools directly.

```powershell
cd src
python integrations\mcp_server.py
```

## **16. Git workflow**

- Keep `main` stable and runnable.
- Never commit `credentials/`, `token.json`, model weights, logs or `venv/`.
- Run the tests before pushing.
- Use clear commit messages.

```powershell
git status
git add <files>
git commit -m "Describe what changed and why"
git push
```

## **17. FAQ**

**Do I need internet?** Only for the first model downloads and for the Gmail,
Calendar and weather tools.

**Can I change the assistant's name or personality?** The name shown on the page is
in `src/ui/index.html`. To change how it introduces itself, edit `SYSTEM_PROMPT` in `config.py`.

**Can I use another language?** Yes: set `STT_LANGUAGE`, choose another Piper voice with
`TTS_VOICE_NAME`, and rewrite `SYSTEM_PROMPT`. The tool phrases in
`tool_orchestrator.py` are French.

**Why press STOP manually?** Automatic silence detection often triggers wrongly in a
noisy room; manual control is more reliable. The terminal mode still uses automatic detection.

**Does this send my audio anywhere?** No. Recording, transcription, the LLM and the
voice run on your machine.
