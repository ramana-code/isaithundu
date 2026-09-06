from pathlib import Path
import sys

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication

from audio_loader import AudioLoader
from metadata import MetadataParser
from player_controller import PlayerController


YAML_PATH = Path("mohananga.yaml")
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


def load_metadata():
    """Load metadata from the YAML file."""

    return MetadataParser().load(
        str(YAML_PATH)
    )


def load_audio(metadata):
    """Load the audio referenced by the metadata."""

    audio_path = (
        YAML_PATH.parent
        / metadata.audio_filename
    )

    return AudioLoader().load(
        audio_path
    )


def main():
    app = QApplication(sys.argv)

    window = load_window()

    metadata = load_metadata()

    audio = load_audio(
        metadata
    )

    metadata.ensure_default_markers_and_region(
        audio.duration
    )

    controller = PlayerController(
        window=window,
        metadata=metadata,
        audio=audio,
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

