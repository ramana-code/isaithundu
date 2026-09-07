from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class ScaleDefinition:
    """Definition of a raga/scale used by the pitch mapper.

    Degrees are zero-based chromatic positions relative to Sa and must be in
    the range 0..11. Labels are in the same order as degrees.
    """

    id: str
    degrees: tuple[int, ...]
    labels: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        scale_id = str(self.id).strip()
        if not scale_id:
            raise ValueError("Scale ID must not be empty.")

        degrees = tuple(int(degree) for degree in self.degrees)
        labels = tuple(str(label).strip() for label in self.labels)

        if not degrees:
            raise ValueError(
                f"Scale '{scale_id}' must contain at least one degree."
            )

        if len(degrees) != len(labels):
            raise ValueError(
                f"Scale '{scale_id}' has {len(degrees)} degrees but "
                f"{len(labels)} labels."
            )

        if any(degree < 0 or degree > 11 for degree in degrees):
            raise ValueError(
                f"Scale '{scale_id}' has a degree outside the range 0..11."
            )

        if len(set(degrees)) != len(degrees):
            raise ValueError(
                f"Scale '{scale_id}' contains duplicate degrees."
            )

        if 0 not in degrees:
            raise ValueError(
                f"Scale '{scale_id}' must contain Sa at degree 0."
            )

        if any(not label for label in labels):
            raise ValueError(
                f"Scale '{scale_id}' contains an empty label."
            )

        # Labels are stored as the user supplied values. If name is omitted,
        # the ID is the effective display name.
        effective_name = (
            str(self.name).strip()
            if self.name is not None and str(self.name).strip()
            else scale_id
        )

        object.__setattr__(self, "id", scale_id)
        object.__setattr__(self, "degrees", degrees)
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "name", effective_name)

    @property
    def display_name(self) -> str:
        """Return the human-readable name of the scale."""

        return self.name or self.id

    @property
    def active_notes(self) -> dict[int, str]:
        """Return the active degree-to-label mapping."""

        return dict(zip(self.degrees, self.labels))


class ScaleRegistry:
    """Registry of raga/scale definitions loaded from YAML databases."""

    def __init__(
        self,
        yaml_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self._scales: dict[str, ScaleDefinition] = {}

        if yaml_paths is not None:
            for yaml_path in yaml_paths:
                self.load(yaml_path)

    def load(self, yaml_path: str | Path) -> None:
        """Load scale definitions from one YAML database file."""

        path = Path(yaml_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(file)

        if data is None:
            raise ValueError(
                f"Scale database is empty: {path}"
            )

        if not isinstance(data, dict):
            raise ValueError(
                f"Scale database root must be a mapping: {path}"
            )

        scales = data.get("scales")

        if not isinstance(scales, list):
            raise ValueError(
                f"Scale database '{path}' must contain a 'scales' list."
            )

        for index, item in enumerate(scales, start=1):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Scale #{index} in '{path}' must be a mapping."
                )

            scale = self._parse_scale(
                item,
                source=path,
                index=index,
            )

            if scale.id in self._scales:
                raise ValueError(
                    f"Duplicate scale ID '{scale.id}' while loading '{path}'."
                )

            self._scales[scale.id] = scale

    def _parse_scale(
        self,
        item: dict,
        *,
        source: Path,
        index: int,
    ) -> ScaleDefinition:
        scale_id = item.get("id")
        degrees = item.get("degrees")
        labels = item.get("labels")
        name = item.get("name")

        if scale_id is None:
            raise ValueError(
                f"Scale #{index} in '{source}' is missing 'id'."
            )

        if degrees is None:
            raise ValueError(
                f"Scale '{scale_id}' in '{source}' is missing 'degrees'."
            )

        if labels is None:
            raise ValueError(
                f"Scale '{scale_id}' in '{source}' is missing 'labels'."
            )

        if not isinstance(degrees, list):
            raise ValueError(
                f"Scale '{scale_id}' in '{source}' must use a list for 'degrees'."
            )

        if not isinstance(labels, list):
            raise ValueError(
                f"Scale '{scale_id}' in '{source}' must use a list for 'labels'."
            )

        return ScaleDefinition(
            id=str(scale_id),
            name=None if name is None else str(name),
            degrees=tuple(degrees),
            labels=tuple(labels),
        )

    def get(self, scale_id: str) -> ScaleDefinition:
        """Return a registered scale by ID."""

        try:
            return self._scales[str(scale_id)]
        except KeyError:
            raise KeyError(
                f"Unknown scale ID: '{scale_id}'."
            ) from None

    def __contains__(self, scale_id: object) -> bool:
        return str(scale_id) in self._scales

    def __len__(self) -> int:
        return len(self._scales)

    def ids(self) -> tuple[str, ...]:
        """Return registered scale IDs in load order."""

        return tuple(self._scales)

    def values(self) -> tuple[ScaleDefinition, ...]:
        """Return registered scale definitions in load order."""

        return tuple(self._scales.values())

    def get_name(self, scale_id: str) -> str:
        """Return the display name for a registered scale."""

        return self.get(scale_id).display_name

    def items(self) -> tuple[tuple[str, ScaleDefinition], ...]:
        """Return registered (ID, definition) pairs in load order."""

        return tuple(self._scales.items())
