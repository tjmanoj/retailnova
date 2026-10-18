"""Voice notes: inline audio -> Gemini transcription (+ language), contracts §9.2."""
from __future__ import annotations

import base64
import struct
import time
from typing import Optional

from . import config
from .db import log
from .limits import ApiError

MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
AUDIO_MIMES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav")

TRANSCRIBE_PROMPT = (
    "Transcribe this shopper's voice note exactly, in its original language and script "
    "(Hinglish may be written in Roman script). Do not translate or add anything. "
    "language = ISO code of the speech (en, hi, ta, te, kn, ml, bn, mr, gu, pa)."
)
_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "language": {"type": "string"}},
    "required": ["text", "language"],
}


def decode_audio(audio_b64: Optional[str], mime: Optional[str]) -> Optional[bytes]:
    """Validate size (and duration for WAV); raises 413 / 400 like the other inputs."""
    if not audio_b64:
        return None
    s = audio_b64.split(",", 1)[1] if audio_b64.startswith("data:") and "," in audio_b64 else audio_b64
    if len(s) * 3 // 4 > MAX_AUDIO_BYTES + 16:
        raise ApiError(413, "audio_too_large", "That voice note is too long. Please keep it under 60 seconds.")
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception:
        raise ApiError(400, "bad_audio", "We couldn't read that voice note. Please try recording again.")
    if len(raw) > MAX_AUDIO_BYTES:
        raise ApiError(413, "audio_too_large", "That voice note is too long. Please keep it under 60 seconds.")
    if (mime or "") == "audio/wav" and raw[:4] == b"RIFF" and len(raw) > 44:
        try:  # bytes per second from the fmt chunk
            byte_rate = struct.unpack("<I", raw[28:32])[0]
            if byte_rate and (len(raw) - 44) / byte_rate > MAX_AUDIO_SECONDS + 1:
                raise ApiError(413, "audio_too_long", "That voice note is too long. Please keep it under 60 seconds.")
        except struct.error:
            pass
    return raw


async def transcribe(audio: bytes, mime: Optional[str]) -> dict:
    """Returns {"text", "language", "latency_ms", "model"}. Raises on failure."""
    from google.genai import types

    from .llm import generate_json

    t0 = time.monotonic()
    parts = [types.Part.from_bytes(data=audio, mime_type=mime or "audio/webm"), TRANSCRIBE_PROMPT]
    res, model = await generate_json(parts, _SCHEMA, model=config.MODEL_AGENT, timeout=8, temperature=0.0,
                                     hedge_after=3.0)
    text = ((res or {}).get("text") or "").strip()
    lang = ((res or {}).get("language") or "en").strip().lower()[:5] or "en"
    ms = int((time.monotonic() - t0) * 1000)
    log("INFO", "voice transcribed", latency_ms=ms, model=model, language=lang, chars=len(text))
    return {"text": text, "language": lang, "latency_ms": ms, "model": model}
