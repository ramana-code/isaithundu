from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess

import numpy as np


@dataclass
class AudioData:
    """Decoded audio data used by the rest of the application.

    Audio is stored as mono float32 samples in the range approximately
    [-1.0, 1.0].
    """

    samples: np.ndarray
    sample_rate: int
    duration: float
    source_path: Path


class AudioLoader:
    """Load and decode audio files.

    The loader deliberately knows nothing about YAML or application metadata.
    It receives an audio filename/path and returns AudioData.

    FFmpeg is used so MP3, M4A, and other formats supported by FFmpeg can
    be loaded without adding format-specific Python audio libraries.
    """

    SUPPORTED_SUFFIXES = {
        ".mp3",
        ".m4a",
        ".mp4",
        ".wav",
        ".flac",
        ".ogg",
        ".aac",
        ".opus",
    }

    def load(self, audio_path: str | Path) -> AudioData:
        """Decode an audio file and return AudioData.

        Relative paths are interpreted relative to the current working
        directory. The caller can resolve a path relative to the YAML file
        before calling this method.
        """
        path = Path(audio_path).expanduser()

        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported audio format '{path.suffix}'. "
                f"Supported formats: {', '.join(sorted(self.SUPPORTED_SUFFIXES))}"
            )

        sample_rate = self._get_sample_rate(path)
        samples = self._decode_to_mono_float32(path)

        duration = len(samples) / sample_rate if sample_rate else 0.0

        return AudioData(
            samples=samples,
            sample_rate=sample_rate,
            duration=duration,
            source_path=path.resolve(),
        )

    def _get_sample_rate(self, path: Path) -> int:
        """Read the source sample rate using ffprobe."""
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "json",
            str(path),
        ]

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffprobe was not found. Please install FFmpeg."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Could not inspect audio file '{path}': {exc.stderr.strip()}"
            ) from exc

        try:
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if not streams or not streams[0].get("sample_rate"):
                raise ValueError
            return int(streams[0]["sample_rate"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Could not determine sample rate for '{path}'."
            ) from exc

    def _decode_to_mono_float32(self, path: Path) -> np.ndarray:
        """Decode audio with FFmpeg as mono float32 PCM."""
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "pipe:1",
        ]

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffmpeg was not found. Please install FFmpeg."
            ) from exc
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Could not decode audio file '{path}': {error}"
            ) from exc

        samples = np.frombuffer(result.stdout, dtype=np.float32).copy()

        if samples.size == 0:
            raise RuntimeError(f"No audio samples were decoded from '{path}'.")

        return samples
