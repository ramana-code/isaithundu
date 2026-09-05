from pathlib import Path
import sys

from PySide6.QtCore import QFile, QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QHBoxLayout, QPushButton

from audio_loader import AudioLoader
from audio_player import AudioPlayer
from metadata import MetadataParser, Marker
from waveform import SynchronizedWaveforms

YAML_PATH = Path("mohananga.yaml")
UI_PATH = Path("ui/player.ui")


def main():
    app = QApplication(sys.argv)
    ui_file = QFile(str(UI_PATH))
    if not ui_file.open(QFile.ReadOnly):
        raise RuntimeError(f"Could not open UI file: {UI_PATH}")
    window = QUiLoader().load(ui_file)
    ui_file.close()
    if window is None:
        raise RuntimeError(f"Could not load UI file: {UI_PATH}")

    metadata = MetadataParser().load(str(YAML_PATH))
    audio_path = YAML_PATH.parent / metadata.audio_filename
    audio = AudioLoader().load(audio_path)

    top_frame = window.findChild(QFrame, "topWaveformFrame")
    bottom_frame = window.findChild(QFrame, "bottomWaveformFrame")
    play_frame = window.findChild(QFrame, "playFrame")
    if top_frame is None or bottom_frame is None:
        raise RuntimeError("Could not find waveform frames in the UI.")
    if play_frame is None:
        raise RuntimeError("Could not find 'playFrame' in the UI.")

    waveforms = SynchronizedWaveforms(top_frame, bottom_frame)
    waveforms.set_audio(audio)
    waveforms.set_markers(metadata)

    if not metadata.regions:
        raise RuntimeError("The YAML metadata contains no regions.")

    first_region = metadata.regions[0]
    region_start = metadata.get_region_start_seconds(first_region)
    region_end = metadata.get_region_end_seconds(first_region)
    waveforms.set_current_time(region_start)

    player = AudioPlayer()
    player.set_audio(audio)
    playback_active = False

    layout = play_frame.layout()
    if layout is None:
        layout = QHBoxLayout(play_frame)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    play_button = QPushButton("Play")
    pause_button = QPushButton("Pause")
    stop_button = QPushButton("Stop")
    loop_checkbox = QCheckBox("Loop")
    layout.addWidget(play_button)
    layout.addWidget(pause_button)
    layout.addWidget(stop_button)
    layout.addWidget(loop_checkbox)
    layout.addStretch()

    def play_region():
        nonlocal playback_active
        playback_active = True
        player.set_loop(loop_checkbox.isChecked())
        player.play(start_time=region_start, end_time=region_end)

    def pause_playback():
        nonlocal playback_active
        playback_active = False
        player.pause()

    def stop_playback():
        nonlocal playback_active
        playback_active = False
        player.stop()
        waveforms.set_current_time(region_start)

    def on_waveform_clicked(seconds: float):
        if playback_active:
            return

        marker_id = f"marker{len(metadata.markers) + 1}"

        while marker_id in metadata.markers:
            marker_id = f"marker{len(metadata.markers) + 1}"

        marker = Marker(
            id=marker_id,
            time=f"{seconds:.3f}",
        )

        metadata.markers[marker_id] = marker
        waveforms.set_markers(metadata)

        print(f"Created marker: {marker.display_label} at {marker.time} seconds")

    waveforms.waveform_clicked.connect(on_waveform_clicked)
    play_button.clicked.connect(play_region)
    pause_button.clicked.connect(pause_playback)
    stop_button.clicked.connect(stop_playback)
    loop_checkbox.toggled.connect(player.set_loop)

    position_timer = QTimer(window)
    position_timer.setInterval(30)

    def update_position():
        waveforms.set_current_time(player.current_time)

    position_timer.timeout.connect(update_position)
    position_timer.start()

    def shutdown():
        position_timer.stop()
        player.close()

    app.aboutToQuit.connect(shutdown)

    print("Audio loaded successfully")
    print("-------------------------")
    print(f"Audio file    : {audio.source_path}")
    print(f"Sample rate   : {audio.sample_rate:,} Hz")
    print(f"Samples       : {len(audio.samples):,}")
    print(f"Duration      : {audio.duration:,.3f} seconds")
    print()
    print("First region")
    print("------------")
    print(f"Region        : {first_region.display_label}")
    print(f"Start         : {region_start:.3f} seconds")
    print(f"End           : {region_end:.3f} seconds")
    print(f"Length        : {region_end - region_start:.3f} seconds")

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
