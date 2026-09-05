from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

from metadata import MetadataParser
from audio_loader import AudioLoader
from waveform import SynchronizedWaveforms


def main():
    # ---------------------------------------------------------
    # File paths
    # ---------------------------------------------------------

    yaml_path = Path("mohananga.yaml")
    ui_path = Path("ui/player.ui")

    # ---------------------------------------------------------
    # Qt application
    # ---------------------------------------------------------

    app = QApplication(sys.argv)

    # ---------------------------------------------------------
    # Load the Qt Designer UI
    # ---------------------------------------------------------

    ui_file = QFile(str(ui_path))

    if not ui_file.open(QFile.ReadOnly):
        raise RuntimeError(
            f"Could not open UI file: {ui_path}"
        )

    loader = QUiLoader()
    window = loader.load(ui_file)
    ui_file.close()

    if window is None:
        raise RuntimeError(
            f"Could not load UI file: {ui_path}"
        )

    # ---------------------------------------------------------
    # Load metadata
    # ---------------------------------------------------------

    parser = MetadataParser()
    metadata = parser.load(yaml_path)

    # ---------------------------------------------------------
    # Find the audio file
    # ---------------------------------------------------------

    audio_path = yaml_path.parent / metadata.audio_filename

    # ---------------------------------------------------------
    # Load audio
    # ---------------------------------------------------------

    audio_loader = AudioLoader()
    audio = audio_loader.load(audio_path)

    # ---------------------------------------------------------
    # Find the two waveform frames from the UI
    # ---------------------------------------------------------

    top_frame = window.findChild(
        type(window.centralWidget()),
        "topWaveformFrame",
    )

    bottom_frame = window.findChild(
        type(window.centralWidget()),
        "bottomWaveformFrame",
    )

    if top_frame is None:
        raise RuntimeError(
            "Could not find 'topWaveformFrame' in the UI."
        )

    if bottom_frame is None:
        raise RuntimeError(
            "Could not find 'bottomWaveformFrame' in the UI."
        )

    # ---------------------------------------------------------
    # Create synchronized waveform views
    # ---------------------------------------------------------

    waveforms = SynchronizedWaveforms(
        top_frame,
        bottom_frame,
    )

    # ---------------------------------------------------------
    # Give the waveform views the loaded audio
    # ---------------------------------------------------------

    waveforms.set_audio(audio)

    # Start at the beginning of the audio.
    waveforms.set_current_time(30.0)

    # ---------------------------------------------------------
    # Display some information in the terminal
    # ---------------------------------------------------------

    print("Audio loaded successfully")
    print("-------------------------")
    print(f"Audio file    : {audio.source_path}")
    print(f"Sample rate   : {audio.sample_rate:,} Hz")
    print(f"Samples       : {len(audio.samples):,}")
    print(f"Duration      : {audio.duration:,.3f} seconds")

    # ---------------------------------------------------------
    # Show the window
    # ---------------------------------------------------------

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()