#!/usr/bin/env python3
"""Generate a compact YAML database of the 72 Melakarta ragas using librosa."""

from __future__ import annotations

import argparse
from pathlib import Path

import librosa
import yaml

class CompactList(list):
    """A list that should be written in YAML flow style."""


def compact_list_representer(
    dumper: yaml.Dumper,
    data: CompactList,
):
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq",
        data,
        flow_style=True,
    )


yaml.SafeDumper.add_representer(
    CompactList,
    compact_list_representer,
)


def build_melakarta_database() -> dict:
    """Build the compact Melakarta database from librosa."""

    mela_map = librosa.list_mela()

    # list_mela() maps raga names -> Melakarta numbers 1..72.
    entries = []

    for name, number in sorted(
        mela_map.items(),
        key=lambda item: item[1],
    ):
        degrees = librosa.mela_to_degrees(number)

        # Use full ASCII Svara names: Sa, Ri1, Ri2, ..., Ni3.
        # unicode=False avoids Unicode subscript characters.
        svaras = librosa.mela_to_svara(
            number,
            abbr=False,
            unicode=False,
        )

        degrees = CompactList(
            int(degree)
            for degree in degrees
        )

        labels = CompactList(
            svaras[degree]
            for degree in degrees
        )

        entries.append(
            {
                "id": f"melakarta_{number:03d}",
                "name": name,
                "degrees": degrees,
                "labels": labels,
            }
        )

    return {
        "database_format": "SvaraScaleDatabase",
        "schema_version": "1.0.0",
        "scales": entries,
    }


def validate_database(database: dict) -> None:
    """Validate the generated database before writing it."""

    scales = database.get("scales")

    if not isinstance(scales, list):
        raise ValueError(
            "Generated database does not contain a scales list."
        )

    if len(scales) != 72:
        raise ValueError(
            f"Expected 72 Melakarta entries, found {len(scales)}."
        )

    ids = set()

    for entry in scales:
        scale_id = entry["id"]

        if scale_id in ids:
            raise ValueError(
                f"Duplicate scale ID generated: {scale_id}"
            )

        ids.add(scale_id)

        degrees = entry["degrees"]
        labels = entry["labels"]

        if len(degrees) != len(labels):
            raise ValueError(
                f"{scale_id}: degrees and labels have different lengths."
            )

        if not degrees:
            raise ValueError(
                f"{scale_id}: scale contains no degrees."
            )

        # Sa is always degree 0.
        if degrees[0] != 0:
            raise ValueError(
                f"{scale_id}: Sa must be degree 0."
            )

        if len(degrees) != 7:
            raise ValueError(
                f"{scale_id}: Melakarta should contain 7 degrees; "
                f"found {len(degrees)}."
            )

        if any(
            not isinstance(degree, int)
            or degree < 0
            or degree > 11
            for degree in degrees
        ):
            raise ValueError(
                f"{scale_id}: degrees must be integers in 0..11."
            )

        if len(set(degrees)) != len(degrees):
            raise ValueError(
                f"{scale_id}: duplicate degree detected."
            )


def write_yaml(database: dict, output_path: Path) -> None:
    """Write the database as compact, readable YAML."""

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        yaml.safe_dump(
            database,
            file,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a YAML database containing all "
            "72 Melakarta ragas from librosa."
        )
    )

    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("melakarta.yaml"),
        help="Output YAML file (default: melakarta.yaml)",
    )

    args = parser.parse_args()

    database = build_melakarta_database()
    validate_database(database)
    write_yaml(database, args.output)

    print(
        f"Wrote {len(database['scales'])} Melakarta definitions "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
