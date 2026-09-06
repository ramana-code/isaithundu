from pathlib import Path
import sys

from PySide6.QtCore import QFile, QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
)

from audio_loader import AudioLoader
from audio_player import AudioPlayer
from metadata import (
    MetadataParser,
    Marker,
    format_seconds_as_time,
    generate_marker_id,
)
from marker_table import MarkerTable
from marker_dialog import MarkerDialog
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
    metadata.ensure_default_markers_and_region(
        audio.duration
    )

    top_frame = window.findChild(QFrame, "topWaveformFrame")
    bottom_frame = window.findChild(QFrame, "bottomWaveformFrame")
    play_frame = window.findChild(QFrame, "playFrame")
    marker_frame = window.findChild(QFrame, "markerFrame")
    if top_frame is None or bottom_frame is None:
        raise RuntimeError("Could not find waveform frames in the UI.")
    if play_frame is None:
        raise RuntimeError("Could not find 'playFrame' in the UI.")
    if marker_frame is None:
        raise RuntimeError("Could not find 'markerFrame' in the UI.")

    waveforms = SynchronizedWaveforms(top_frame, bottom_frame)
    waveforms.set_audio(audio)
    waveforms.set_markers(metadata)

    # ---------------------------------------------------------
    # Marker table
    # ---------------------------------------------------------

    marker_table = MarkerTable(marker_frame)

    marker_layout = marker_frame.layout()
    if marker_layout is None:
        marker_layout = QVBoxLayout(marker_frame)

    marker_layout.setContentsMargins(0, 0, 0, 0)
    marker_layout.setSpacing(0)
    marker_layout.addWidget(marker_table)

    marker_table.set_markers(metadata.markers)

    def play_region_near_marker(marker_id: str):
        marker = metadata.markers.get(marker_id)

        if marker is None:
            return

        marker_time = marker.seconds

        start_time = max(
            0.0,
            marker_time - 5.0,
        )

        end_time = min(
            audio.duration,
            marker_time + 5.0,
        )
        marker_table.set_playback_active(True)

        player.play(
            start_time=start_time,
            end_time=end_time,
        )

    def edit_marker(marker_id: str):
        marker = metadata.markers.get(marker_id)

        if marker is None:
            return

        dialog = MarkerDialog(
            marker,
            parent=window,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            waveforms.set_markers(metadata)

            marker_table.set_markers(
                metadata.markers,
                select_marker_id=marker_id,
            )

            waveforms.select_marker(marker_id)

    def recenter_waveform(marker_id: str):
        marker = metadata.markers.get(marker_id)

        if marker is None:
            return

        waveforms.recenter_on_time(marker.seconds)

    def delete_marker(marker_id: str):
        if marker_id not in metadata.markers:
            return

        del metadata.markers[marker_id]

        waveforms.set_markers(metadata)
        marker_table.set_markers(metadata.markers)

    marker_table.play_near_marker_requested.connect(
        play_region_near_marker
    )

    marker_table.recenter_requested.connect(
        recenter_waveform
    )

    marker_table.edit_requested.connect(
        edit_marker
    )

    marker_table.delete_requested.connect(
        delete_marker
    )

    marker_table.marker_double_clicked.connect(
        edit_marker
    )

    first_region = metadata.regions[0]
    region_start = metadata.get_region_start_seconds(first_region)
    region_end = metadata.get_region_end_seconds(first_region)
    waveforms.set_current_time(region_start)

    player = AudioPlayer()
    player.set_audio(audio)

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
        player.set_loop(loop_checkbox.isChecked())

        waveforms.set_playback_position(
            player.current_time
        )
        marker_table.set_playback_active(True)

        player.play(
            start_time=region_start,
            end_time=region_end,
        )

    def pause_playback():
        player.pause()
        marker_table.set_playback_active(False)

    def stop_playback():
        player.stop()
        waveforms.set_current_time(region_start)
        marker_table.set_playback_active(False)

    def on_waveform_clicked(seconds: float):
        # Markers may be created only when playback is stopped or paused.
        if player.is_playing:
            return

        marker_id = generate_marker_id(set(metadata.markers))
        marker = Marker(
            id=marker_id,
            time=format_seconds_as_time(seconds),
        )

        metadata.markers[marker_id] = marker

        waveforms.set_markers(metadata)
        marker_table.set_markers(
            metadata.markers,
            select_marker_id=marker_id,
        )
        waveforms.select_marker(marker_id)

        print(f"Created marker: {marker.id} at {marker.time}")

    def select_marker_from_table(marker_id: str):
        waveforms.select_marker(marker_id)

    def select_marker_from_waveform(marker_id: str):
        marker_table.select_marker(marker_id)

    waveforms.waveform_clicked.connect(on_waveform_clicked)
    marker_table.marker_selected.connect(select_marker_from_table)

    play_button.clicked.connect(play_region)
    pause_button.clicked.connect(pause_playback)
    stop_button.clicked.connect(stop_playback)
    loop_checkbox.toggled.connect(player.set_loop)

    position_timer = QTimer(window)
    position_timer.setInterval(30)

    def update_position():
        playing = player.is_playing

        if playing:
            waveforms.set_playback_position(
                player.current_time
            )

        marker_table.set_playback_active(playing)

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
