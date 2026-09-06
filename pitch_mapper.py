from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from pitch_analyzer import PitchTrack


# Twelve pitch positions within one octave, expressed as frequency ratios
# relative to Sa.  Position 12 is the octave (2:1), rather than an
# additional chromatic position.
DEFAULT_RATIOS = (
    1.0,
    16 / 15,
    9 / 8,
    6 / 5,
    5 / 4,
    4 / 3,
    45 / 32,
    3 / 2,
    8 / 5,
    27 / 16,
    9 / 5,
    15 / 8,
)


@dataclass(frozen=True)
class PitchSystem:
    """Define the musical pitch system used to interpret a PitchTrack.

    active_notes maps one or more of the twelve pitch positions in an octave
    to their display labels.  The number of active notes is not assumed to be
    seven; a raga may contain any subset of the twelve positions.

    All frequencies are derived from sa_frequency_hz and the supplied ratios.
    """

    sa_frequency_hz: float
    ratios: Sequence[float]
    active_notes: Mapping[int, str]

    def __post_init__(self) -> None:
        sa = float(self.sa_frequency_hz)

        if not np.isfinite(sa) or sa <= 0.0:
            raise ValueError(
                "sa_frequency_hz must be a finite positive number."
            )

        ratios = tuple(float(ratio) for ratio in self.ratios)

        if len(ratios) != 12:
            raise ValueError(
                "PitchSystem requires exactly 12 ratios."
            )

        if any(
            not np.isfinite(ratio) or ratio <= 0.0
            for ratio in ratios
        ):
            raise ValueError(
                "All pitch ratios must be finite and positive."
            )

        if not np.isclose(ratios[0], 1.0):
            raise ValueError(
                "The first pitch ratio must be 1.0."
            )

        notes = {
            int(position): str(label)
            for position, label in self.active_notes.items()
        }

        if not notes:
            raise ValueError(
                "PitchSystem must contain at least one active note."
            )

        if any(
            position < 0 or position >= 12
            for position in notes
        ):
            raise ValueError(
                "Active note positions must be in the range 0..11."
            )

        if any(
            not label
            for label in notes.values()
        ):
            raise ValueError(
                "Active note labels must not be empty."
            )

        object.__setattr__(
            self,
            "sa_frequency_hz",
            sa,
        )
        object.__setattr__(
            self,
            "ratios",
            ratios,
        )
        object.__setattr__(
            self,
            "active_notes",
            notes,
        )

    @classmethod
    def from_melakarta(
        cls,
        sa_frequency_hz: float,
        mela: int,
        ratios: Sequence[float] = DEFAULT_RATIOS,
    ) -> PitchSystem:
        """Build a PitchSystem from a librosa melakarta definition."""

        try:
            import librosa
        except ImportError as exc:
            raise RuntimeError(
                "librosa is required to create a melakarta PitchSystem."
            ) from exc

        degrees = librosa.mela_to_degrees(mela)
        svaras = librosa.mela_to_svara(
            mela,
            abbr=False,
            unicode=False,
        )

        active_notes = {
            int(position): svaras[position]
            for position in degrees
        }

        return cls(
            sa_frequency_hz=sa_frequency_hz,
            ratios=ratios,
            active_notes=active_notes,
        )

    @property
    def octave_ratio(self) -> float:
        """Return the frequency ratio for the octave."""

        return 2.0

    def frequency_for_position(
        self,
        position: int,
        octave: int = 0,
    ) -> float:
        """Return the reference frequency for a pitch position."""

        if not 0 <= position < 12:
            raise ValueError(
                "Pitch position must be in the range 0..11."
            )

        return (
            self.sa_frequency_hz
            * float(self.ratios[position])
            * self.octave_ratio ** octave
        )

    def cents_for_position(
        self,
        position: int,
        octave: int = 0,
    ) -> float:
        """Return the position's interval from Sa in cents."""

        return (
            1200.0
            * np.log2(
                self.frequency_for_position(
                    position,
                    octave,
                )
                / self.sa_frequency_hz
            )
        )

    def reference_notes(
        self,
        min_octave: int = -1,
        max_octave: int = 1,
    ) -> list[tuple[float, int, str, int]]:
        """Return reference notes suitable for plotting.

        Each tuple is:
            (cents_from_sa, position, label, octave)
        """

        notes = []

        for octave in range(
            int(min_octave),
            int(max_octave) + 1,
        ):
            for position, label in self.active_notes.items():
                cents = self.cents_for_position(
                    position,
                    octave,
                )

                notes.append(
                    (
                        cents,
                        position,
                        label,
                        octave,
                    )
                )

        notes.sort(
            key=lambda item: item[0]
        )

        return notes


