from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont

from audio_loader import AudioData


class WaveformPyramid:
    """Precomputed multiresolution min/max waveform envelopes."""

    def __init__(self, audio: AudioData, max_display_points: int = 2500):
        self.audio = audio
        self.max_display_points = int(max_display_points)
        self.levels: list[tuple[int, np.ndarray, np.ndarray]] = []
        self._build()

    def _build(self) -> None:
        samples = self.audio.samples
        if len(samples) == 0:
            return

        block_size = 2

        while True:
            minimums, maximums = self._make_level(samples, block_size)
            self.levels.append((block_size, minimums, maximums))

            if len(minimums) <= self.max_display_points:
                break

            block_size *= 2

    @staticmethod
    def _make_level(
        samples: np.ndarray,
        block_size: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        count = len(samples)
        full_count = count // block_size
        remainder = count % block_size

        if full_count:
            full = samples[:full_count * block_size].reshape(
                full_count,
                block_size,
            )
            minimums = np.min(full, axis=1)
            maximums = np.max(full, axis=1)
        else:
            minimums = np.empty(0, dtype=samples.dtype)
            maximums = np.empty(0, dtype=samples.dtype)

        if remainder:
            tail = samples[full_count * block_size:]
            minimums = np.concatenate(
                (minimums, np.asarray([np.min(tail)], dtype=samples.dtype))
            )
            maximums = np.concatenate(
                (maximums, np.asarray([np.max(tail)], dtype=samples.dtype))
            )

        return minimums, maximums

    def select_level(
        self,
        visible_samples: int,
        target_bins: int,
    ) -> tuple[int, np.ndarray, np.ndarray]:
        if not self.levels:
            raise RuntimeError("Waveform pyramid contains no levels.")

        target_bins = max(1, int(target_bins))
        desired_block = max(
            1,
            int(np.ceil(visible_samples / target_bins)),
        )

        for level in self.levels:
            if level[0] >= desired_block:
                return level

        return self.levels[-1]

    def get_visible_envelope(
        self,
        start_sample: int,
        end_sample: int,
        target_bins: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        start_sample = max(0, int(start_sample))
        end_sample = min(len(self.audio.samples), int(end_sample))

        if end_sample <= start_sample:
            empty = np.empty(0, dtype=np.float64)
            return empty, empty, empty

        visible_samples = end_sample - start_sample
        block_size, minimums, maximums = self.select_level(
            visible_samples,
            target_bins,
        )

        first_bin = start_sample // block_size
        last_bin = (end_sample - 1) // block_size

        minimums = minimums[first_bin:last_bin + 1]
        maximums = maximums[first_bin:last_bin + 1]

        # Correct edge bins when the visible range cuts through a block.
        if minimums.size:
            if start_sample % block_size:
                block_end = min(
                    (first_bin + 1) * block_size,
                    end_sample,
                )
                chunk = self.audio.samples[start_sample:block_end]
                if len(chunk):
                    minimums = minimums.copy()
                    maximums = maximums.copy()
                    minimums[0] = np.min(chunk)
                    maximums[0] = np.max(chunk)

            last_bin_start = last_bin * block_size
            if end_sample < last_bin_start + block_size:
                chunk = self.audio.samples[last_bin_start:end_sample]
                if len(chunk):
                    minimums = minimums.copy()
                    maximums = maximums.copy()
                    minimums[-1] = np.min(chunk)
                    maximums[-1] = np.max(chunk)

        bin_starts = (
            np.arange(first_bin, first_bin + len(minimums), dtype=np.float64)
            * block_size
        )
        bin_ends = np.minimum(
            bin_starts + block_size,
            len(self.audio.samples),
        )

        envelope = np.column_stack((minimums, maximums))
        return bin_starts, bin_ends, envelope

class TimeAxisItem(pg.AxisItem):
    """Display absolute audio time as MM:SS or HH:MM:SS."""

    def tickStrings(self, values, scale, spacing):
        labels = []

        for value in values:
            # The waveform can show blank space before the beginning
            # or after the end of the audio. Don't display negative time.
            if value < 0:
                labels.append("")
                continue

            total_seconds = int(round(value))

            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            if hours > 0:
                labels.append(
                    f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                )
            else:
                labels.append(
                    f"{minutes:02d}:{seconds:02d}"
                )

        return labels

class WaveformView(pg.PlotWidget):
    """Display an absolute-time portion of an AudioData waveform.

    The X-axis uses absolute audio time.
    The playhead is always fixed at the center of the view.
    """

    clicked = Signal(float)
    marker_moved = Signal(str, float)
    marker_move_finished = Signal(str, float)

    def __init__(self, window_seconds: float, parent=None):
        super().__init__(parent)

        self.window_seconds = float(window_seconds)
        self.half_window = self.window_seconds / 2.0

        self.audio: AudioData | None = None
        self.current_time = 0.0
        self.view_center_time = 0.0
        self.waveform_pyramid: WaveformPyramid | None = None

        # Marker graphics keyed by stable marker ID.
        self.marker_items: dict[str, tuple[pg.InfiniteLine, pg.TextItem]] = {}
        self.selected_marker_id: str | None = None
        self._dragging_marker_id: str | None = None
        self.marker_drag_tolerance_pixels = 6
        self._playback_active = False

        # Target visual resolution.
        self.max_display_points = 2500

        self._configure_plot()

    def _configure_plot(self) -> None:
        """Configure the pyqtgraph view."""

        self.setBackground("white")

        plot_item = self.getPlotItem()

        plot_item.setMouseEnabled(
            x=False,
            y=False,
        )

        plot_item.setAxisItems(
            {
                "bottom": TimeAxisItem(
                    orientation="bottom"
                )
            }
        )
        plot_item.setLabel("bottom", "")
        plot_item.setLabel("left", "")
        plot_item.hideAxis("left")

        bottom_axis = plot_item.getAxis("bottom")
        bottom_axis.setPen("#777777")
        bottom_axis.setTextPen("#333333")

        plot_item.showGrid(
            x=True,
            y=False,
            alpha=0.15,
        )

        self.setYRange(
            -1.05,
            1.05,
            padding=0,
        )

        self.setXRange(
            -self.half_window,
            self.half_window,
            padding=0,
        )

        self.waveform_curve = self.plot(
            pen=pg.mkPen(
                color="#1976D2",
                width=1,
            )
        )

        # Fixed playhead: absolute current_time.
        self.playhead = pg.InfiniteLine(
            pos=self.current_time,
            angle=90,
            movable=False,
            pen=pg.mkPen(
                color="#F57C00",
                width=2,
            ),
        )

        self.addItem(self.playhead)

    def set_markers(self, markers) -> None:
        """Display metadata markers using absolute audio time."""
        self.clear_markers()

        if markers is None:
            return

        marker_values = markers.values() if hasattr(markers, "values") else markers

        for marker in marker_values:
            marker_id = str(marker.id)
            marker_time = float(marker.seconds)

            marker_line = pg.InfiniteLine(
                pos=marker_time,
                angle=90,
                movable=False,
                pen=pg.mkPen(
                    color="#7B1FA2",
                    width=1.5,
                ),
            )

            label_text = getattr(marker, "label", None) or marker_id
            label = pg.TextItem(
                text=marker_id,
                color="#777777",
                anchor=(0, 1),
            )

            label_font = QFont()
            label_font.setPointSize(8)
            label.setFont(label_font)
            label.setPos(marker_time, 0.70)

            self.addItem(marker_line)
            self.addItem(label)

            self.marker_items[marker_id] = (marker_line, label)

    def select_marker(self, marker_id: str | None) -> None:
        """Visually select one marker in this waveform."""
        if self.selected_marker_id in self.marker_items:
            old_line, _old_label = self.marker_items[self.selected_marker_id]
            old_line.setPen(
                pg.mkPen(
                    color="#7B1FA2",
                    width=1.5,
                )
            )

        self.selected_marker_id = (
            str(marker_id) if marker_id is not None else None
        )

        if self.selected_marker_id in self.marker_items:
            line, _label = self.marker_items[self.selected_marker_id]
            line.setPen(
                pg.mkPen(
                    color="#E91E63",
                    width=2.5,
                )
            )

    def set_marker_time(
        self,
        marker_id: str,
        seconds: float,
    ) -> None:
        """Move one marker graphic without rebuilding all markers."""

        marker_item = self.marker_items.get(
            str(marker_id)
        )

        if marker_item is None:
            return

        marker_line, label = marker_item

        seconds = float(seconds)

        marker_line.setValue(seconds)
        label.setPos(seconds, 0.70)

    def clear_markers(self) -> None:
        """Remove all marker lines and labels."""
        for marker_line, label in self.marker_items.values():
            self.removeItem(marker_line)
            self.removeItem(label)

        self.marker_items.clear()
        self.selected_marker_id = None

    def set_audio(self, audio: AudioData) -> None:
        """Set audio and build the waveform pyramid once."""

        self.audio = audio
        self.current_time = 0.0

        self.waveform_pyramid = WaveformPyramid(
            audio,
            max_display_points=self.max_display_points,
        )

        self.update_waveform()

    def set_current_time(self, current_time: float) -> None:
        """Set absolute audio position at the center of the view."""

        if self.audio is None:
            return

        self.current_time = max(
            0.0,
            min(
                float(current_time),
                self.audio.duration,
            ),
        )

        self.update_waveform()

    def update_waveform(self) -> None:
        """Display the precomputed envelope around current_time."""

        if self.audio is None or self.waveform_pyramid is None:
            self.waveform_curve.clear()
            return

        view_start = (
            self.view_center_time - self.half_window
        )
        view_end = (
            self.view_center_time + self.half_window
        )

        audio_start = max(0.0, view_start)
        audio_end = min(self.audio.duration, view_end)

        if audio_start >= audio_end:
            self.waveform_curve.clear()
            self.setXRange(view_start, view_end, padding=0)
            self.playhead.setPos(self.current_time)
            return

        sample_rate = self.audio.sample_rate

        start_sample = max(
            0,
            int(np.floor(audio_start * sample_rate)),
        )
        end_sample = min(
            len(self.audio.samples),
            int(np.ceil(audio_end * sample_rate)),
        )

        if end_sample <= start_sample:
            self.waveform_curve.clear()
            self.setXRange(view_start, view_end, padding=0)
            self.playhead.setPos(self.current_time)
            return

        target_bins = min(
            self.max_display_points,
            max(500, self.width() * 2),
        )

        bin_starts, bin_ends, envelope = (
            self.waveform_pyramid.get_visible_envelope(
                start_sample,
                end_sample,
                target_bins,
            )
        )

        if len(envelope) == 0:
            self.waveform_curve.clear()
        else:
            x_starts = bin_starts / sample_rate
            x_ends = bin_ends / sample_rate

            # Use the center of each bin for a vertical min/max segment.
            x_values = np.repeat(
                (x_starts + x_ends) / 2.0,
                2,
            )
            y_values = envelope.reshape(-1)

            self.waveform_curve.setData(
                x_values,
                y_values,
            )

        # Keep the absolute-time window centered.
        self.setXRange(
            view_start,
            view_end,
            padding=0,
        )

        # Keep the playhead at the actual absolute audio position.
        self.playhead.setPos(self.current_time)

    def mousePressEvent(self, event) -> None:
        """Handle marker dragging or new-marker creation."""

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.audio is not None
        ):
            mouse_pos = event.position().toPoint()

            # ---------------------------------------------------------
            # Selected marker gets first priority: begin dragging.
            # ---------------------------------------------------------

            if self._selected_marker_near_mouse(mouse_pos):
                self._dragging_marker_id = (
                    self.selected_marker_id
                )

                event.accept()
                return

            # ---------------------------------------------------------
            # Any other existing marker blocks marker creation.
            # ---------------------------------------------------------

            if self._marker_near_mouse(mouse_pos):
                event.accept()
                return

            # ---------------------------------------------------------
            # Otherwise this is a normal marker-creation click.
            # ---------------------------------------------------------

            scene_pos = self.mapToScene(mouse_pos)

            view_pos = (
                self.getPlotItem()
                .vb
                .mapSceneToView(scene_pos)
            )

            click_time = max(
                0.0,
                min(
                    float(view_pos.x()),
                    self.audio.duration,
                ),
            )

            self.clicked.emit(click_time)

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Move the selected marker during a drag."""

        if (
            self._dragging_marker_id is not None
            and self.audio is not None
        ):
            scene_pos = self.mapToScene(
                event.position().toPoint()
            )

            view_pos = (
                self.getPlotItem()
                .vb
                .mapSceneToView(scene_pos)
            )

            new_time = max(
                0.0,
                min(
                    float(view_pos.x()),
                    self.audio.duration,
                ),
            )

            marker_id = self._dragging_marker_id

            self.set_marker_time(
                marker_id,
                new_time,
            )

            self.marker_moved.emit(
                marker_id,
                new_time,
            )

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish a marker drag."""

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._dragging_marker_id is not None
            and self.audio is not None
        ):
            marker_id = self._dragging_marker_id

            marker_item = self.marker_items.get(
                marker_id
            )

            if marker_item is not None:
                marker_line, _label = marker_item

                final_time = max(
                    0.0,
                    min(
                        float(marker_line.value()),
                        self.audio.duration,
                    ),
                )

                self.marker_move_finished.emit(
                    marker_id,
                    final_time,
                )

            self._dragging_marker_id = None

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def set_playback_position(self, current_time: float) -> None:
        """Set playback position and center the waveform on it."""

        if self.audio is None:
            return

        self.current_time = max(
            0.0,
            min(
                float(current_time),
                self.audio.duration,
            ),
        )

        self.view_center_time = self.current_time

        self.update_waveform()

    def recenter_on_time(self, seconds: float) -> None:
        """Move only the waveform view center.

        The audio playback position/playhead is not changed.
        """

        if self.audio is None:
            return

        self.view_center_time = max(
            0.0,
            min(
                float(seconds),
                self.audio.duration,
            ),
        )

        self.update_waveform()

    def set_playback_active(self, active: bool) -> None:
        """Enable or disable marker dragging during playback."""
        self._playback_active = bool(active)

    def _selected_marker_near_mouse(
        self,
        mouse_pos,
    ) -> bool:
        """Return True when the mouse is near the selected marker."""

        if self._playback_active:
            return False

        marker_id = self.selected_marker_id

        if marker_id is None:
            return False

        if marker_id in {"m000", "m999"}:
            return False

        marker_item = self.marker_items.get(marker_id)

        if marker_item is None:
            return False

        marker_line, _label = marker_item
        marker_time = float(marker_line.value())

        scene_pos = self.getPlotItem().vb.mapViewToScene(
            pg.Point(marker_time, 0)
        )

        local_pos = self.mapFromScene(scene_pos)

        return (
            abs(
                local_pos.x() - mouse_pos.x()
            )
            <= self.marker_drag_tolerance_pixels
        )

    def _marker_near_mouse(
    self,
    mouse_pos,
    ) -> bool:
        """Return True when the mouse is within the marker hit tolerance."""

        tolerance = self.marker_drag_tolerance_pixels

        for marker_line, _label in self.marker_items.values():
            marker_time = float(marker_line.value())

            scene_pos = (
                self.getPlotItem()
                .vb
                .mapViewToScene(
                    pg.Point(marker_time, 0)
                )
            )

            local_pos = self.mapFromScene(scene_pos)

            if (
                abs(
                    float(local_pos.x())
                    - mouse_pos.x()
                )
                <= tolerance
            ):
                return True

        return False

