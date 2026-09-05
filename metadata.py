from dataclasses import dataclass
from typing import Optional
import yaml


def parse_time_to_seconds(time_value) -> float:
    """
    Convert a human-readable time value to seconds.

    Accepted formats:
        "hh:mm:ss"
        "hh:mm:ss.m"
        "mm:ss"
        "mm:ss.m"
        "ss"
        "ss.m"

    Examples:
        "01:02:03.125" -> 3723.125
        "02:03.5"      -> 123.5
        "90.25"        -> 90.25
        90.25          -> 90.25
    """

    if isinstance(time_value, (int, float)):
        if time_value < 0:
            raise ValueError("Time cannot be negative.")
        return float(time_value)

    if not isinstance(time_value, str):
        raise ValueError(f"Invalid time value: {time_value!r}")

    value = time_value.strip()

    if not value:
        raise ValueError("Time cannot be empty.")

    try:
        parts = value.split(":")

        if len(parts) == 1:
            seconds = float(parts[0])

        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])

            if minutes < 0 or seconds < 0:
                raise ValueError

            if seconds >= 60:
                raise ValueError(
                    f"Invalid time '{value}': seconds must be < 60."
                )

            seconds += minutes * 60

        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])

            if hours < 0 or minutes < 0 or seconds < 0:
                raise ValueError

            if minutes >= 60:
                raise ValueError(
                    f"Invalid time '{value}': minutes must be < 60."
                )

            if seconds >= 60:
                raise ValueError(
                    f"Invalid time '{value}': seconds must be < 60."
                )

            seconds += minutes * 60
            seconds += hours * 3600

        else:
            raise ValueError

    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid time format: '{value}'"
        ) from None

    if seconds < 0:
        raise ValueError("Time cannot be negative.")

    return seconds


