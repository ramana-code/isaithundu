from __future__ import annotations

from pathlib import Path

import numpy as np
import librosa

from audio_loader import AudioLoader
from metadata import MetadataParser
from pitch_analyzer import EssentiaPitchAnalyzer
from pitch_mapper import (
    DEFAULT_RATIOS,
    PitchMapper,
    PitchSystem,
)


# -------------------------------------------------------------------------
# Development test settings
# -------------------------------------------------------------------------

YAML_PATH = Path("mohananga.yaml")

# Replace these three values with the values for your current test track.
SRUTHI = "G3"
SRUTHI_CENTS = -20.0
MELA = 1


def calculate_sa_frequency(
    sruthi: str,
    cents: float,
) -> float:
    """Convert a Western pitch + cents correction to the Sa frequency."""

    base_frequency = float(
        librosa.note_to_hz(sruthi)
    )

    return base_frequency * (
        2.0 ** (cents / 1200.0)
    )


def print_pitch_system(
    pitch_system: PitchSystem,
) -> None:
    """Print the active notes and their reference frequencies."""

    print()
    print("Pitch system")
    print("------------")
    print(
        f"Sa frequency : "
        f"{pitch_system.sa_frequency_hz:.6f} Hz"
    )

    print()
    print(
        "Pos  Ratio       Frequency (Hz)    "
        "Interval (cents)   Svara"
    )

    for position, label in pitch_system.active_notes.items():
        frequency = pitch_system.frequency_for_position(
            position
        )
        cents = pitch_system.cents_for_position(
            position
        )

        ratio = pitch_system.ratios[position]

        print(
            f"{position:3d}  "
            f"{ratio:>8.5f}    "
            f"{frequency:14.6f}    "
            f"{cents:9.3f}       "
            f"{label}"
        )


def print_mapped_samples(
    mapped_track,
    sample_count: int = 20,
) -> None:
    """Print a representative set of mapped pitch samples."""

    valid = np.flatnonzero(
        np.isfinite(
            mapped_track.frequencies_hz
        )
    )

    if len(valid) == 0:
        print()
        print("No valid pitch samples were mapped.")
        return

    if len(valid) > sample_count:
        positions = np.linspace(
            0,
            len(valid) - 1,
            sample_count,
            dtype=int,
        )
        valid = valid[positions]

    print()
    print("Mapped pitch samples")
    print("--------------------")
    print(
        "       Time (s)    Frequency (Hz) "
        "  Cents from Sa   Position   Octave   Svara"
    )

    for index in valid:
        print(
            f"{mapped_track.times[index]:15.6f} "
            f"{mapped_track.frequencies_hz[index]:15.3f} "
            f"{mapped_track.cents_from_sa[index]:15.3f} "
            f"{mapped_track.nearest_positions[index]:10d} "
            f"{mapped_track.nearest_octaves[index]:8d} "
            f"{str(mapped_track.svara_names[index]):>8}"
        )


def print_pitch_ranges(
    mapped_track,
) -> None:
    """Print basic ranges from the mapped track."""

    valid = (
        np.isfinite(
            mapped_track.frequencies_hz
        )
    )

    if not np.any(valid):
        return

    frequencies = mapped_track.frequencies_hz[valid]
    cents = mapped_track.cents_from_sa[valid]

    print()
    print("Mapped ranges")
    print("-------------")
    print(
        f"Frequency range : "
        f"{np.min(frequencies):.3f} - "
        f"{np.max(frequencies):.3f} Hz"
    )
    print(
        f"Cents range     : "
        f"{np.min(cents):.3f} - "
        f"{np.max(cents):.3f}"
    )

def print_reference_lines(
    pitch_system: PitchSystem,
) -> None:
    """Print reference notes for three octaves around Sa."""

    print()
    print("Reference lines")
    print("----------------")
    print(
        "  Cents from Sa    Frequency (Hz)    "
        "Octave    Svara"
    )

    notes = pitch_system.reference_notes(
        min_octave=-1,
        max_octave=1,
    )

    for cents, position, label, octave in notes:
        frequency = pitch_system.frequency_for_position(
            position,
            octave,
        )

        print(
            f"{cents:16.3f} "
            f"{frequency:17.3f} "
            f"{octave:8d} "
            f"{label:>8}"
        )

def main() -> None:
    print("Loading metadata...")
    metadata = MetadataParser().load(
        str(YAML_PATH)
    )

    audio_path = (
        YAML_PATH.parent
        / metadata.audio_filename
    )

    print(
        f"Loading audio: {audio_path}"
    )

    audio = AudioLoader().load(
        audio_path
    )

    print(
        f"Audio duration: "
        f"{audio.duration:.3f} seconds"
    )

    print()
    print("Analyzing pitch...")
    analyzer = EssentiaPitchAnalyzer()
    pitch_track = analyzer.analyze(
        audio
    )

    print(
        f"Pitch frames: "
        f"{pitch_track.size:,}"
    )

    sa_frequency_hz = calculate_sa_frequency(
        SRUTHI,
        SRUTHI_CENTS,
    )

    pitch_system = PitchSystem.from_melakarta(
        sa_frequency_hz=sa_frequency_hz,
        mela=MELA,
        ratios=DEFAULT_RATIOS,
    )

    print_pitch_system(
        pitch_system
    )

    print_reference_lines(
        pitch_system
    )

    mapper = PitchMapper(
        pitch_system
    )

    mapped_track = mapper.map_track(
        pitch_track
    )

    print_pitch_ranges(
        mapped_track
    )

    print_mapped_samples(
        mapped_track,
        sample_count=20,
    )

    print()
    print(
        f"Mapped frames: "
        f"{mapped_track.size:,}"
    )


if __name__ == "__main__":
    main()