class SynchronizedWaveforms(QObject):
    """Manage the two synchronized waveform views."""

    TOP_WINDOW_SECONDS = 60.0
    BOTTOM_WINDOW_SECONDS = 10.0

    waveform_clicked = Signal(float)
    marker_moved = Signal(str, float)
    marker_move_finished = Signal(str, float)

    def __init__(self, top_frame, bottom_frame):
        super().__init__()

        self.top_view = WaveformView(
            self.TOP_WINDOW_SECONDS,
            top_frame,
        )

        self.bottom_view = WaveformView(
            self.BOTTOM_WINDOW_SECONDS,
            bottom_frame,
        )

        self._install_view(
            top_frame,
            self.top_view,
        )

        self._install_view(
            bottom_frame,
            self.bottom_view,
        )
        self.top_view.clicked.connect(self._waveform_clicked)
        self.bottom_view.clicked.connect(self._waveform_clicked)

        self.top_view.marker_moved.connect(
            self._marker_moved
        )

        self.bottom_view.marker_moved.connect(
            self._marker_moved
        )

        self.top_view.marker_move_finished.connect(
            self._marker_move_finished
        )

        self.bottom_view.marker_move_finished.connect(
            self._marker_move_finished
        )

    @staticmethod
    def _install_view(frame, view) -> None:
        """Put a waveform view into a Qt Designer frame."""

        layout = frame.layout()

        if layout is None:
            from PySide6.QtWidgets import QVBoxLayout

            layout = QVBoxLayout(frame)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

        layout.addWidget(view)

    def set_audio(self, audio: AudioData) -> None:
        """Display the same audio in both waveform views."""

        self.top_view.set_audio(audio)
        self.bottom_view.set_audio(audio)

    def set_markers(self, metadata) -> None:
        """Display all metadata markers in both synchronized views."""
        markers = getattr(metadata, "markers", None)

        self.top_view.set_markers(markers)
        self.bottom_view.set_markers(markers)

    def select_marker(self, marker_id: str | None) -> None:
        """Select the same marker in both waveform views."""
        self.top_view.select_marker(marker_id)
        self.bottom_view.select_marker(marker_id)

    def set_current_time(self, current_time: float) -> None:
        """Set the same absolute time in both waveform views."""

        self.top_view.set_current_time(current_time)
        self.bottom_view.set_current_time(current_time)

    def _waveform_clicked(self, absolute_time: float) -> None:
        """Handle a click from either synchronized waveform."""
        self.waveform_clicked.emit(absolute_time)

    def set_playback_position(
        self,
        current_time: float,
    ) -> None:
        """Move playback position and center both waveforms."""

        self.top_view.set_playback_position(current_time)
        self.bottom_view.set_playback_position(current_time)


    def recenter_on_time(self, seconds: float) -> None:
        """Recenter both waveform views without moving playback."""

        self.top_view.recenter_on_time(seconds)
        self.bottom_view.recenter_on_time(seconds)

    def _marker_moved(
        self,
        marker_id: str,
        seconds: float,
    ) -> None:
        """Keep both waveform views synchronized."""

        self.top_view.set_marker_time(
            marker_id,
            seconds,
        )

        self.bottom_view.set_marker_time(
            marker_id,
            seconds,
        )

        self.marker_moved.emit(
            marker_id,
            seconds,
        )


    def _marker_move_finished(
        self,
        marker_id: str,
        seconds: float,
    ) -> None:
        """Report completion of a marker drag."""

        self.marker_move_finished.emit(
            marker_id,
            seconds,
        )

    def set_playback_active(self, active: bool) -> None:
        """Enable or disable marker dragging in both views."""

        self.top_view.set_playback_active(active)
        self.bottom_view.set_playback_active(active)
