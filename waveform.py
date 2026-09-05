from __future__ import annotations

import numpy as np
import pyqtgraph as pg

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


class WaveformView(pg.PlotWidget):
    """Display an absolute-time portion of an AudioData waveform.

    The X-axis uses absolute audio time.
    The playhead is always fixed at the center of the view.
    """

    def __init__(self, window_seconds: float, parent=None):
        super().__init__(parent)

        self.window_seconds = float(window_seconds)
        self.half_window = self.window_seconds / 2.0

        self.audio: AudioData | None = None
        self.current_time = 0.0
        self.waveform_pyramid: WaveformPyramid | None = None

        # Target visual resolution.
        self.max_display_points = 2500

        self._configure_plot()

    def _configure_plot(self) -> None:
        """Configure the pyqtgraph view."""

        self.setBackground("white")

        plot_item = self.getPlotItem()

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

        view_start = self.current_time - self.half_window
        view_end = self.current_time + self.half_window

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


class SynchronizedWaveforms:
    """Manage the two synchronized waveform views."""

    TOP_WINDOW_SECONDS = 60.0
    BOTTOM_WINDOW_SECONDS = 10.0

    def __init__(self, top_frame, bottom_frame):
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

    def set_current_time(self, current_time: float) -> None:
        """Set the same absolute time in both waveform views."""

        self.top_view.set_current_time(current_time)
        self.bottom_view.set_current_time(current_time)
