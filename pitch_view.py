from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg

from pitch_mapper import MappedPitchTrack, PitchMapper

class TimeAxisItem(pg.AxisItem):
    """Display absolute audio time as MM:SS or HH:MM:SS."""

    def tickStrings(
        self,
        values,
        scale,
        spacing,
    ):
        labels = []

        for value in values:
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

class PitchView(pg.PlotWidget):
    """Display mapped pitch on an absolute audio timeline.

    The underlying Y coordinate is cents relative to Sa. All plot axes are
    hidden so the plotting area can align horizontally with the waveform.
    Svara names are drawn directly inside the plot at their reference lines.
    The playback playhead remains fixed at the center of the visible window.
    """

    DEFAULT_WINDOW_SECONDS = 20.0

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        parent=None,
    ):
        bottom_axis = TimeAxisItem(
            orientation="bottom"
        )

        super().__init__(
            parent=parent,
            axisItems={
                "bottom": bottom_axis,
            },
        )

        self.window_seconds = float(window_seconds)

        if self.window_seconds <= 0.0:
            raise ValueError(
                "window_seconds must be positive."
            )

        self.half_window = (
            self.window_seconds / 2.0
        )

        self.current_time = 0.0

        self.pitch_track: MappedPitchTrack | None = None
        self.pitch_mapper: PitchMapper | None = None

        self._manual_y_range = False

        self._reference_lines: list[
            pg.InfiniteLine
        ] = []

        self._reference_labels_left: list[
            pg.TextItem
        ] = []

        self._reference_labels_right: list[
            pg.TextItem
        ] = []

        self._configure_plot()

    def _configure_plot(self) -> None:
        """Configure the pitch plot and fixed playhead."""

        self.setBackground("white")

        plot_item = self.getPlotItem()

        # Hide every plot axis. The pitch plot should use the same full
        # horizontal plotting area as the waveform.
        plot_item.hideAxis("left")
        plot_item.hideAxis("right")
        plot_item.showAxis("bottom")

        # No background grid.
        plot_item.showGrid(
            x=False,
            y=False,
        )

        plot_item.setLabel(
            "bottom",
            "",
        )

        bottom_axis = plot_item.getAxis("bottom")
        bottom_axis.setPen("#777777")
        bottom_axis.setTextPen("#333333")

        self.setXRange(
            -self.half_window,
            self.half_window,
            padding=0,
        )

        # Use a distinct, thicker color from the waveform.
        self.pitch_curve = self.plot(
            pen=pg.mkPen(
                color="#C62828",
                width=2.5,
            ),
            connect="finite",
        )

        # Fixed playback-position line.
        self.playhead = pg.InfiniteLine(
            pos=self.current_time,
            angle=90,
            movable=False,
            pen=pg.mkPen(
                color="#F57C00",
                width=2,
            ),
        )

        self.addItem(
            self.playhead
        )

    def set_pitch_track(
        self,
        pitch_track: MappedPitchTrack | None,
        pitch_mapper: PitchMapper | None = None,
    ) -> None:
        """Set mapped pitch data and the musical reference system."""

        self.pitch_track = pitch_track
        self.pitch_mapper = pitch_mapper

        self._manual_y_range = False

        self._update_pitch_curve()
        self._update_reference_lines()
        self._update_y_range()

    def set_current_time(
        self,
        current_time: float,
    ) -> None:
        """Set the absolute time at the center of the visible window."""

        self.current_time = float(
            current_time
        )

        view_start = (
            self.current_time
            - self.half_window
        )

        view_end = (
            self.current_time
            + self.half_window
        )

        self.setXRange(
            view_start,
            view_end,
            padding=0,
        )

        self.playhead.setPos(
            self.current_time
        )
        self._update_reference_label_positions()

        if not self._manual_y_range:
            self._update_y_range()

    def set_playback_position(
        self,
        current_time: float,
    ) -> None:
        """Alias used by PlayerController."""

        self.set_current_time(
            current_time
        )

    def auto_range_y(self) -> None:
        """Resume automatic Y-axis scaling."""

        self._manual_y_range = False
        self._update_y_range()

    def set_manual_y_range(
        self,
        minimum: float,
        maximum: float,
    ) -> None:
        """Set a fixed Y-axis range in cents."""

        if not (
            np.isfinite(minimum)
            and np.isfinite(maximum)
        ):
            raise ValueError(
                "Y-axis limits must be finite."
            )

        if maximum <= minimum:
            raise ValueError(
                "Maximum Y value must be greater than minimum."
            )

        self._manual_y_range = True

        self.setYRange(
            float(minimum),
            float(maximum),
            padding=0,
        )

    def _update_pitch_curve(self) -> None:
        """Draw the pitch curve while preserving missing-data gaps."""

        if self.pitch_track is None:
            self.pitch_curve.clear()
            return

        times = self.pitch_track.times
        cents = self.pitch_track.cents_from_sa

        valid_time = np.isfinite(times)

        if not np.any(valid_time):
            self.pitch_curve.clear()
            return

        # Keep NaNs in cents. With connect="finite", PyQtGraph leaves a gap
        # wherever the pitch value is missing.
        self.pitch_curve.setData(
            times[valid_time],
            cents[valid_time],
        )

    def _clear_reference_items(self) -> None:
        """Remove reference lines and labels."""

        plot_item = self.getPlotItem()

        for item in self._reference_lines:
            plot_item.removeItem(item)

        for item in self._reference_labels_left:
            plot_item.removeItem(item)

        for item in self._reference_labels_right:
            plot_item.removeItem(item)

        self._reference_lines.clear()
        self._reference_labels_left.clear()
        self._reference_labels_right.clear()

    def _update_reference_lines(self) -> None:
        """Draw active raga reference lines across three octaves."""

        self._clear_reference_items()

        if self.pitch_mapper is None:
            return

        plot_item = self.getPlotItem()

        reference_notes = (
            self.pitch_mapper.pitch_system.reference_notes(
                min_octave=-1,
                max_octave=1,
            )
        )

        left_label_x = (
            self.current_time
            - self.half_window
            + 0.15
        )

        right_label_x = (
            self.current_time
            + self.half_window
            - 0.15
        )

        for cents, position, label, octave in reference_notes:
            if position == 0:
                line_pen = pg.mkPen(
                    color="#555555",
                    width=2,
                )
            else:
                line_pen = pg.mkPen(
                    color="#999999",
                    width=1,
                )

            line = pg.InfiniteLine(
                pos=cents,
                angle=0,
                movable=False,
                pen=line_pen,
            )

            plot_item.addItem(line)

            self._reference_lines.append(line)

            left_text = pg.TextItem(
                text=str(label),
                color="#666666",
                anchor=(0.0, 0.5),
            )

            right_text = pg.TextItem(
                text=str(label),
                color="#666666",
                anchor=(1.0, 0.5),
            )

            plot_item.addItem(left_text)
            plot_item.addItem(right_text)

            left_text.setPos(
                left_label_x,
                cents,
            )

            right_text.setPos(
                right_label_x,
                cents,
            )

            self._reference_labels_left.append( left_text )
            self._reference_labels_right.append( right_text )

    def _update_reference_label_positions(self) -> None:
        """Keep Svara labels at fixed insets inside both plot edges."""

        if not self._reference_labels_left:
            return

        left_label_x = (
            self.current_time
            - self.half_window
            + 0.15
        )

        right_label_x = (
            self.current_time
            + self.half_window
            - 0.15
        )

        for label in self._reference_labels_left:
            position = label.pos()

            label.setPos(
                left_label_x,
                position.y(),
            )

        for label in self._reference_labels_right:
            position = label.pos()

            label.setPos(
                right_label_x,
                position.y(),
            )

    def _update_y_range(self) -> None:
        """Fit Y to valid pitch data in the current visible time window."""

        if self.pitch_track is None:
            return

        times = self.pitch_track.times
        cents = self.pitch_track.cents_from_sa

        view_start = (
            self.current_time
            - self.half_window
        )

        view_end = (
            self.current_time
            + self.half_window
        )

        valid = (
            np.isfinite(times)
            & np.isfinite(cents)
            & (times >= view_start)
            & (times <= view_end)
        )

        if not np.any(valid):
            return

        visible_cents = cents[valid]

        minimum = float(
            np.min(visible_cents)
        )

        maximum = float(
            np.max(visible_cents)
        )

        if np.isclose(
            minimum,
            maximum,
        ):
            padding = 100.0
        else:
            padding = max(
                50.0,
                0.10 * (maximum - minimum),
            )

        self.setYRange(
            minimum - padding,
            maximum + padding,
            padding=0,
        )

    def clear(self) -> None:
        """Clear pitch data and musical reference lines."""

        self.pitch_track = None
        self.pitch_mapper = None

        self.pitch_curve.clear()

        self._clear_reference_items()

        self._manual_y_range = False
