# Ajout MCP : envoi d'email + Google Calendar

Ces fichiers s'ajoutent au repo `ai-assitant` **sans toucher** à `stt.py`,
`llm.py`, ni `tts.py` — conformément à la Section 16 du README
("Adding Project-Specific Functions / Skills").

## 1. Où placer les fichiers dans ton repo

```
src/
├── assistant.py          <- à PATCHER (voir §5, 3 lignes à ajouter)
├── config.py              <- à COMPLÉTER (voir config_additions.py)
├── stt.py                 <- INCHANGÉ
├── llm.py                 <- INCHANGÉ
├── tts.py                 <- INCHANGÉ
├── tool_orchestrator.py   <- NOUVEAU (copier tel quel)
├── tools/
│   ├── __init__.py         <- fichier vide, à créer
│   ├── email_tool.py        <- NOUVEAU
│   └── calendar_tool.py     <- NOUVEAU
├── integrations/
│   ├── __init__.py         <- fichier vide, à créer
│   ├── google_auth.py       <- NOUVEAU
│   └── mcp_server.py        <- NOUVEAU (serveur MCP autonome, optionnel)
└── credentials/             <- NOUVEAU dossier, à AJOUTER AU .gitignore
    ├── google_credentials.json   <- tu le télépharges depuis Google Cloud
    └── google_token.json         <- généré automatiquement au 1er lancement
```

**Important** : ajoute `src/credentials/` à `.gitignore` (ne jamais commit
tes identifiants Google).

## 2. Configuration Google Cloud (une seule fois)

1. Va sur https://console.cloud.google.com/ et crée un projet (ou utilises-en un).
2. Active deux APIs : **Gmail API** et **Google Calendar API**
   (menu "APIs & Services" → "Enable APIs and Services").
3. "APIs & Services" → "OAuth consent screen" : type **External**, ajoute
   ton adresse Gmail comme "test user".
4. "APIs & Services" → "Credentials" → "Create Credentials" →
   **OAuth client ID** → type **Desktop app**.
5. Télécharge le JSON et enregistre-le sous
   `src/credentials/google_credentials.json`.

Au premier lancement de l'assistant, une page de navigateur s'ouvrira pour
autoriser l'accès ; un `google_token.json` sera créé automatiquement et
réutilisé ensuite (pas besoin de se reconnecter à chaque fois).

## 3. Dépendances (`requirements.txt`)

Ajoute les lignes de `requirements_additions.txt` à la fin de ton
`requirements.txt`, puis :

```bash
pip install -r requirements.txt
```

## 4. `config.py`

Ajoute le contenu de `config_additions.py` à la fin de ton `src/config.py`
existant (ne remplace rien, juste un ajout).

## 5. Patch de `assistant.py` (3 lignes)

Dans `src/assistant.py`, trouve la méthode `run_one_turn()` (ou équivalent)
à l'endroit où le texte transcrit (`user_text`) est envoyé au LLM. Juste
**avant** l'appel à `self.llm.chat(user_text)`, ajoute :

```python
from tool_orchestrator import try_handle_tool_intent

# ... dans run_one_turn(), avant l'appel LLM normal :
tool_reply = try_handle_tool_intent(user_text)
if tool_reply is not None:
    reply_text = tool_reply
else:
    reply_text = self.llm.chat(user_text)
```

C'est tout : `stt.py`, `llm.py`, `tts.py` restent intacts. Si aucune
intention email/calendrier n'est détectée, `try_handle_tool_intent` renvoie
`None` et le flux normal (LLM conversationnel) continue exactement comme
avant.

## 6. Comment ça marche

- `tool_orchestrator.py` fait son **propre** appel direct à Ollama (pas via
  `llm.py`) avec la liste d'outils (`tools=[...]`), pour détecter si le
  texte de l'utilisateur correspond à "envoyer un email" ou "créer un
  événement".
- Si oui, il extrait les paramètres (destinataire, sujet, corps, titre,
  horaires...) et appelle directement `tools/email_tool.py` ou
  `tools/calendar_tool.py`, qui parlent à l'API Gmail/Calendar via OAuth2.
- Le texte renvoyé (ex. "Email envoyé à ...") est ensuite lu à voix haute
  par ton `tts.py` existant, sans aucune modification de ce fichier.

`integrations/mcp_server.py` est un **serveur MCP autonome** séparé — utile
si tu veux aussi connecter ces mêmes outils (email/calendrier) à Claude
Desktop ou un autre client MCP, indépendamment de la boucle vocale.
Il n'est pas nécessaire au fonctionnement de l'assistant vocal lui-même.

## 7. Tester

```bash
cd src
python tools/email_tool.py       # test manuel d'envoi (voir bas du fichier)
python tools/calendar_tool.py    # test manuel calendrier
python assistant.py              # test vocal complet
```

Exemples de phrases vocales à essayer :
- "Envoie un email à karim@example.com, sujet réunion, dis-lui que je serai en retard"
- "Crée un événement demain à 10h intitulé réunion projet"
- "Quels sont mes prochains événements ?"

## 8. Limites connues (modèle `qwen2.5:3b`)

Le tool-calling avec un petit modèle comme `qwen2.5:3b` fonctionne mais
n'est pas parfait — il peut mal extraire une date/heure relative ("demain",
"dans une heure"). Pour de meilleurs résultats, sois explicite dans ta
demande vocale (dates et heures précises), ou passe temporairement sur un
modèle plus costaud (`LLM_MODEL=llama3.1:8b` par ex.) juste pour tester.
