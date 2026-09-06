from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import numpy as np

from audio_loader import AudioData


@dataclass
class PitchTrack:
    """Time-aligned fundamental-frequency analysis results.

    frequencies_hz contains NaN for frames where no reliable fundamental
    frequency was detected. confidence contains the analyzer's confidence
    measure when one is available. voiced identifies frames classified as
    voiced by the analyzer.
    """

    times: np.ndarray
    frequencies_hz: np.ndarray
    confidence: np.ndarray
    voiced: np.ndarray

    def __post_init__(self) -> None:
        self.times = np.asarray(self.times, dtype=np.float64)
        self.frequencies_hz = np.asarray(
            self.frequencies_hz,
            dtype=np.float64,
        )
        self.confidence = np.asarray(
            self.confidence,
            dtype=np.float64,
        )
        self.voiced = np.asarray(
            self.voiced,
            dtype=bool,
        )

        if not (
            self.times.ndim == 1
            and self.frequencies_hz.ndim == 1
            and self.confidence.ndim == 1
            and self.voiced.ndim == 1
        ):
            raise ValueError(
                "PitchTrack arrays must all be one-dimensional."
            )

        length = len(self.times)

        if not (
            len(self.frequencies_hz) == length
            and len(self.confidence) == length
            and len(self.voiced) == length
        ):
            raise ValueError(
                "PitchTrack arrays must all have the same length."
            )

    @property
    def size(self) -> int:
        """Return the number of analyzed frames."""

        return len(self.times)

    def slice(
        self,
        start_time: float,
        end_time: float,
    ) -> PitchTrack:
        """Return the portion of the pitch track within a time interval."""

        if end_time < start_time:
            raise ValueError(
                "end_time must be greater than or equal to start_time."
            )

        mask = (
            (self.times >= float(start_time))
            & (self.times <= float(end_time))
        )

        return PitchTrack(
            times=self.times[mask],
            frequencies_hz=self.frequencies_hz[mask],
            confidence=self.confidence[mask],
            voiced=self.voiced[mask],
        )

    def summary(self) -> dict[str, float | int]:
        """Return basic information about the pitch track."""

        result: dict[str, float | int] = {
            "frames": self.size,
        }

        if self.size == 0:
            return result

        result["first_time"] = float(self.times[0])
        result["last_time"] = float(self.times[-1])

        if self.size > 1:
            result["frame_step"] = float(
                np.median(
                    np.diff(self.times)
                )
            )

        result["duration"] = float(
            self.times[-1] - self.times[0]
        )

        result["voiced_frames"] = int(
            np.count_nonzero(self.voiced)
        )

        result["voiced_percent"] = float(
            100.0 * np.mean(self.voiced)
        )

        return result

    def confidence_summary(
        self,
        thresholds: tuple[float, ...] = (
            0.1,
            0.2,
            0.3,
            0.5,
            0.7,
            0.9,
        ),
    ) -> dict[str, float | int | dict[float, int]]:
        """Return statistics describing pitch confidence."""

        if self.size == 0:
            return {
                "min": float("nan"),
                "max": float("nan"),
                "mean": float("nan"),
                "median": float("nan"),
                "above_threshold": {},
            }

        confidence = self.confidence

        result: dict[
            str,
            float | int | dict[float, int],
        ] = {
            "min": float(np.min(confidence)),
            "max": float(np.max(confidence)),
            "mean": float(np.mean(confidence)),
            "median": float(np.median(confidence)),
            "above_threshold": {},
        }

        above_threshold = result["above_threshold"]

        for threshold in thresholds:
            above_threshold[threshold] = int(
                np.count_nonzero(
                    self.voiced
                    & (confidence >= threshold)
                )
            )

        return result

    def sample_rows(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        count: int = 10,
    ) -> list[dict[str, float | bool]]:
        """Return representative pitch-track samples."""

        if self.size == 0 or count <= 0:
            return []

        mask = np.ones(
            self.size,
            dtype=bool,
        )

        if start_time is not None:
            mask &= self.times >= start_time

        if end_time is not None:
            mask &= self.times <= end_time

        indices = np.flatnonzero(mask)

        if len(indices) == 0:
            return []

        if len(indices) > count:
            positions = np.linspace(
                0,
                len(indices) - 1,
                count,
                dtype=int,
            )
            indices = indices[positions]

        rows = []

        for index in indices:
            frequency = self.frequencies_hz[index]

            rows.append(
                {
                    "time": float(
                        self.times[index]
                    ),
                    "frequency_hz": (
                        float(frequency)
                        if np.isfinite(frequency)
                        else float("nan")
                    ),
                    "confidence": float(
                        self.confidence[index]
                    ),
                    "voiced": bool(
                        self.voiced[index]
                    ),
                }
            )

        return rows

    def print_diagnostics(
        self,
        sample_count: int = 10,
    ) -> None:
        """Print a human-readable diagnostic summary."""

        summary = self.summary()
        confidence = self.confidence_summary()

        print()
        print("Pitch track")
        print("-----------")
        print(
            f"Frames          : "
            f"{summary['frames']:,}"
        )

        if "first_time" in summary:
            print(
                f"First time      : "
                f"{summary['first_time']:.6f} s"
            )

            print(
                f"Last time       : "
                f"{summary['last_time']:.6f} s"
            )

        if "frame_step" in summary:
            print(
                f"Frame step      : "
                f"{summary['frame_step']:.6f} s"
            )

        if "duration" in summary:
            print(
                f"Track duration  : "
                f"{summary['duration']:.6f} s"
            )

        print(
            f"Voiced frames   : "
            f"{summary['voiced_frames']:,} "
            f"({summary['voiced_percent']:.1f}%)"
        )

        print()
        print("Confidence")
        print("----------")
        print(
            f"Min             : "
            f"{confidence['min']:.3f}"
        )
        print(
            f"Max             : "
            f"{confidence['max']:.3f}"
        )
        print(
            f"Mean            : "
            f"{confidence['mean']:.3f}"
        )
        print(
            f"Median          : "
            f"{confidence['median']:.3f}"
        )

        print()
        print("Confidence thresholds")

        above_threshold = confidence["above_threshold"]

        for threshold, frame_count in (
            above_threshold.items()
        ):
            percent = (
                100.0
                * frame_count
                / self.size
            )

            print(
                f"  >= {threshold:.1f}: "
                f"{frame_count:,} frames "
                f"({percent:.1f}%)"
            )

        print()
        print("Sample pitch rows")
        print("-----------------")
        print(
            "       Time (s)    Frequency (Hz) "
            " Confidence   Voiced"
        )

        for row in self.sample_rows(
            count=sample_count
        ):
            frequency = row["frequency_hz"]

            if np.isfinite(frequency):
                frequency_text = (
                    f"{frequency:15.3f}"
                )
            else:
                frequency_text = (
                    f"{'---':>15}"
                )

            print(
                f"{row['time']:15.6f} "
                f"{frequency_text} "
                f"{row['confidence']:11.3f} "
                f"{str(row['voiced']):>8}"
            )