@dataclass
class MappedPitchTrack:
    """PitchTrack data mapped into a raga/svara pitch coordinate system."""

    times: np.ndarray
    frequencies_hz: np.ndarray
    confidence: np.ndarray
    voiced: np.ndarray
    cents_from_sa: np.ndarray
    nearest_positions: np.ndarray
    nearest_octaves: np.ndarray
    svara_names: np.ndarray

    def __post_init__(self) -> None:
        self.times = np.asarray(
            self.times,
            dtype=np.float64,
        )
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
        self.cents_from_sa = np.asarray(
            self.cents_from_sa,
            dtype=np.float64,
        )
        self.nearest_positions = np.asarray(
            self.nearest_positions,
            dtype=np.int16,
        )
        self.nearest_octaves = np.asarray(
            self.nearest_octaves,
            dtype=np.int16,
        )
        self.svara_names = np.asarray(
            self.svara_names,
            dtype=object,
        )

        arrays = (
            self.frequencies_hz,
            self.confidence,
            self.voiced,
            self.cents_from_sa,
            self.nearest_positions,
            self.nearest_octaves,
            self.svara_names,
        )

        if any(
            len(array) != len(self.times)
            for array in arrays
        ):
            raise ValueError(
                "All MappedPitchTrack arrays must have the same length."
            )

    @property
    def size(self) -> int:
        """Return the number of mapped pitch frames."""

        return len(self.times)

    def slice(
        self,
        start_time: float,
        end_time: float,
    ) -> MappedPitchTrack:
        """Return the mapped pitch data within a time interval."""

        if end_time < start_time:
            raise ValueError(
                "end_time must be greater than or equal to start_time."
            )

        mask = (
            (self.times >= float(start_time))
            & (self.times <= float(end_time))
        )

        return MappedPitchTrack(
            times=self.times[mask],
            frequencies_hz=self.frequencies_hz[mask],
            confidence=self.confidence[mask],
            voiced=self.voiced[mask],
            cents_from_sa=self.cents_from_sa[mask],
            nearest_positions=self.nearest_positions[mask],
            nearest_octaves=self.nearest_octaves[mask],
            svara_names=self.svara_names[mask],
        )


class PitchMapper:
    """Map analyzed frequencies into a PitchSystem."""

    def __init__(self, pitch_system: PitchSystem):
        self.pitch_system = pitch_system

        self._reference_cents = np.asarray(
            [
                self.pitch_system.cents_for_position(
                    position
                )
                for position in self.pitch_system.active_notes
            ],
            dtype=np.float64,
        )

        self._reference_positions = np.asarray(
            list(
                self.pitch_system.active_notes.keys()
            ),
            dtype=np.int16,
        )

        self._reference_names = np.asarray(
            list(
                self.pitch_system.active_notes.values()
            ),
            dtype=object,
        )

    def map_track(
        self,
        pitch_track: PitchTrack,
    ) -> MappedPitchTrack:
        """Map every valid pitch sample onto the svara coordinate system."""

        frequencies = np.asarray(
            pitch_track.frequencies_hz,
            dtype=np.float64,
        )

        cents_from_sa = np.full(
            len(frequencies),
            np.nan,
            dtype=np.float64,
        )

        nearest_positions = np.full(
            len(frequencies),
            -1,
            dtype=np.int16,
        )

        nearest_octaves = np.zeros(
            len(frequencies),
            dtype=np.int16,
        )

        svara_names = np.full(
            len(frequencies),
            None,
            dtype=object,
        )

        valid = (
            np.isfinite(frequencies)
            & (frequencies > 0.0)
        )

        if np.any(valid):
            valid_frequencies = frequencies[valid]

            cents = (
                1200.0
                * np.log2(
                    valid_frequencies
                    / self.pitch_system.sa_frequency_hz
                )
            )

            cents_from_sa[valid] = cents

            # Determine the nearest active note across adjacent octaves.
            # A three-octave window is sufficient because the nearest
            # reference around any point lies in the current or adjacent
            # octave.
            octave_indices = np.floor(
                cents / 1200.0
            ).astype(np.int16)

            octave_indices = np.clip(
                octave_indices,
                -32767,
                32767,
            )

            best_distance = np.full(
                len(valid_frequencies),
                np.inf,
                dtype=np.float64,
            )
            best_position = np.full(
                len(valid_frequencies),
                -1,
                dtype=np.int16,
            )
            best_octave = np.zeros(
                len(valid_frequencies),
                dtype=np.int16,
            )
            best_name = np.full(
                len(valid_frequencies),
                None,
                dtype=object,
            )

            for octave_offset in (-1, 0, 1):
                candidate_octaves = (
                    octave_indices + octave_offset
                )

                for (
                    position,
                    base_cents,
                    name,
                ) in zip(
                    self._reference_positions,
                    self._reference_cents,
                    self._reference_names,
                ):
                    candidate_cents = (
                        base_cents
                        + 1200.0
                        * candidate_octaves
                    )

                    distance = np.abs(
                        cents - candidate_cents
                    )

                    update = (
                        distance < best_distance
                    )

                    best_distance[update] = (
                        distance[update]
                    )
                    best_position[update] = position
                    best_octave[update] = (
                        candidate_octaves[update]
                    )
                    best_name[update] = name

            nearest_positions[valid] = best_position
            nearest_octaves[valid] = best_octave
            svara_names[valid] = best_name

        return MappedPitchTrack(
            times=pitch_track.times,
            frequencies_hz=pitch_track.frequencies_hz,
            confidence=pitch_track.confidence,
            voiced=pitch_track.voiced,
            cents_from_sa=cents_from_sa,
            nearest_positions=nearest_positions,
            nearest_octaves=nearest_octaves,
            svara_names=svara_names,
        )

    def reference_lines(
        self,
        min_octave: int = -1,
        max_octave: int = 1,
    ) -> list[tuple[float, str]]:
        """Return (cents, label) pairs for pitch-graph reference lines."""

        return [
            (
                cents,
                label,
            )
            for cents, _position, label, _octave in
            self.pitch_system.reference_notes(
                min_octave=min_octave,
                max_octave=max_octave,
            )
        ]
