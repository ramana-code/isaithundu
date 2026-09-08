from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QFileDialog,
)

from audio_player import AudioPlayer
from marker_dialog import MarkerDialog
from region_dialog import RegionDialog
from marker_table import MarkerTable
from metadata import (
    AudioMetadata,
    Marker,
    Region,
    MetadataSerializer,
    format_seconds_as_time,
    generate_marker_id,
    generate_region_id,
)
from waveform import SynchronizedWaveforms
from region_table import RegionTable
from pitch_analyzer import (
    PitchAnalyzer,
    PitchTrack,
    create_pitch_analyzer,
)
from pitch_mapper import (
    DEFAULT_RATIOS,
    PitchMapper,
    PitchSystem,
)
from pitch_view import PitchView
from scale_registry import ScaleRegistry


class PlayerController:
    """
    Coordinate the application-level interaction between:

        - metadata
        - audio
        - audio player
        - waveform views
        - marker table
        - playback controls

    Individual widgets and data models remain responsible for their
    own behavior. This class handles the connections between them.
    """

    POSITION_TIMER_INTERVAL_MS = 30

    PITCH_ANALYZER_BACKEND = "essentia"

    # The raga definitions are maintained independently of librosa.
    SCALE_DATABASE_PATHS = (
        Path("data/melakarta.yaml"),
        Path("data/janyaragas.yaml"),
    )

    def __init__(
        self,
        window,
        metadata: AudioMetadata,
        audio,
        metadata_path: str | Path,
    ):
        self.window = window
        self.metadata = metadata
        self.audio = audio
        self.metadata_path = Path(metadata_path)

        self.player = AudioPlayer()
        self.player.set_audio(audio)

        self.scale_registry = ScaleRegistry(
            self.SCALE_DATABASE_PATHS
        )

        self.pitch_analyzer: PitchAnalyzer | None = None
        self.pitch_track: PitchTrack | None = None
        self.pitch_mapper: PitchMapper | None = None
        self.mapped_pitch_track = None

        self._find_frames()
        self._create_load_panel()
        self._create_waveforms()
        self._create_pitch_view()
        self._create_marker_table()
        self._create_region_table()
        self._create_playback_controls()

        self._initialize_metadata_display()
        self._connect_signals()
        self._create_position_timer()

        self._print_audio_information()

    # -----------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------

    def _find_frames(self) -> None:
        """Find the application frames defined in Qt Designer."""

        self.top_frame = self.window.findChild(
            QFrame,
            "topWaveformFrame",
        )

        self.bottom_frame = self.window.findChild(
            QFrame,
            "bottomWaveformFrame",
        )

        self.play_frame = self.window.findChild(
            QFrame,
            "playFrame",
        )

        self.load_frame = self.window.findChild(
            QFrame,
            "loadFrame",
        )

        self.marker_frame = self.window.findChild(
            QFrame,
            "markerFrame",
        )

        self.region_frame = self.window.findChild(
            QFrame,
            "regionFrame",
        )

        if (
            self.top_frame is None
            or self.bottom_frame is None
        ):
            raise RuntimeError(
                "Could not find waveform frames in the UI."
            )

        if self.play_frame is None:
            raise RuntimeError(
                "Could not find 'playFrame' in the UI."
            )

        if self.load_frame is None:
            raise RuntimeError(
                "Could not find 'loadFrame' in the UI."
            )

        if self.marker_frame is None:
            raise RuntimeError(
                "Could not find 'markerFrame' in the UI."
            )

        if self.region_frame is None:
            raise RuntimeError(
                "Could not find 'regionFrame' in the UI."
            )

    def _create_load_panel(self) -> None:
        """Create the audio information and pitch tuning controls."""

        layout = self.load_frame.layout()

        if layout is None:
            layout = QVBoxLayout(
                self.load_frame
            )

        layout.setContentsMargins(
            8,
            6,
            8,
            6,
        )

        layout.setSpacing(4)

        # ---------------------------------------------------------
        # Audio information
        # ---------------------------------------------------------

        raga = self.scale_registry.get(
            self.metadata.raga
        )

        audio_info_label = QLabel(
            f"Audio: {self.audio.source_path.name}; "
            f"Duration: {self.audio.duration:.3f} s; "
            f"Sample rate: {self.audio.sample_rate:,} Hz; "
            f"Raga: {raga.display_name}"
        )

        audio_info_label.setStyleSheet(
            "font-size: 9pt; color: #666666;"
        )

        audio_info_label.setWordWrap(
            False
        )

        layout.addWidget(
            audio_info_label
        )

        # ---------------------------------------------------------
        # Sruthi
        # ---------------------------------------------------------

        sruthi_layout = QHBoxLayout()

        sruthi_layout.addWidget(
            QLabel("Sruthi:")
        )

        self.sruthi_note_combo = QComboBox()

        self.sruthi_note_combo.addItems(
            [
                "C",
                "C#",
                "D",
                "D#",
                "E",
                "F",
                "F#",
                "G",
                "G#",
                "A",
                "A#",
                "B",
            ]
        )

        octave_layout = QHBoxLayout()

        self.sruthi_octave_spin = QSpinBox()
        self.sruthi_octave_spin.setRange(
            2,
            4,
        )

        sruthi = self.metadata.sruthi

        note = sruthi[:-1]
        octave = int(sruthi[-1])

        note_index = self.sruthi_note_combo.findText(
            note
        )

        if note_index >= 0:
            self.sruthi_note_combo.setCurrentIndex(
                note_index
            )

        self.sruthi_octave_spin.setValue(
            octave
        )

        sruthi_layout.addWidget(
            self.sruthi_note_combo
        )

        sruthi_layout.addWidget(
            self.sruthi_octave_spin
        )

        layout.addLayout(
            sruthi_layout
        )

        # ---------------------------------------------------------
        # Cents
        # ---------------------------------------------------------

        cents_layout = QHBoxLayout()

        cents_layout.addWidget(
            QLabel("Cents:")
        )

        self.cents_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.cents_slider.setRange(
            -50,
            50,
        )

        self.cents_slider.setValue(
            int(round(self.metadata.cents))
        )

        self.cents_spin = QSpinBox()

        self.cents_spin.setRange(
            -50,
            50,
        )

        self.cents_spin.setValue(
            int(round(self.metadata.cents))
        )

        cents_layout.addWidget(
            self.cents_slider
        )

        cents_layout.addWidget(
            self.cents_spin
        )

        layout.addLayout(
            cents_layout
        )

        # ---------------------------------------------------------
        # Playback settings
        # ---------------------------------------------------------

        playback_label = QLabel(
            "Playback"
        )

        playback_label.setStyleSheet(
            "font-weight: bold;"
        )

        layout.addWidget(
            playback_label
        )

        # Target pitch convenience selector.

        target_layout = QHBoxLayout()

        target_layout.addWidget(
            QLabel("Target pitch:")
        )

        self.playback_target_combo = QComboBox()

        self.playback_target_combo.addItems(
            [
                "Original",
                "D#3",
                "E3",
            ]
        )

        target_layout.addWidget(
            self.playback_target_combo
        )

        layout.addLayout(
            target_layout
        )

        # Pitch shift in semitones.

        shift_layout = QHBoxLayout()

        shift_layout.addWidget(
            QLabel("Pitch shift:")
        )

        self.playback_shift_spin = QSpinBox()
        self.playback_shift_spin.setRange(
            -12,
            12,
        )
        self.playback_shift_spin.setValue(
            0
        )

        shift_layout.addWidget(
            self.playback_shift_spin
        )

        layout.addLayout(
            shift_layout
        )

        # Fine pitch adjustment in cents.

        shift_cents_layout = QHBoxLayout()

        shift_cents_layout.addWidget(
            QLabel("Pitch cents:")
        )

        self.playback_shift_cents_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.playback_shift_cents_slider.setRange(
            -50,
            50,
        )
        self.playback_shift_cents_slider.setValue(
            0
        )

        self.playback_shift_cents_spin = QSpinBox()
        self.playback_shift_cents_spin.setRange(
            -50,
            50,
        )
        self.playback_shift_cents_spin.setValue(
            0
        )

        shift_cents_layout.addWidget(
            self.playback_shift_cents_slider
        )

        shift_cents_layout.addWidget(
            self.playback_shift_cents_spin
        )

        layout.addLayout(
            shift_cents_layout
        )

        # Resulting pitch.

        self.playback_result_label = QLabel(
            "Resulting pitch: "
            + self._calculate_playback_result_pitch()
        )

        layout.addWidget(
            self.playback_result_label
        )

        # Playback speed.

        speed_layout = QHBoxLayout()

        speed_layout.addWidget(
            QLabel("Speed:")
        )

        self.playback_speed_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.playback_speed_slider.setRange(
            70,
            130,
        )
        self.playback_speed_slider.setValue(
            100
        )

        self.playback_speed_spin = QDoubleSpinBox()
        self.playback_speed_spin.setRange(
            0.70,
            1.30,
        )
        self.playback_speed_spin.setSingleStep(
            0.01
        )
        self.playback_speed_spin.setDecimals(
            2
        )
        self.playback_speed_spin.setValue(
            1.00
        )

        speed_layout.addWidget(
            self.playback_speed_slider
        )

        speed_layout.addWidget(
            self.playback_speed_spin
        )

        layout.addLayout(
            speed_layout
        )

        # ---------------------------------------------------------
        # Save buttons
        # ---------------------------------------------------------

        save_layout = QHBoxLayout()

        self.analyze_button = QPushButton(
            "Analyze"
        )

        save_layout.addWidget(
            self.analyze_button
        )

        self.apply_tuning_button = QPushButton(
            "Apply"
        )

        save_layout.addWidget(
            self.apply_tuning_button
        )

        self.save_button = QPushButton(
            "Save"
        )

        self.save_as_button = QPushButton(
            "Save As..."
        )

        save_layout.addWidget(
            self.save_button
        )

        save_layout.addWidget(
            self.save_as_button
        )

        layout.addLayout(
            save_layout
        )

        # Keep references to information labels for future updates.
        self.audio_info_label = audio_info_label

    def _create_waveforms(self) -> None:
        """Create and initialize the synchronized waveform views."""

        self.waveforms = SynchronizedWaveforms(
            self.top_frame,
            self.bottom_frame,
        )

        self.waveforms.set_audio(self.audio)
        self.waveforms.set_markers(self.metadata)

    def _analyze_pitch(self) -> None:
        """Analyze the complete audio file once and build the mapped pitch track."""

        self.analyze_button.setEnabled(False)

        self.pitch_analyzer = create_pitch_analyzer(
            backend=self.PITCH_ANALYZER_BACKEND,
        )

        self.pitch_track = (
            self.pitch_analyzer.analyze(
                self.audio
            )
        )

        sa_frequency_hz = (
            self._calculate_sa_frequency()
        )

        scale = self.scale_registry.get(
            self.metadata.raga
        )

        pitch_system = PitchSystem(
            sa_frequency_hz=sa_frequency_hz,
            ratios=DEFAULT_RATIOS,
            scale=scale,
        )

        self.pitch_mapper = PitchMapper(
            pitch_system
        )

        self.mapped_pitch_track = (
            self.pitch_mapper.map_track(
                self.pitch_track
            )
        )

        self.pitch_view.set_pitch_track(
            self.mapped_pitch_track,
            self.pitch_mapper,
        )

        print(
            "Pitch analysis complete"
        )
        print(
            f"Pitch frames  : "
            f"{self.pitch_track.size:,}"
        )

        self.analyze_button.setEnabled(False)

    def _calculate_sa_frequency(self) -> float:
        """Calculate Sa from the YAML sruthi and cents metadata."""

        import librosa

        reference_hz = float(
            librosa.note_to_hz(
                self.metadata.sruthi
            )
        )

        return reference_hz * (
            2.0 ** (
                self.metadata.cents / 1200.0
            )
        )

    def _get_audio_tuning_frequency(self) -> float:
        """Return the frequency represented by the audio Sruthi and cents."""

        import librosa

        reference_hz = float(
            librosa.note_to_hz(
                self.metadata.sruthi
            )
        )

        return reference_hz * (
            2.0 ** (
                self.metadata.cents / 1200.0
            )
        )

    def _pitch_name_from_frequency(
        self,
        frequency_hz: float,
    ) -> str:
        """Return a readable note name plus cents from a frequency."""

        import librosa

        note_name = librosa.hz_to_note(
            frequency_hz,
            cents=True,
        )

        return note_name

    def _calculate_playback_result_pitch(self) -> str:
        """Calculate the resulting pitch from playback shift controls."""

        audio_frequency = (
            self._get_audio_tuning_frequency()
        )

        semitone_shift = (
            self.playback_shift_spin.value()
        )

        cents_shift = (
            self.playback_shift_cents_spin.value()
        )

        total_shift_cents = (
            semitone_shift * 100.0
            + cents_shift
        )

        playback_frequency = (
            audio_frequency
            * (
                2.0 ** (
                    total_shift_cents / 1200.0
                )
            )
        )

        return self._pitch_name_from_frequency(
            playback_frequency
        )

    def _create_pitch_view(self) -> None:
        """Create the pitch view using the bottom waveform window size."""

        self.pitch_frame = self.window.findChild(
            QFrame,
            "pitchFrame",
        )

        if self.pitch_frame is None:
            raise RuntimeError(
                "Could not find 'pitchFrame' in the UI."
            )

        self.pitch_view = PitchView(
            window_seconds=(
                self.waveforms.BOTTOM_WINDOW_SECONDS
            ),
            parent=self.pitch_frame,
        )

        layout = self.pitch_frame.layout()

        if layout is None:
            layout = QVBoxLayout(
                self.pitch_frame
            )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(0)
        layout.addWidget(self.pitch_view)

    def _create_marker_table(self) -> None:
        """Create and install the marker table and Add Marker button."""

        self.marker_table = MarkerTable(
            self.marker_frame
        )

        layout = self.marker_frame.layout()

        if layout is None:
            layout = QVBoxLayout(
                self.marker_frame
            )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(4)

        layout.addWidget(
            self.marker_table
        )

        self.add_marker_button = QPushButton(
            "Add Marker"
        )

        layout.addWidget(
            self.add_marker_button
        )

        self.marker_table.set_markers(
            self.metadata.markers
        )

        self._update_marker_delete_state()

        self.add_marker_button.clicked.connect(
            self.add_marker_at_current_position
        )

    def _create_region_table(self) -> None:
        """Create and install the region table and Add Region button."""

        self.region_table = RegionTable(
            self.region_frame
        )

        layout = self.region_frame.layout()

        if layout is None:
            layout = QVBoxLayout(
                self.region_frame
            )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(4)

        layout.addWidget(
            self.region_table
        )

        self.add_region_button = QPushButton(
            "Add Region"
        )

        layout.addWidget(
            self.add_region_button
        )

        self.region_table.set_regions(
            self.metadata
        )

        self.add_region_button.clicked.connect(
            self.add_region
        )

    def _create_playback_controls(self) -> None:
        """Create the playback controls in playFrame."""

        layout = self.play_frame.layout()

        if layout is None:
            layout = QHBoxLayout(
                self.play_frame
            )

        layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )
        layout.setSpacing(8)

        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.loop_checkbox = QCheckBox("Loop")

        layout.addWidget(self.play_button)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.loop_checkbox)
        layout.addStretch()

    def _initialize_metadata_display(self) -> None:
        """Initialize the active playback region and waveform position."""

        if not self.metadata.regions:
            raise RuntimeError(
                "The metadata contains no regions."
            )

        self.active_region = self.metadata.regions[0]

        self.region_start = (
            self.metadata.get_region_start_seconds(
                self.active_region
            )
        )

        self.region_end = (
            self.metadata.get_region_end_seconds(
                self.active_region
            )
        )

        self._set_current_time(
            self.region_start
        )

    def _connect_signals(self) -> None:
        """Connect UI/widget signals to controller behavior."""

        # Marker table actions.
        self.marker_table.play_near_marker_requested.connect(
            self.play_near_marker
        )

        self.marker_table.loop_near_marker_requested.connect(
            self.loop_near_marker
        )

        self.marker_table.recenter_requested.connect(
            self.recenter_graph
        )

        self.marker_table.edit_requested.connect(
            self.edit_marker
        )

        self.marker_table.delete_requested.connect(
            self.delete_marker
        )

        self.marker_table.marker_double_clicked.connect(
            self.edit_marker
        )

        # Marker movement.
        self.waveforms.marker_move_finished.connect(
            self.on_marker_move_finished
        )

        # Waveform clicks.
        self.waveforms.waveform_clicked.connect(
            self.add_marker
        )

        # Marker table selection.
        self.marker_table.marker_selected.connect(
            self.select_marker_from_table
        )

        self.region_table.region_selected.connect(
            self.select_region_from_table
        )

        self.region_table.start_marker_requested.connect(
            self.select_marker_from_region
        )

        self.region_table.end_marker_requested.connect(
            self.select_marker_from_region
        )

        self.region_table.play_requested.connect(
            self.play_selected_region
        )

        self.region_table.loop_requested.connect(
            self.loop_selected_region
        )

        self.region_table.edit_requested.connect(
            self.edit_region
        )

        self.region_table.delete_requested.connect(
            self.delete_region
        )

        self.region_table.region_double_clicked.connect(
            self.edit_region
        )

        # Playback controls.
        self.play_button.clicked.connect(
            self.play_region
        )

        self.pause_button.clicked.connect(
            self.pause_playback
        )

        self.stop_button.clicked.connect(
            self.stop_playback
        )

        self.loop_checkbox.toggled.connect(
            self.player.set_loop
        )

        self.cents_slider.valueChanged.connect(
            self._sync_cents_spinbox
        )

        self.cents_spin.valueChanged.connect(
            self._sync_cents_slider
        )

        self.playback_target_combo.currentTextChanged.connect(
            self._on_playback_target_changed
        )

        self.playback_shift_spin.valueChanged.connect(
            self._update_playback_result
        )

        self.playback_shift_cents_slider.valueChanged.connect(
            self._sync_playback_shift_cents_spin
        )

        self.playback_shift_cents_spin.valueChanged.connect(
            self._sync_playback_shift_cents_slider
        )

        self.playback_shift_cents_spin.valueChanged.connect(
            self._update_playback_result
        )

        self.playback_speed_slider.valueChanged.connect(
            self._sync_playback_speed_spin
        )

        self.playback_speed_spin.valueChanged.connect(
            self._sync_playback_speed_slider
        )

        self.analyze_button.clicked.connect(
            self._analyze_pitch
        )

        self.apply_tuning_button.clicked.connect(
            self._apply_tuning
        )

        self.save_button.clicked.connect(
            self.save_metadata
        )

        self.save_as_button.clicked.connect(
            self.save_metadata_as
        )

    def _create_position_timer(self) -> None:
        """Create the timer used to synchronize playback state."""

        self.position_timer = QTimer(
            self.window
        )

        self.position_timer.setInterval(
            self.POSITION_TIMER_INTERVAL_MS
        )

        self.position_timer.timeout.connect(
            self.update_position
        )

        self.position_timer.start()

    def _get_sruthi_text(self) -> str:
        """Return the currently selected Western pitch name with octave."""

        return (
            f"{self.sruthi_note_combo.currentText()}"
            f"{self.sruthi_octave_spin.value()}"
        )

    def _sync_cents_spinbox(
        self,
        value: int,
    ) -> None:
        """Keep the cents spin box synchronized with the slider."""

        if self.cents_spin.value() != value:
            self.cents_spin.setValue(value)


    def _sync_cents_slider(
        self,
        value: int,
    ) -> None:
        """Keep the cents slider synchronized with the spin box."""

        if self.cents_slider.value() != value:
            self.cents_slider.setValue(value)

    def _apply_tuning(self) -> None:
        """Apply the current tuning controls to the pitch mapping."""

        sruthi = self._get_sruthi_text()
        cents = float(
            self.cents_spin.value()
        )

        changed = (
            sruthi != self.metadata.sruthi
            or cents != self.metadata.cents
        )

        if not changed:
            return

        self.metadata.sruthi = sruthi
        self.metadata.cents = cents

        if self.pitch_track is None:
            return

        self._remap_pitch()

    def _remap_pitch(self) -> None:
        """Rebuild pitch mapping using the existing analyzed pitch track."""

        if self.pitch_track is None:
            return

        sa_frequency_hz = self._calculate_sa_frequency()

        scale = self.scale_registry.get(
            self.metadata.raga
        )

        pitch_system = PitchSystem(
            sa_frequency_hz=sa_frequency_hz,
            ratios=DEFAULT_RATIOS,
            scale=scale,
        )

        self.pitch_mapper = PitchMapper(
            pitch_system
        )

        self.mapped_pitch_track = (
            self.pitch_mapper.map_track(
                self.pitch_track
            )
        )

        self.pitch_view.set_pitch_track(
            self.mapped_pitch_track,
            self.pitch_mapper,
        )

    def _update_playback_result(self) -> None:
        """Update the resulting pitch displayed in the load panel."""

        self.playback_result_label.setText(
            "Resulting pitch: "
            + self._calculate_playback_result_pitch()
        )

    def _on_playback_target_changed(
        self,
        target: str,
    ) -> None:
        """Convert a target note into semitone/cents playback shift."""

        if target == "Original":
            self.playback_shift_spin.setValue(0)
            self.playback_shift_cents_spin.setValue(0)
            return

        import librosa
        import numpy as np

        source_frequency = (
            self._get_audio_tuning_frequency()
        )

        target_frequency = float(
            librosa.note_to_hz(target)
        )

        shift_cents = (
            1200.0
            * np.log2(
                target_frequency
                / source_frequency
            )
        )

        # Convert to the nearest whole semitone plus
        # a residual cents adjustment.
        semitones = int(
            round(
                shift_cents / 100.0
            )
        )

        residual_cents = int(
            round(
                shift_cents
                - semitones * 100
            )
        )

        # Keep the residual within the control range.
        if residual_cents > 50:
            semitones += 1
            residual_cents -= 100
        elif residual_cents < -50:
            semitones -= 1
            residual_cents += 100

        semitones = max(
            -12,
            min(12, semitones),
        )

        self.playback_shift_spin.setValue(
            semitones
        )

        self.playback_shift_cents_spin.setValue(
            residual_cents
        )

        self._update_playback_result()

    def _sync_playback_shift_cents_spin(
        self,
        value: int,
    ) -> None:
        """Synchronize playback pitch-cents slider and spin box."""

        if self.playback_shift_cents_spin.value() != value:
            self.playback_shift_cents_spin.setValue(
                value
            )

    def _sync_playback_shift_cents_slider(
        self,
        value: int,
    ) -> None:
        """Synchronize playback pitch-cents spin box and slider."""

        if self.playback_shift_cents_slider.value() != value:
            self.playback_shift_cents_slider.setValue(
                value
            )

    def _sync_playback_speed_spin(
        self,
        value: int,
    ) -> None:
        """Synchronize playback-speed slider and spin box."""

        speed = value / 100.0

        if self.playback_speed_spin.value() != speed:
            self.playback_speed_spin.setValue(
                speed
            )


    def _sync_playback_speed_slider(
        self,
        value: float,
    ) -> None:
        """Synchronize playback-speed spin box and slider."""

        slider_value = int(
            round(
                value * 100
            )
        )

        if self.playback_speed_slider.value() != slider_value:
            self.playback_speed_slider.setValue(
                slider_value
            )

    # -----------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------

    def _get_active_region_times(
        self,
    ) -> tuple[float, float]:
        """Resolve the current start and end times of the active region."""

        start_time = self.metadata.get_region_start_seconds(
            self.active_region
        )

        end_time = self.metadata.get_region_end_seconds(
            self.active_region
        )

        return start_time, end_time

    def play_region(self) -> None:
        """Play the currently active region."""

        self.player.set_loop(
            self.loop_checkbox.isChecked()
        )

        self._set_current_time(
            self.player.current_time
        )

        self.marker_table.set_playback_active(
            True
        )
        self.region_table.set_playback_active(
            True
        )

        start_time, end_time = (
            self._get_active_region_times()
        )

        self.player.play(
            start_time=start_time,
            end_time=end_time,
        )

    def pause_playback(self) -> None:
        """Pause audio playback."""

        self.player.pause()

        self.marker_table.set_playback_active(
            False
        )
        self.region_table.set_playback_active(
            False
        )

    def stop_playback(self) -> None:
        """Stop playback and return to the active region start."""

        self.player.stop()

        start_time, _end_time = (
            self._get_active_region_times()
        )

        self._set_current_time(
            start_time
        )

        self.marker_table.set_playback_active(
            False
        )
        self.region_table.set_playback_active(
            False
        )

    def play_near_marker(
        self,
        marker_id: str,
        loop: bool = False,
    ) -> None:
        """Play a temporary ten-second window centered on a marker."""

        marker = self.metadata.markers.get(
            marker_id
        )

        if marker is None:
            return

        marker_time = marker.seconds

        start_time = max(
            0.0,
            marker_time - 5.0,
        )

        end_time = min(
            self.audio.duration,
            marker_time + 5.0,
        )

        if (loop):
            self.loop_checkbox.setChecked(True)
        else:
            self.loop_checkbox.setChecked(False)

        self.marker_table.set_playback_active(
            True
        )
        self.region_table.set_playback_active(
            True
        )

        self.player.play(
            start_time=start_time,
            end_time=end_time,
        )

    def loop_near_marker(
        self,
        marker_id: str,
    ) -> None:
        self.play_near_marker(marker_id, True)

    # -----------------------------------------------------------------
    # Marker handling
    # -----------------------------------------------------------------

    def add_marker(
        self,
        seconds: float,
    ) -> None:
        """Create a new marker from a waveform click."""

        if self.player.is_playing:
            return

        marker_id = generate_marker_id(
            set(self.metadata.markers)
        )

        marker = Marker(
            id=marker_id,
            time=format_seconds_as_time(seconds),
        )

        self.metadata.markers[marker_id] = marker

        self.waveforms.set_markers(
            self.metadata
        )

        self.marker_table.set_markers(
            self.metadata.markers,
            select_marker_id=marker_id,
        )

        self.waveforms.select_marker(
            marker_id
        )

        print(
            f"Created marker: "
            f"{marker.id} at {marker.time}"
        )

    def add_marker_at_current_position(self) -> None:
        """Create a marker at the current player position."""

        if self.player.is_playing:
            return

        seconds = self.player.current_time

        marker_id = generate_marker_id(
            set(self.metadata.markers)
        )

        # Temporary marker. It is not added to metadata
        # until the user accepts the dialog.
        marker = Marker(
            id=marker_id,
            time=format_seconds_as_time(seconds),
        )

        dialog = MarkerDialog(
            marker,
            parent=self.window,
            is_new=True,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.metadata.markers[marker_id] = marker

        self.waveforms.set_markers(
            self.metadata
        )

        self.marker_table.set_markers(
            self.metadata.markers,
            select_marker_id=marker_id,
        )

        self.waveforms.select_marker(
            marker_id
        )

        self._update_marker_delete_state()

        print(
            f"Created marker: "
            f"{marker.id} at {marker.time}"
        )

    def select_marker_from_table(
        self,
        marker_id: str,
    ) -> None:
        """Select a marker in both waveform views."""

        self.waveforms.select_marker(
            marker_id
        )

    def select_marker_from_region(
        self,
        marker_id: str,
    ) -> None:
        """Select a marker referenced by the region table."""

        if marker_id not in self.metadata.markers:
            return

        self.marker_table.select_marker(
            marker_id
        )

        self.waveforms.select_marker(
            marker_id
        )

    def edit_marker(
        self,
        marker_id: str,
    ) -> None:
        """Open the marker editor."""

        marker = self.metadata.markers.get(
            marker_id
        )

        if marker is None:
            return

        dialog = MarkerDialog(
            marker,
            parent=self.window,
        )

        if (
            dialog.exec()
            == QDialog.DialogCode.Accepted
        ):
            self.waveforms.set_markers(
                self.metadata
            )

            self.marker_table.set_markers(
                self.metadata.markers,
                select_marker_id=marker_id,
            )

            self.waveforms.select_marker(
                marker_id
            )

    def delete_marker(
        self,
        marker_id: str,
    ) -> None:
        """Delete a marker that is not referenced by any region."""

        if marker_id not in self.metadata.markers:
            return

        dependent_regions = (
            self.metadata.regions_using_marker(
                marker_id
            )
        )

        if dependent_regions:
            region_ids = ", ".join(
                region.id
                for region in dependent_regions
            )

            print(
                f"Cannot delete marker '{marker_id}': "
                f"it is used by region(s) {region_ids}."
            )
            return

        del self.metadata.markers[marker_id]

        self.waveforms.set_markers(
            self.metadata
        )

        self.marker_table.set_markers(
            self.metadata.markers
        )

    def recenter_graph(
        self,
        marker_id: str,
    ) -> None:
        """Center the waveform and pitch views on a marker."""

        marker = self.metadata.markers.get(
            marker_id
        )

        if marker is None:
            return

        self._recenter_views(
            marker.seconds
        )

    def on_marker_move_finished(
        self,
        marker_id: str,
        seconds: float,
    ) -> None:
        """Commit a completed waveform marker drag."""

        marker = self.metadata.markers.get(
            marker_id
        )

        if marker is None:
            return

        marker.set_time(seconds)

        self.marker_table.set_markers(
            self.metadata.markers,
            select_marker_id=marker_id,
        )

        self.region_table.set_regions(
            self.metadata
        )

    # -----------------------------------------------------------------
    # Region handling
    # -----------------------------------------------------------------

    def select_region_from_table(
        self,
        region_id: str,
    ) -> None:
        """Make a region the active playback region."""

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        self.active_region = region

        start_time, _end_time = (
            self._get_active_region_times()
        )

        if not self.player.is_playing:
            self._set_current_time(
                start_time
            )

    def play_selected_region(
        self,
        region_id: str,
    ) -> None:
        """Play a selected region once."""

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        self.active_region = region

        start_time, end_time = (
            self._get_active_region_times()
        )

        self.loop_checkbox.setChecked(False)

        self._set_current_time(
            start_time
        )

        self.marker_table.set_playback_active(
            True
        )
        self.region_table.set_playback_active(
            True
        )

        self.player.play(
            start_time=start_time,
            end_time=end_time,
        )

    def loop_selected_region(
        self,
        region_id: str,
    ) -> None:
        """Play a selected region repeatedly."""

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        self.active_region = region

        start_time, end_time = (
            self._get_active_region_times()
        )

        self.loop_checkbox.setChecked(True)

        self._set_current_time(
            start_time
        )

        self.marker_table.set_playback_active(
            True
        )
        self.region_table.set_playback_active(
            True
        )

        self.player.play(
            start_time=start_time,
            end_time=end_time,
        )

    def add_region(self) -> None:
        """Create a new region using existing markers."""

        if self.player.is_playing:
            return

        markers = sorted(
            self.metadata.markers.values(),
            key=lambda marker: marker.seconds,
        )

        if len(markers) < 2:
            print(
                "Cannot add region: "
                "at least two markers are required."
            )
            return

        selected_marker_id = (
            self.marker_table.selected_marker_id()
        )

        start_marker_id = None
        end_marker_id = None

        if selected_marker_id is not None:
            for index, marker in enumerate(markers):
                if marker.id == selected_marker_id:
                    start_marker_id = marker.id

                    if index + 1 < len(markers):
                        end_marker_id = markers[
                            index + 1
                        ].id

                    break

        # If there is no selected marker, use the first
        # two chronological markers.
        if start_marker_id is None:
            start_marker_id = markers[0].id
            end_marker_id = markers[1].id

        # A selected marker may be the last marker, in which
        # case there is no marker after it.
        if end_marker_id is None:
            print(
                "Cannot add region: "
                "the selected marker has no later marker."
            )
            return

        region_id = generate_region_id(
            {
                region.id
                for region in self.metadata.regions
            }
        )

        # This Region is temporary until the user accepts
        # the dialog. It is NOT added to metadata yet.
        region = Region(
            id=region_id,
            start=start_marker_id,
            end=end_marker_id,
            label=None,
            description="",
        )

        dialog = RegionDialog(
            region,
            self.metadata,
            parent=self.window,
            is_new=True,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Only now does the new region become part of the metadata.
        self.metadata.regions.append(region)

        self.region_table.set_regions(
            self.metadata,
            select_region_id=region_id,
        )

        self._update_marker_delete_state()

    def edit_region(
        self,
        region_id: str,
    ) -> None:
        """Open the region editor for a normal region."""

        if self.player.is_playing:
            return

        if region_id in self.region_table.RESERVED_REGION_IDS:
            return

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        dialog = RegionDialog(
            region,
            self.metadata,
            parent=self.window,
            is_new=False,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._region_was_edited(
            region_id
        )

    def _region_was_edited(
        self,
        region_id: str,
    ) -> None:
        """Refresh region display after a successful edit."""

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        if self.active_region.id == region_id:
            self.active_region = region

            start_time, end_time = (
                self._get_active_region_times()
            )

            self.region_start = start_time
            self.region_end = end_time

        self.region_table.set_regions(
            self.metadata,
            select_region_id=region_id,
        )

    def delete_region(
        self,
        region_id: str,
    ) -> None:
        """Delete a non-reserved region."""

        if region_id in self.region_table.RESERVED_REGION_IDS:
            return

        region = self.metadata.get_region(
            region_id
        )

        if region is None:
            return

        # Keep at least the required default region.
        if len(self.metadata.regions) == 1:
            return

        was_active = (
            region is self.active_region
        )

        self.metadata.regions.remove(
            region
        )

        if was_active:
            self.active_region = (
                self.metadata.regions[0]
            )

        self.region_table.set_regions(
            self.metadata,
            select_region_id=(
                self.active_region.id
                if self.metadata.regions
                else None
            ),
        )

    # -----------------------------------------------------------------
    # View synchronization
    # -----------------------------------------------------------------

    def _set_current_time(
        self,
        current_time: float,
    ) -> None:
        """Set the playback position in both waveform and pitch views."""

        self.waveforms.set_playback_position(
            current_time
        )

        self.pitch_view.set_current_time(
            current_time
        )

    def _recenter_views(
        self,
        current_time: float,
    ) -> None:
        """Recenter both waveform and pitch views without moving playback."""

        self.waveforms.recenter_on_time(
            current_time
        )

        self.pitch_view.set_current_time(
            current_time
        )


    # -----------------------------------------------------------------
    # Playback state synchronization
    # -----------------------------------------------------------------

    def update_position(self) -> None:
        """
        Synchronize waveform playback position and
        interactive-state flags with the actual player.
        """

        playing = self.player.is_playing

        if playing:
            self._set_current_time(
                self.player.current_time
            )

        self.marker_table.set_playback_active(
            playing
        )

        self.region_table.set_playback_active(
            playing
        )

        self.waveforms.set_playback_active(
            playing
        )

        self.add_marker_button.setEnabled(
            not playing
        )

        self.add_region_button.setEnabled(
            not playing
        )

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    def shutdown(self) -> None:
        """Release timer and audio resources."""

        self.position_timer.stop()
        self.player.close()

    def _update_marker_delete_state(self) -> None:
        """Update which markers may be deleted."""

        protected_ids = set()

        for region in self.metadata.regions:
            protected_ids.add(region.start)
            protected_ids.add(region.end)

        self.marker_table.set_non_deletable_marker_ids(
            protected_ids
        )

    def save_metadata(self) -> None:
        """Save the current metadata to the active YAML file."""

        if self.metadata_path is None:
            self.save_metadata_as()
            return

        MetadataSerializer().save(
            self.metadata,
            str(self.metadata_path),
        )

        print(
            f"Saved metadata: {self.metadata_path}"
        )


    def save_metadata_as(self) -> None:
        """Save the current metadata to a new YAML file."""

        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save Metadata As",
            str(self.metadata_path)
            if self.metadata_path is not None
            else "",
            "YAML Files (*.yaml *.yml)",
        )

        if not path:
            return

        self.metadata_path = Path(path)

        MetadataSerializer().save(
            self.metadata,
            str(self.metadata_path),
        )

        print(
            f"Saved metadata: {self.metadata_path}"
        )

    # -----------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------

    def _print_audio_information(self) -> None:
        """Print the same startup diagnostics as the previous main."""

        print("Audio loaded successfully")
        print("-------------------------")
        print(
            f"Audio file    : "
            f"{self.audio.source_path}"
        )
        print(
            f"Sample rate   : "
            f"{self.audio.sample_rate:,} Hz"
        )
        print(
            f"Samples       : "
            f"{len(self.audio.samples):,}"
        )
        print(
            f"Duration      : "
            f"{self.audio.duration:,.3f} seconds"
        )
        print()
        print("First region")
        print("------------")
        print(
            f"Region        : "
            f"{self.active_region.display_label}"
        )
        print(
            f"Start         : "
            f"{self.region_start:.3f} seconds"
        )
        print(
            f"End           : "
            f"{self.region_end:.3f} seconds"
        )
        print(
            f"Length        : "
            f"{self.region_end - self.region_start:.3f} seconds"
        )

