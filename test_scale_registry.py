from pathlib import Path
import tempfile

from scale_registry import ScaleRegistry
from pitch_mapper import DEFAULT_RATIOS, PitchMapper, PitchSystem


def main() -> None:
    yaml_text = '''\ndatabase_format: SvaraScaleDatabase\nschema_version: "1.0.0"\nscales:\n  - id: test_major\n    name: Test Major\n    degrees: [0, 2, 4, 5, 7, 9, 11]\n    labels: [Sa, Ri2, Ga3, Ma1, Pa, Dha2, Ni3]\n  - id: test_pentatonic\n    degrees: [0, 2, 4, 7, 9]\n    labels: [Sa, Ri2, Ga3, Pa, Dha2]\n  - id: unnamed_scale\n    degrees: [0, 3, 7]\n    labels: [Sa, Ga2, Pa]\n'''

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "test_scales.yaml"
        path.write_text(yaml_text, encoding="utf-8")

        registry = ScaleRegistry([path])

        assert len(registry) == 3
        assert registry.get("unnamed_scale").display_name == "unnamed_scale"
        assert registry.get("test_pentatonic").active_notes == {
            0: "Sa",
            2: "Ri2",
            4: "Ga3",
            7: "Pa",
            9: "Dha2",
        }

        pitch_system = PitchSystem(
            sa_frequency_hz=195.0,
            ratios=DEFAULT_RATIOS,
            scale=registry.get("test_pentatonic"),
        )

        assert pitch_system.active_notes == {
            0: "Sa",
            2: "Ri2",
            4: "Ga3",
            7: "Pa",
            9: "Dha2",
        }

        mapper = PitchMapper(pitch_system)
        references = mapper.reference_lines()
        assert len(references) == 15

    print("ScaleRegistry test passed.")


if __name__ == "__main__":
    main()
