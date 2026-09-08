from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class PlaybackTransform:
    """Playback transformation requested by the user.

    pitch_semitones and pitch_cents are independent controls. They are
    combined into one fractional semitone value for Rubber Band.

    speed is a playback-speed multiplier:
        1.00 = normal speed
        0.80 = slower
        1.20 = faster
    """

    pitch_semitones: int = 0
    pitch_cents: int = 0
    speed: float = 1.0

    @property
    def total_pitch_semitones(self) -> float:
        """Return the complete pitch shift in semitones."""

        return (
            float(self.pitch_semitones)
            + float(self.pitch_cents) / 100.0
        )


class PlaybackProcessor:
    """Generate an offline, high-quality transformed playback signal."""

    RUBBERBAND_EXECUTABLE = "rubberband"
    MIN_SPEED = 0.70
    MAX_SPEED = 1.30
    MIN_CENTS = -50
    MAX_CENTS = 50
    MIN_SEMITONES = -12
    MAX_SEMITONES = 12

    def __init__(
        self,
        executable: str = RUBBERBAND_EXECUTABLE,
    ) -> None:
        self.executable = executable
        self._validate_executable()

    def process(
        self,
        samples: np.ndarray,
        sample_rate: int,
        transform: PlaybackTransform,
    ) -> np.ndarray:
        """Return transformed mono float32 audio samples.

        Pitch and speed are applied together in one Rubber Band offline
        operation. The input array is never modified.
        """

        audio = np.asarray(
            samples,
            dtype=np.float32,
        )

        if audio.ndim != 1:
            raise ValueError(
                "PlaybackProcessor expects mono audio samples."
            )

        if audio.size == 0:
            return audio.copy()

        if sample_rate <= 0:
            raise ValueError(
                "sample_rate must be positive."
            )

        self._validate_transform(transform)

        # No processing is necessary at the default settings.
        if (
            np.isclose(transform.total_pitch_semitones, 0.0)
            and np.isclose(transform.speed, 1.0)
        ):
            return audio.copy()

        with tempfile.TemporaryDirectory(
            prefix="isaithundu_rubberband_"
        ) as directory:
            directory_path = Path(directory)
            input_path = directory_path / "input.wav"
            output_path = directory_path / "output.wav"

            # Use float32 WAV so we do not unnecessarily quantize the
            # original in the Python-to-Rubber-Band handoff.
            sf.write(
                input_path,
                audio,
                sample_rate,
                subtype="FLOAT",
            )

            command = self._build_command(
                input_path=input_path,
                output_path=output_path,
                transform=transform,
            )

            try:
                result = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Rubber Band executable was not found. "
                    "Install the rubberband-cli package and make sure "
                    "the 'rubberband' command is on PATH."
                ) from exc
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip()
                stdout = exc.stdout.strip()
                details = stderr or stdout or "unknown error"
                raise RuntimeError(
                    "Rubber Band processing failed: "
                    f"{details}"
                ) from exc

            # Rubber Band normally writes this file on success. Check
            # explicitly so a strange tool failure cannot turn into a
            # confusing soundfile exception.
            if not output_path.is_file():
                raise RuntimeError(
                    "Rubber Band completed without producing an output file."
                )

            processed, output_rate = sf.read(
                output_path,
                dtype="float32",
                always_2d=False,
            )

            if int(output_rate) != int(sample_rate):
                raise RuntimeError(
                    "Rubber Band changed the sample rate from "
                    f"{sample_rate} Hz to {output_rate} Hz."
                )

            processed = np.asarray(
                processed,
                dtype=np.float32,
            )

            if processed.ndim != 1:
                raise RuntimeError(
                    "Rubber Band produced non-mono output."
                )

            return processed

    def _build_command(
        self,
        input_path: Path,
        output_path: Path,
        transform: PlaybackTransform,
    ) -> list[str]:
        """Build one combined offline Rubber Band command."""

        return [
            self.executable,
            "--quiet",
            "--fine",
            "--formant",
            "--tempo",
            f"{transform.speed:.6f}",
            "--pitch",
            f"{transform.total_pitch_semitones:.6f}",
            str(input_path),
            str(output_path),
        ]

    def _validate_executable(self) -> None:
        """Ensure the configured Rubber Band executable exists."""

        if shutil.which(self.executable) is None:
            raise RuntimeError(
                f"Rubber Band executable '{self.executable}' was not found. "
                "Install rubberband-cli and make sure it is on PATH."
            )

    def _validate_transform(
        self,
        transform: PlaybackTransform,
    ) -> None:
        """Validate user-facing playback transformation limits."""

        if not (
            self.MIN_SEMITONES
            <= transform.pitch_semitones
            <= self.MAX_SEMITONES
        ):
            raise ValueError(
                "pitch_semitones must be in the range "
                f"{self.MIN_SEMITONES}..{self.MAX_SEMITONES}."
            )

        if not (
            self.MIN_CENTS
            <= transform.pitch_cents
            <= self.MAX_CENTS
        ):
            raise ValueError(
                "pitch_cents must be in the range "
                f"{self.MIN_CENTS}..{self.MAX_CENTS}."
            )

        if not (
            np.isfinite(transform.speed)
            and self.MIN_SPEED
            <= transform.speed
            <= self.MAX_SPEED
        ):
            raise ValueError(
                "speed must be in the range "
                f"{self.MIN_SPEED:.2f}..{self.MAX_SPEED:.2f}."
            )