class PitchAnalyzer(ABC):
    """Interface for one-time offline pitch analysis."""

    @abstractmethod
    def analyze(self, audio: AudioData) -> PitchTrack:
        """Analyze the complete audio and return a pitch track."""


class EssentiaPitchAnalyzer(PitchAnalyzer):
    """Predominant-melody pitch analyzer using Essentia MELODIA.

    This is intended for polyphonic recordings containing a predominant
    melodic source, such as a singer accompanied by instruments.
    """

    TARGET_SAMPLE_RATE = 44100
    FRAME_SIZE = 2048
    HOP_SIZE = 128

    def __init__(
        self,
        min_frequency: float = 60.0,
        max_frequency: float = 2000.0,
        voicing_tolerance: float = 0.2,
    ) -> None:
        self.min_frequency = float(min_frequency)
        self.max_frequency = float(max_frequency)
        self.voicing_tolerance = float(voicing_tolerance)

        if self.min_frequency <= 0:
            raise ValueError("min_frequency must be positive.")

        if self.max_frequency <= self.min_frequency:
            raise ValueError(
                "max_frequency must be greater than min_frequency."
            )

    def analyze(self, audio: AudioData) -> PitchTrack:
        try:
            import essentia.standard as es
        except ImportError as exc:
            raise RuntimeError(
                "Essentia is required for EssentiaPitchAnalyzer. "
                "Install it with 'pip install essentia'."
            ) from exc

        samples = np.asarray(audio.samples, dtype=np.float32)

        if samples.size == 0:
            raise ValueError("Cannot analyze empty audio.")

        processed = samples

        if audio.sample_rate != self.TARGET_SAMPLE_RATE:
            resampler = es.Resample(
                inputSampleRate=float(audio.sample_rate),
                outputSampleRate=float(self.TARGET_SAMPLE_RATE),
                quality=0,
            )
            processed = np.asarray(
                resampler(processed),
                dtype=np.float32,
            )

        # Essentia recommends equal-loudness preprocessing for this
        # predominant-melody algorithm.
        equal_loudness = es.EqualLoudness(
            sampleRate=self.TARGET_SAMPLE_RATE,
        )
        processed = np.asarray(
            equal_loudness(processed),
            dtype=np.float32,
        )

        extractor = es.PredominantPitchMelodia(
            frameSize=self.FRAME_SIZE,
            hopSize=self.HOP_SIZE,
            minFrequency=self.min_frequency,
            maxFrequency=self.max_frequency,
            voicingTolerance=self.voicing_tolerance,
            guessUnvoiced=False,
        )

        pitch_values, pitch_confidence = extractor(processed)

        frequencies_hz = np.asarray(
            pitch_values,
            dtype=np.float64,
        )
        confidence = np.asarray(
            pitch_confidence,
            dtype=np.float64,
        )

        # Essentia uses zero pitch for unvoiced frames by default. Convert
        # those values to NaN so a plotting library naturally leaves gaps.
        voiced = frequencies_hz > 0.0
        frequencies_hz = frequencies_hz.copy()
        frequencies_hz[~voiced] = np.nan

        times = (
            np.arange(len(frequencies_hz), dtype=np.float64)
            * self.HOP_SIZE
            / self.TARGET_SAMPLE_RATE
        )

        return PitchTrack(
            times=times,
            frequencies_hz=frequencies_hz,
            confidence=confidence,
            voiced=voiced,
        )


