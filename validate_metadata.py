#!/usr/bin/env python3
"""
Validate an audio metadata YAML file before loading it in the GUI application.

Usage:
    python validate_metadata.py path/to/metadata.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import librosa
import yaml

from audio_loader import AudioLoader
from metadata import MetadataParser
from scale_registry import ScaleRegistry


SCALE_DATABASE_PATHS = (
    Path("data/melakarta.yaml"),
    Path("data/janyaragas.yaml"),
)

# Keep these in sync with the corresponding application constants.
RESERVED_MARKER_IDS = {"m000", "m999"}
RESERVED_REGION_IDS = {"rall"}


def validate_raw_yaml(path: Path) -> dict:
    """Parse YAML and perform basic structural checks."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML syntax: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read '{path}': {exc}") from exc

    if data is None:
        raise ValueError("YAML file is empty.")

    if not isinstance(data, dict):
        raise ValueError("Top-level YAML value must be a mapping.")

    target_audio = data.get("target_audio")
    if target_audio is not None and not isinstance(target_audio, dict):
        raise ValueError("'target_audio' must be a mapping.")

    return data


def validate_file_name(metadata_path: Path, raw_data: dict) -> Path:
    """Resolve the audio file referenced by target_audio.file_name."""

    target_audio = raw_data.get("target_audio", {})
    file_name = target_audio.get("file_name")

    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError(
            "'target_audio.file_name' is missing or is not a non-empty string."
        )

    audio_path = Path(file_name).expanduser()

    if not audio_path.is_absolute():
        audio_path = metadata_path.parent / audio_path

    audio_path = audio_path.resolve()

    if not audio_path.is_file():
        raise ValueError(f"Audio file does not exist: {audio_path}")

    return audio_path


def validate_raw_tuning(raw_data: dict) -> None:
    """Check the tuning fields before invoking MetadataParser."""

    target_audio = raw_data.get("target_audio", {})

    sruthi = target_audio.get("sruthi", "E3")
    cents = target_audio.get("cents", 0)

    if not isinstance(sruthi, str) or not sruthi.strip():
        raise ValueError("'target_audio.sruthi' must be a non-empty string.")

    try:
        frequency = float(librosa.note_to_hz(sruthi))
    except Exception as exc:
        raise ValueError(f"Invalid sruthi '{sruthi}'.") from exc

    if frequency <= 0.0:
        raise ValueError(
            f"Sruthi '{sruthi}' does not resolve to a positive frequency."
        )

    if isinstance(cents, bool):
        raise ValueError("'target_audio.cents' must be numeric, not boolean.")

    try:
        float(cents)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid cents value '{cents}'.") from exc


