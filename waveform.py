from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from audio_loader import AudioData


class WaveformView(pg.PlotWidget):
    """Display an absolute-time portion of an AudioData waveform.

    The X-axis uses absolute audio time.
    The playhead is always fixed at the center of the view.
    """

    def __init__(
        self,
        window_seconds: float,
        parent=None,
    ):
        super().__init__(parent)

        self.window_seconds = float(window_seconds)
        self.half_window = self.window_seconds / 2.0

        self.audio: AudioData | None = None
        self.current_time = 0.0

        # Keep a reasonable number of waveform bins on screen.
        self.max_display_points = 6000

        self._configure_plot()

    def _configure_plot(self) -> None:
        """Configure the pyqtgraph view."""

        # Light/default plot background.
        self.setBackground("white")

        plot_item = self.getPlotItem()

        # ---------------------------------------------------------
        # Axes
        # ---------------------------------------------------------

        # No axis titles.
        plot_item.setLabel("bottom", "")
        plot_item.setLabel("left", "")

        # Amplitude values are not useful for this application.
        plot_item.hideAxis("left")

        # Keep the absolute-time X-axis values.
        bottom_axis = plot_item.getAxis("bottom")
        bottom_axis.setPen("#777777")
        bottom_axis.setTextPen("#333333")

        # ---------------------------------------------------------
        # Grid
        # ---------------------------------------------------------

        plot_item.showGrid(
            x=True,
            y=False,
            alpha=0.15,
        )

        # ---------------------------------------------------------
        # Y range
        # ---------------------------------------------------------

        self.setYRange(
            -1.05,
            1.05,
            padding=0,
        )

        # ---------------------------------------------------------
        # Initial X range
        # ---------------------------------------------------------

        self.setXRange(
            -self.half_window,
            self.half_window,
            padding=0,
        )

        # ---------------------------------------------------------
        # Waveform
        # ---------------------------------------------------------

        self.waveform_curve = self.plot(
            pen=pg.mkPen(
                color="#1976D2",
                width=1,
            ),
        )

        # ---------------------------------------------------------
        # Fixed playhead
        # ---------------------------------------------------------

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
        """Set the audio source displayed by this waveform."""

        self.audio = audio
        self.current_time = 0.0

        self.update_waveform()

    def set_current_time(self, current_time: float) -> None:
        """Set the absolute audio position at the center of the view."""

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
        """Update the waveform around the current absolute time."""

        if self.audio is None:
            self.waveform_curve.clear()
            return

        # ---------------------------------------------------------
        # Absolute visible time range
        # ---------------------------------------------------------

        view_start = self.current_time - self.half_window
        view_end = self.current_time + self.half_window

        # Actual audio exists only between 0 and duration.
        audio_start = max(
            0.0,
            view_start,
        )

        audio_end = min(
            self.audio.duration,
            view_end,
        )

        # No audio exists inside the visible window.
        if audio_start >= audio_end:
            self.waveform_curve.clear()

            self.setXRange(
                view_start,
                view_end,
                padding=0,
            )

            return

        # ---------------------------------------------------------
        # Convert visible audio range to samples
        # ---------------------------------------------------------

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
            return

        samples = self.audio.samples[
            start_sample:end_sample
        ]

        # ---------------------------------------------------------
        # Downsample into min/max waveform bins
        # ---------------------------------------------------------

        num_bins = min(
            self.max_display_points,
            max(1000, self.width() * 4),
        )

        num_bins = min(
            num_bins,
            len(samples),
        )

        if num_bins <= 0:
            self.waveform_curve.clear()
            return

        # Divide samples into approximately equal bins.
        edges = np.linspace(
            0,
            len(samples),
            num_bins + 1,
            dtype=np.int64,
        )

        x_values = []
        y_values = []

        for i in range(num_bins):
            bin_start = edges[i]
            bin_end = edges[i + 1]

            if bin_end <= bin_start:
                continue

            chunk = samples[bin_start:bin_end]

            minimum = np.min(chunk)
            maximum = np.max(chunk)

            # Absolute time corresponding to this bin.
            bin_start_time = (
                audio_start
                + (bin_start / sample_rate)
            )

            bin_end_time = (
                audio_start
                + (bin_end / sample_rate)
            )

            x_values.extend([
                bin_start_time,
                bin_end_time,
            ])

            y_values.extend([
                minimum,
                maximum,
            ])

        # ---------------------------------------------------------
        # Draw waveform
        # ---------------------------------------------------------

        self.waveform_curve.setData(
            np.asarray(x_values),
            np.asarray(y_values),
        )

        # ---------------------------------------------------------
        # Keep absolute-time view centered on current_time
        # ---------------------------------------------------------

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

    def __init__(
        self,
        top_frame,
        bottom_frame,
    ):
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