class LibrosaPitchAnalyzer(PitchAnalyzer):
    """Offline F0 analyzer using librosa's probabilistic YIN (pYIN)."""

    def __init__(
        self,
        min_frequency: float = 60.0,
        max_frequency: float = 2000.0,
        frame_length: int = 2048,
        hop_length: int = 256,
    ) -> None:
        self.min_frequency = float(min_frequency)
        self.max_frequency = float(max_frequency)
        self.frame_length = int(frame_length)
        self.hop_length = int(hop_length)

        if self.min_frequency <= 0:
            raise ValueError("min_frequency must be positive.")

        if self.max_frequency <= self.min_frequency:
            raise ValueError(
                "max_frequency must be greater than min_frequency."
            )

        if self.frame_length <= 0:
            raise ValueError("frame_length must be positive.")

        if self.hop_length <= 0:
            raise ValueError("hop_length must be positive.")

    def analyze(self, audio: AudioData) -> PitchTrack:
        try:
            import librosa
        except ImportError as exc:
            raise RuntimeError(
                "librosa is required for LibrosaPitchAnalyzer. "
                "Install it with 'pip install librosa'."
            ) from exc

        samples = np.asarray(audio.samples, dtype=np.float32)

        if samples.size == 0:
            raise ValueError("Cannot analyze empty audio.")

        f0, voiced_flag, voiced_prob = librosa.pyin(
            samples,
            sr=audio.sample_rate,
            fmin=self.min_frequency,
            fmax=min(
                self.max_frequency,
                audio.sample_rate / 2.0,
            ),
            frame_length=self.frame_length,
            hop_length=self.hop_length,
            center=True,
            fill_na=np.nan,
        )

        times = librosa.times_like(
            f0,
            sr=audio.sample_rate,
            hop_length=self.hop_length,
        )

        return PitchTrack(
            times=times,
            frequencies_hz=np.asarray(f0, dtype=np.float64),
            confidence=np.asarray(
                voiced_prob,
                dtype=np.float64,
            ),
            voiced=np.asarray(
                voiced_flag,
                dtype=bool,
            ),
        )


def create_pitch_analyzer(
    backend: Literal["essentia", "librosa"] = "essentia",
    **kwargs,
) -> PitchAnalyzer:
    """Create a pitch analyzer using the requested backend."""

    if backend == "essentia":
        return EssentiaPitchAnalyzer(**kwargs)

    if backend == "librosa":
        return LibrosaPitchAnalyzer(**kwargs)

    raise ValueError(
        f"Unknown pitch analyzer backend: {backend!r}"
    )