def validate_metadata_semantics(
    metadata,
    audio_duration: float,
    scale_registry: ScaleRegistry,
) -> list[str]:
    """Validate raga, markers, and regions."""

    problems: list[str] = []

    # Raga / scale.
    try:
        scale_registry.get(metadata.raga)
    except Exception as exc:
        problems.append(
            f"Raga '{metadata.raga}' could not be resolved: {exc}"
        )

    # Markers.
    markers = metadata.markers
    marker_ids = list(markers.keys())

    if len(marker_ids) != len(set(marker_ids)):
        problems.append("Duplicate marker IDs found.")

    for marker_id, marker in markers.items():
        if not marker_id:
            problems.append("Marker has an empty ID.")
            continue

        try:
            seconds = float(marker.seconds)
        except (TypeError, ValueError):
            problems.append(
                f"Marker '{marker_id}' has invalid time '{marker.seconds}'."
            )
            continue

        if seconds < 0.0:
            problems.append(
                f"Marker '{marker_id}' is before audio start ({seconds:.3f} s)."
            )
        elif seconds > audio_duration:
            problems.append(
                f"Marker '{marker_id}' is beyond audio end ({seconds:.3f} s)."
            )

            # Reserved structural markers have fixed semantics when present.
        if marker_id == "m000" and seconds != 0.0:
            problems.append(
                f"Reserved marker 'm000' must be at audio start (0.000 s); "
                f"found {seconds:.3f} s."
            )

        if marker_id == "m999" and seconds != audio_duration:
            problems.append(
                f"Reserved marker 'm999' must be at audio end "
                f"({audio_duration:.3f} s); found {seconds:.3f} s."
            )


    # Regions.
    region_ids = [region.id for region in metadata.regions]

    if len(region_ids) != len(set(region_ids)):
        problems.append("Duplicate region IDs found.")

    for region in metadata.regions:
        if region.id in RESERVED_REGION_IDS:
            if (
                region.id == "rall"
                and (
                    region.start != "m000"
                    or region.end != "m999"
                )
            ):
                problems.append(
                    f"Reserved region 'rall' must use start marker 'm000' "
                    f"and end marker 'm999'."
                )
            elif region.id != "rall":
                problems.append(
                    f"Region ID '{region.id}' is reserved."
                )

        start_id = region.start
        end_id = region.end

        if start_id not in markers:
            problems.append(
                f"Region '{region.id}' references missing start marker '{start_id}'."
            )
            continue

        if end_id not in markers:
            problems.append(
                f"Region '{region.id}' references missing end marker '{end_id}'."
            )
            continue

        start_seconds = float(markers[start_id].seconds)
        end_seconds = float(markers[end_id].seconds)
        duration = end_seconds - start_seconds

        if start_id == end_id:
            problems.append(
                f"Region '{region.id}' uses the same start/end marker '{start_id}'."
            )
        elif start_seconds == end_seconds:
            problems.append(
                f"Region '{region.id}' has identical start/end times ({start_seconds:.3f} s)."
            )
        elif start_seconds > end_seconds:
            problems.append(
                f"Region '{region.id}' has start after end."
            )
        elif duration < 1.0:
            problems.append(
                f"Region '{region.id}' is too short ({duration:.3f} s; minimum 1.000 s)."
            )

        if start_seconds < 0.0 or end_seconds > audio_duration:
            problems.append(
                f"Region '{region.id}' lies outside audio bounds."
            )

    return problems


def validate(path: Path) -> int:
    """Validate one metadata file and return a process exit code."""

    path = path.expanduser().resolve()

    if not path.is_file():
        print(f"ERROR: Metadata file does not exist: {path}")
        return 1

    print(f"Validating: {path}")

    try:
        raw_data = validate_raw_yaml(path)
        validate_raw_tuning(raw_data)
        audio_path = validate_file_name(path, raw_data)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    try:
        metadata = MetadataParser().load(str(path))
    except Exception as exc:
        print(f"ERROR: MetadataParser rejected the file: {exc}")
        return 1

    try:
        audio = AudioLoader().load(audio_path)
    except Exception as exc:
        print(f"ERROR: Could not load referenced audio '{audio_path}': {exc}")
        return 1

    try:
        scale_registry = ScaleRegistry(SCALE_DATABASE_PATHS)
    except Exception as exc:
        print(f"ERROR: Could not initialize ScaleRegistry: {exc}")
        return 1

    problems = validate_metadata_semantics(
        metadata,
        audio.duration,
        scale_registry,
    )

    if problems:
        print()
        for problem in problems:
            print(f"ERROR: {problem}")
        print()
        print(f"Validation FAILED: {len(problems)} problem(s).")
        return 1

    print()
    print("Validation PASSED.")
    print(f"Audio       : {audio_path.name}")
    print(f"Duration    : {audio.duration:.3f} s")
    print(f"Sample rate : {audio.sample_rate:,} Hz")
    print(f"Markers     : {len(metadata.markers)}")
    print(f"Regions     : {len(metadata.regions)}")
    print(f"Raga        : {metadata.raga}")
    print(f"Sruthi      : {metadata.sruthi}")
    print(f"Cents       : {metadata.cents}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an audio metadata YAML file."
    )
    parser.add_argument(
        "metadata",
        type=Path,
        help="Path to the metadata YAML file.",
    )
    args = parser.parse_args()
    return validate(args.metadata)


if __name__ == "__main__":
    sys.exit(main())
