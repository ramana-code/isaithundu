from pathlib import Path
import sys

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication

from audio_loader import AudioLoader
from metadata import MetadataParser
from player_controller import PlayerController

UI_PATH = Path("ui/player.ui")

def load_window():
    """Load the Qt Designer UI."""

    ui_file = QFile(str(UI_PATH))

    if not ui_file.open(QFile.ReadOnly):
        raise RuntimeError(
            f"Could not open UI file: {UI_PATH}"
        )

    window = QUiLoader().load(ui_file)
    ui_file.close()

    if window is None:
        raise RuntimeError(
            f"Could not load UI file: {UI_PATH}"
        )

    return window

def load_metadata(
    yaml_path: Path,
):
    """Load metadata from the YAML file."""

    return MetadataParser().load(
        str(yaml_path)
    )

def load_audio(
    metadata,
    yaml_path: Path,
):
    """Load the audio referenced by the metadata."""

    audio_path = (
        yaml_path.parent
        / metadata.audio_filename
    )

    return AudioLoader().load(
        audio_path
    )

def main():
    app = QApplication(sys.argv)

    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python main.py <metadata.yaml>"
        )

    yaml_path = Path(
        sys.argv[1]
    ).expanduser().resolve()

    window = load_window()

    metadata = load_metadata(yaml_path)

    audio = load_audio(
        metadata,
        yaml_path,
    )

    metadata.ensure_default_markers_and_region(
        audio.duration
    )

    controller = PlayerController(
        window=window,
        metadata=metadata,
        audio=audio,
        metadata_path=yaml_path,
    )

    app.aboutToQuit.connect(
        controller.shutdown
    )

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()

