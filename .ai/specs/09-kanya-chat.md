# 09 The chat, as Kanya's

## Why

The user asked for itos's chat to be the chat Canyas built for Kanya (`Canyas_agentic_harness/frontend`): its
sidebar, the right-hand drawer, the input bar, and the tools under each reply. Decided 2026-10-31: **identical to
Kanya** (Canyas tokens, fonts, light and dark themes, the orb as wizi's face) and **the same voice service** (OpenAI:
`gpt-4o-mini-tts` speaks replies, realtime transcription listens), with the key from the same Secrets Manager entry
(`OPENAI_API_KEY` in `dev/AppAlpha/secrets`, present).

## What

- **Look:** Canyas `tokens.css` and `base.css`, Archivo / IBM Plex fonts, a theme choice (auto, light, dark).
- **Left sidebar** (`AppLayout` + `Sidebar`): the itos name, New project, the project list (rename, delete), theme;
  folds to a rail of icons in a chat, resizable, a drawer on narrow screens; choices remembered on the device.
- **The chat** (`ChatPage`, after `ProductionChatPage`): header (title, stage, the drawer toggle with the to-do
  count); the conversation with wizi's orb beside each reply; the live thinking line; the approval card inline in the
  feed; the boxed composer (text growing with what is written, + on the left; voice buttons, Stop and Send on the
  right).
- **Right drawer** ("Brief and documents"): wizi's to-dos, the brief and decisions (map, questionnaire), the
  documents, package checks and downloads. Closed by default; beside the chat on wide screens, over it on narrow ones.
- **Reply tools** under each wizi reply: copy, good / bad (bad asks why; kept per project), read aloud, try again
  with guidance (latest reply), sources. A long reply shows its opening and a document card that opens the reader.
- **Reader pane** on the right: a long reply or a document, copy, download; resizable; Escape closes it.
- **Voice:** Dictate (words appear in the box) and Voice mode (each finished sentence is sent; replies are read
  aloud; talking over wizi stops its voice), through `WS /api/voice/listen` and `POST /api/voice/speak`.
- **Stop:** ends wizi's current turn (`POST /api/projects/{id}/stop`).

## Context

**Relevant files**

- Source: `Canyas_agentic_harness/frontend/src/{styles/tokens.css,styles/base.css,styles/app.css,styles/kanya.css,
  components/layout/*,components/chat/*,components/ThinkingOrb.tsx,components/KanyaFace.tsx,pages/kanya/Composer.tsx,
  pages/kanya/ThinkingLine.tsx,pages/kanya/TodoPanel.tsx}`; `backend/src/canyas_api/routers/voice.py`.
- itos: `frontend/src/App.tsx`, `components/*`, `styles.css`, `index.html`; `backend/app/main.py`, `store.py`,
  `secrets.py`.

**Decisions already made**

- Ported code keeps its behaviour and wording, with Kanya → wizi and Canyas → itos where a name shows. Canyas's own
  data (productions, spend, scene review, memory) is not ported.
- No new frontend dependencies: itos keeps its own Markdown renderer, routing by state, and fetch-based client.
- Ratings live in `app.db` (`reply_feedback`), keyed by the SHA-256 of the reply text, one per reply.
- The AssemblyAI voice note path stays in the backend but the composer uses Kanya's voice buttons.

## Constraints

**Must:** keep every existing feature reachable (approvals typed or clicked, questionnaires, package, questions back,
decision map, mermaid, history); keep the smoke scripts passing (updated to the new layout where they name it).
**Must not:** put a key in the browser or a log; send voice anywhere but the backend relay.

## Tasks

### T1: Canyas look and the sidebar shell
**Do:** Tokens, base styles, fonts, theme choice; `AppLayout` and `Sidebar` with projects; App uses them.
**Files:** `frontend/index.html`, `frontend/src/styles/*`, `frontend/src/components/layout/*`, `frontend/src/App.tsx`,
`frontend/src/theme.ts`
**Verify:** `npm run build`; the app renders in light and dark.
**Blocked by:** none
**Status:** done, 2026-10-31

### T2: The chat page and the right drawer
**Do:** `ChatPage` (header, conversation rows with the orb, thinking line, inline card, boxed composer with Stop),
the drawer (to-dos, brief and decisions, documents), the reader pane; Stop route.
**Files:** `frontend/src/components/chat/*`, `frontend/src/components/Chat.tsx`, `frontend/src/components/*Panel.tsx`,
`frontend/src/components/DocViewer.tsx`, `backend/app/main.py`, `backend/tests/test_history.py`
**Verify:** `npm run build`; `uv run pytest -q`; smoke scripts.
**Blocked by:** T1
**Status:** done, 2026-10-31

### T3: Reply tools and ratings
**Do:** Copy, good / bad with reasons, try again with guidance, sources, the long-reply document card; `reply_feedback`
table and `GET/POST/DELETE /api/projects/{id}/feedback`.
**Files:** `frontend/src/components/chat/*`, `backend/app/store.py`, `backend/app/main.py`, `backend/tests/test_feedback.py`
**Verify:** `uv run pytest -q tests/test_feedback.py`; `npm run build`
**Blocked by:** T2
**Status:** done, 2026-10-31

### T4: Voice: read aloud, dictate, voice mode
**Do:** `backend/app/voice.py` (speak: OpenAI streaming speech as 24 kHz PCM; listen: a websocket relaying PCM to an
OpenAI realtime transcription session), routes in `main.py`; `voice.ts` and `VoiceButtons` in the composer; read aloud
in the reply tools.
**Files:** `backend/app/voice.py`, `backend/app/main.py`, `backend/app/secrets.py`, `backend/pyproject.toml`,
`frontend/src/components/chat/voice.ts`, `frontend/src/components/chat/VoiceButtons.tsx`, `backend/tests/test_voice.py`
**Verify:** `uv run pytest -q tests/test_voice.py`; Manual: read aloud plays a reply; dictation fills the box.
**Blocked by:** T2
**Status:** done, 2026-10-31

### T5: Live check
**Do:** The whole chat in the running app, light and dark, wide and narrow; screenshots compared with Kanya's layout.
**Files:** this spec
**Verify:** Manual, recorded below.
**Blocked by:** T1-T4
**Status:** done, 2026-10-31

## Done

- [x] `uv run pytest -q` (184) and `npm run build` pass
- [x] Smoke scripts pass: all six updated to the new layout and voice (each run three times); `audio-capture.cjs` and
  `live-voice.cjs` removed with the AssemblyAI capture they tested
- [x] Live check recorded, 2026-10-31, real model and real OpenAI voice:
  - Start page, a real exchange, the thinking line (orb, word, clock, Stop), the reply tools, the drawer over the chat
    below 1500px, light and dark: no page errors.
  - Read aloud: `/api/voice/speak` 200 `audio/pcm`, the button switched to Stop. Dictation: a generated sentence played
    as a fake microphone came back in the box through the realtime relay, from Vite and through Docker's nginx.
  - Found on the way and fixed: Kanya turns every reply over 1,500 characters into a document card, which hid wizi's
    questions at the end of a round; a reply is now a document only when long with a heading, or over 6,000
    characters. WebSockets were not proxied (Vite `ws: true`; an upgraded nginx location for `/api/voice/listen`).
    The server's progress lines showed only in a tooltip; the live line shows them again.
