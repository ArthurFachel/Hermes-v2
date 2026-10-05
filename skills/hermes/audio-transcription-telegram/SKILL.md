---
name: audio-transcription-telegram
description: Configure, troubleshoot, or explain automatic audio/voice transcription for the Hermes gateway on Telegram (and other messaging platforms). Use when a user wants incoming Telegram voice notes auto-transcribed, wants to pick/switch the STT provider (local faster-whisper, Groq, OpenAI, Mistral, xAI, ElevenLabs, DeepInfra), wants to suppress the 🎙️ transcript echo, wants to disable STT and hand the raw audio path to the agent, or reports voice messages not being transcribed.
---

# Audio Transcription on Telegram

Hermes auto-transcribes inbound Telegram voice notes and injects the text into
the conversation as if the user had typed it. This skill covers the config
knobs, provider choices, and failure modes. Config lives under `stt:` in
`~/.hermes/config.yaml`; the gateway toggle lives in `gateway.stt_enabled`.

## When to use
- "How do I turn on voice transcription for my Telegram bot?"
- "Voice notes aren't being transcribed" / "the bot just says the message
  couldn't be transcribed".
- "Which STT provider should I use / how do I switch providers?"
- "Stop echoing the 🎙️ transcript back to me."
- "Send the raw audio file to the agent instead of transcribing."

## How the pipeline works (so you can debug it)
1. Telegram adapter downloads the voice/audio attachment to
   `~/.hermes/cache/audio/<hash>.ogg` (voice notes arrive as OGG/Opus).
2. `gateway/run.py::_enrich_message_with_transcription()` calls
   `tools.transcription_tools.transcribe_audio(path)`.
3. If STT is enabled and a provider resolves, the transcript is prepended to the
   user turn as a quoted line (`"...transcript..."`), and — when echo is on — a
   `🎙️ "..."` message is sent back to the chat.
4. If transcription fails, the LLM only sees the neutral marker
   `[voice message could not be transcribed]`; the real cause is logged, never
   shown to the model (this is deliberate — see Pitfalls).

`transcribe_audio` returns `{"success": bool, "transcript": str, "provider":
str, "error": str?}`. Smartphone voice notes are `.ogg`; `SUPPORTED_FORMATS`
also covers mp3, m4a, wav, webm, aac, flac. Hard cap: 25 MB per file.

## Provider resolution order
Set `stt.provider` explicitly to pin one (no silent cloud fallback). When unset,
auto-detect runs: local (faster-whisper) > local_command > groq > openai >
mistral > xai > elevenlabs > deepinfra.

Built-in providers:
- `local` — faster-whisper, free, no API key. Auto-downloads model on first use
  (`base` ≈ 150 MB). Models: tiny, base, small, medium, large-v3.
- `local_command` — shell out to a whisper CLI; also the
  `HERMES_LOCAL_STT_COMMAND` escape hatch.
- `groq` — Groq Whisper API, free tier; needs `GROQ_API_KEY`.
- `openai` — Whisper API; needs `VOICE_TOOLS_OPENAI_KEY` (or `OPENAI_API_KEY`).
- `mistral` — Voxtral Transcribe; needs `MISTRAL_API_KEY`.
- `xai` — Grok STT, diarization + 21 languages; xAI OAuth or `XAI_API_KEY`.
- `elevenlabs` — Scribe; needs `ELEVENLABS_API_KEY`.
- `deepinfra` — OpenAI-compatible; needs `DEEPINFRA_API_KEY`.

Any STT CLI/curl pipeline can be added with zero Python via
`stt.providers.<name>: type: command` (placeholders `{input_path}`,
`{output_path}`, `{output_dir}`, `{format}`, `{language}`, `{model}`).

## Configure it
Preferred: `hermes tools` → Speech-to-Text section (writes the same keys).

Or edit `~/.hermes/config.yaml` directly:
```yaml
stt:
  enabled: true          # master switch (gateway also reads gateway.stt_enabled)
  echo_transcripts: true # 🎙️ echo of the raw transcript back to chat
  provider: local        # local | groq | openai | mistral | xai | elevenlabs | deepinfra
  local:
    model: base          # tiny|base|small|medium|large-v3
    language: ""         # "" = auto-detect; else "pt", "en", ...
  openai:
    model: whisper-1     # whisper-1 | gpt-4o-mini-transcribe | gpt-4o-transcribe
```
Keys go in the profile's `.env` (e.g. `GROQ_API_KEY=...`,
`VOICE_TOOLS_OPENAI_KEY=...`), not in config.yaml, for the cloud providers.

Apply changes with `hermes gateway restart`. If you change the active
dependency environment (e.g. install faster-whisper), restart Hermes too.

## Common tasks
- Suppress the 🎙️ echo while keeping transcription:
  `stt.echo_transcripts: false` (equivalently top-level
  `stt_echo_transcripts: false`).
- Disable STT, hand raw audio to the agent: `stt.enabled: false`. The gateway
  still downloads the clip and passes a marker
  `[The user sent a voice message: /home/<user>/.hermes/cache/audio/<hash>.ogg]`
  so tools/skills can read the path (custom diarization, archiving, etc.).
- Force Portuguese: `stt.local.language: pt` (or the provider's language key).
- Best accuracy for long recordings: use `xai` (diarization) or a cloud
  provider; local `large-v3` is heavier but offline.
- Files >20 MB (long memos): the public Telegram Bot API caps `getFile` at
  20 MB. Run a local `telegram-bot-api` daemon and set a custom `base_url` to
  lift the ceiling to 2 GB (Hermes auto-raises its internal cap).
- Large outgoing TTS voice bubbles need **ffmpeg** (Edge TTS emits MP3; Telegram
  voice bubbles require OGG/Opus). OpenAI/ElevenLabs produce Opus natively.

## Troubleshooting
- "could not be transcribed" in chat → the real error is in the gateway log.
  Check it, then verify provider credentials and that a provider resolves:
  run a quick check with the project venv python:
  `venv/bin/python -c "from tools.transcription_tools import transcribe_audio; print(transcribe_audio('/path/to.wav'))"`.
- Silent no-op / "No STT provider available" → no local engine installed and no
  cloud key set. Either `hermes tools` to install faster-whisper, or set a
  provider key.
- `stt.provider: local` but fails → faster-whisper not installed and lazy
  install disabled (`security.allow_lazy_installs`). Install it via
  `hermes tools`, or switch provider.
- Wrong language output → set the provider's language key; empty = auto-detect.
- Echo loop in a topic/thread → set `echo_transcripts: false`; note the echo is
  also deduplicated per event, so a duplicated echo usually means two events.

## Pitfalls
- Do NOT tell the model (via prompt edits or config) about STT setup state from
  inside the conversation. The gateway deliberately hides STT failure causes
  from the LLM because those phrases get persisted and poison later turns —
  keep diagnosis in logs only.
- `stt.enabled` (yaml `stt.enabled`) and `gateway.stt_enabled` are bridged;
  setting one is normally enough, but if transcription won't turn on, check both.
- The echo is sent by the gateway, not the model — suppress it with config, not
  by asking the model to stop.
- `local_command` and plugin provider internals are advanced surfaces; prefer
  the built-in provider names unless the user explicitly needs a custom engine.
- version-sensitive: provider list and config layout can gain entries over time
  (e.g. deepinfra). Confirm the exact key with `hermes tools` / the docs before
  asserting it exists.
