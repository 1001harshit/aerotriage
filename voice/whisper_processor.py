"""
Local Whisper v3 transcription for voice triage. Offline-only; no external APIs.
"""
import os
import tempfile
from typing import Union

# Lazy load to avoid import cost when voice not used
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path_or_bytes: Union[str, bytes]) -> str:
    """
    Transcribe audio file path or bytes to text. Uses Whisper large-v3 locally.
    """
    model = _get_model()
    if isinstance(audio_path_or_bytes, bytes):
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_path_or_bytes)
            path = f.name
        try:
            segments, _ = model.transcribe(path, beam_size=5, language="en")
            text = " ".join(s.text for s in segments if s.text).strip()
            return text or ""
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    else:
        segments, _ = model.transcribe(audio_path_or_bytes, beam_size=5, language="en")
        text = " ".join(s.text for s in segments if s.text).strip()
        return text or ""
