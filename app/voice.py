"""
Speech layer. Both engines are loaded lazily so the text API works without them.
  STT: faster-whisper (runs locally, no API key)
  TTS: gTTS (needs internet) -> MP3 bytes
Swap either function for Deepgram / Azure / ElevenLabs / Piper etc. if you prefer.
"""
import io

from . import config

_whisper = None


def speech_to_text(audio_bytes: bytes) -> str:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _info = _whisper.transcribe(
        io.BytesIO(audio_bytes), language=config.STT_LANGUAGE, vad_filter=True, beam_size=5
    )
    return " ".join(s.text.strip() for s in segments).strip()


def text_to_speech(text: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang=config.TTS_LANG, tld=config.TTS_TLD).write_to_fp(buf)
    return buf.getvalue()