def format_seconds_as_time(seconds: float) -> str:
    """
    Convert seconds into the canonical human-readable metadata format.

    Under one hour:
        MM:SS
        MM:SS.m

    One hour or more:
        HH:MM:SS
        HH:MM:SS.m

    Examples:
        30       -> "00:30"
        30.5     -> "00:30.5"
        90       -> "01:30"
        90.125   -> "01:30.125"
        3600     -> "01:00:00"
        3723.125 -> "01:02:03.125"
    """

    if seconds < 0:
        raise ValueError("Time cannot be negative.")

    seconds = round(float(seconds), 6)

    hours = int(seconds // 3600)
    remaining = seconds - (hours * 3600)

    minutes = int(remaining // 60)
    remaining -= minutes * 60

    if remaining >= 60:
        remaining = 0
        minutes += 1

    if minutes >= 60:
        minutes = 0
        hours += 1

    if remaining.is_integer():
        seconds_text = f"{int(remaining):02d}"
    else:
        seconds_text = f"{remaining:09.6f}".rstrip("0")

        if remaining < 10:
            seconds_text = "0" + seconds_text

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds_text}"

    return f"{minutes:02d}:{seconds_text}"


@dataclass
class Marker:
    """
    A position marker on the audio timeline.
    """

    id: str
    time: str
    label: Optional[str] = None
    description: str = ""

    @property
    def display_label(self) -> str:
        """Return the label to display in the GUI."""
        return self.label or self.id

    @property
    def seconds(self) -> float:
        """Return the marker position as seconds."""
        return parse_time_to_seconds(self.time)

    def set_time(self, seconds: float) -> None:
        """Set the marker time using seconds."""
        self.time = format_seconds_as_time(seconds)


@dataclass
class Region:
    """
    A region defined by two marker IDs.

    The region does not store its own start/end times.
    Those are resolved through the referenced markers.
    """

    id: str
    start: str
    end: str
    label: Optional[str] = None
    description: str = ""

    @property
    def display_label(self) -> str:
        """Return the label to display in the GUI."""
        return self.label or self.id


@dataclass
class AudioMetadata:
    """
    In-memory representation of the complete metadata document.
    """

    file_format: str
    schema_version: str
    audio_filename: str
    markers: dict[str, Marker]
    regions: list[Region]

    def get_marker(self, marker_id: str) -> Optional[Marker]:
        return self.markers.get(marker_id)

    def get_region(self, region_id: str) -> Optional[Region]:
        for region in self.regions:
            if region.id == region_id:
                return region

        return None

    def get_region_start_seconds(self, region: Region) -> float:
        marker = self.get_marker(region.start)

        if marker is None:
            raise ValueError(
                f"Region '{region.id}' references "
                f"unknown start marker '{region.start}'."
            )

        return marker.seconds

    def get_region_end_seconds(self, region: Region) -> float:
        marker = self.get_marker(region.end)

        if marker is None:
            raise ValueError(
                f"Region '{region.id}' references "
                f"unknown end marker '{region.end}'."
            )

        return marker.seconds


class MetadataParser:
    """
    Load an AudioMetadata object from a YAML file.
    """

    def load(self, yaml_filepath: str) -> AudioMetadata:
        with open(yaml_filepath, "r", encoding="utf-8") as file:
            raw_data = yaml.safe_load(file)

        if raw_data is None:
            raise ValueError("Metadata file is empty.")

        if not isinstance(raw_data, dict):
            raise ValueError(
                "Metadata root must be a YAML mapping."
            )

        return self._parse_document(raw_data)

    def _parse_document(self, data: dict) -> AudioMetadata:
        file_format = data.get("file_format")
        schema_version = data.get("schema_version")

        if not file_format:
            raise ValueError("Missing 'file_format'.")

        if not schema_version:
            raise ValueError("Missing 'schema_version'.")

        target_audio = data.get("target_audio")

        if not isinstance(target_audio, dict):
            raise ValueError(
                "Missing or invalid 'target_audio' section."
            )

        audio_filename = target_audio.get("file_name")

        if not audio_filename:
            raise ValueError(
                "Missing 'target_audio.file_name'."
            )

        markers = self._parse_markers(
            data.get("markers", [])
        )

        regions = self._parse_regions(
            data.get("regions", []),
            markers
        )

        return AudioMetadata(
            file_format=file_format,
            schema_version=schema_version,
            audio_filename=audio_filename,
            markers=markers,
            regions=regions,
        )

    def _parse_markers(self, marker_data) -> dict[str, Marker]:
        if not isinstance(marker_data, list):
            raise ValueError("'markers' must be a list.")

        markers = {}

        for index, item in enumerate(marker_data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Marker #{index + 1} must be a mapping."
                )

            marker_id = item.get("id")
            time = item.get("time")

            if not marker_id:
                raise ValueError(
                    f"Marker #{index + 1} is missing 'id'."
                )

            if time is None:
                raise ValueError(
                    f"Marker '{marker_id}' is missing 'time'."
                )

            if marker_id in markers:
                raise ValueError(
                    f"Duplicate marker ID: '{marker_id}'."
                )

            parse_time_to_seconds(time)

            markers[marker_id] = Marker(
                id=marker_id,
                time=str(time),
                label=item.get("label"),
                description=item.get("description", ""),
            )

        return markers

    def _parse_regions(
        self,
        region_data,
        markers: dict[str, Marker],
    ) -> list[Region]:

        if not isinstance(region_data, list):
            raise ValueError("'regions' must be a list.")

        regions = []
        region_ids = set()

        for index, item in enumerate(region_data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Region #{index + 1} must be a mapping."
                )

            region_id = item.get("id")
            start = item.get("start")
            end = item.get("end")

            if not region_id:
                raise ValueError(
                    f"Region #{index + 1} is missing 'id'."
                )

            if region_id in region_ids:
                raise ValueError(
                    f"Duplicate region ID: '{region_id}'."
                )

            if not start:
                raise ValueError(
                    f"Region '{region_id}' is missing 'start'."
                )

            if not end:
                raise ValueError(
                    f"Region '{region_id}' is missing 'end'."
                )

            if start not in markers:
                raise ValueError(
                    f"Region '{region_id}' references "
                    f"unknown start marker '{start}'."
                )

            if end not in markers:
                raise ValueError(
                    f"Region '{region_id}' references "
                    f"unknown end marker '{end}'."
                )

            start_seconds = markers[start].seconds
            end_seconds = markers[end].seconds

            if end_seconds < start_seconds:
                raise ValueError(
                    f"Region '{region_id}' ends before it starts."
                )

            regions.append(
                Region(
                    id=region_id,
                    start=start,
                    end=end,
                    label=item.get("label"),
                    description=item.get("description", ""),
                )
            )

            region_ids.add(region_id)

        return regions


class MetadataSerializer:
    """
    Save an AudioMetadata object to YAML.

    Marker times are always written in canonical human-readable
    format:
        MM:SS
        MM:SS.m
        HH:MM:SS
        HH:MM:SS.m
    """

    def save(self, metadata: AudioMetadata, yaml_filepath: str) -> None:
        data = self._build_document(metadata)

        with open(yaml_filepath, "w", encoding="utf-8") as file:
            yaml.safe_dump(
                data,
                file,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )

    def _build_document(self, metadata: AudioMetadata) -> dict:
        return {
            "file_format": metadata.file_format,
            "schema_version": metadata.schema_version,
            "target_audio": {
                "file_name": metadata.audio_filename,
            },
            "markers": [
                self._serialize_marker(marker)
                for marker in metadata.markers.values()
            ],
            "regions": [
                self._serialize_region(region)
                for region in metadata.regions
            ],
        }

    def _serialize_marker(self, marker: Marker) -> dict:
        data = {
            "id": marker.id,
            "time": format_seconds_as_time(marker.seconds),
        }

        if marker.label:
            data["label"] = marker.label

        if marker.description:
            data["description"] = marker.description

        return data

    def _serialize_region(self, region: Region) -> dict:
        data = {
            "id": region.id,
            "start": region.start,
            "end": region.end,
        }

        if region.label:
            data["label"] = region.label

        if region.description:
            data["description"] = region.description

        return data
