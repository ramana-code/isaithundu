from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from pitch_mapper import MappedPitchTrack, PitchMapper


class PitchView(pg.PlotWidget):
    """Display a mapped pitch track on an absolute audio timeline.

    Y is cents relative to Sa, so the display axis is linear.
    The playhead stays at the center while the absolute-time data scrolls.
    """

    DEFAULT_WINDOW_SECONDS = 10.0

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        parent=None,
    ):
        super().__init__(parent)

        self.window_seconds = float(window_seconds)
        if self.window_seconds <= 0.0:
            raise ValueError("window_seconds must be positive.")

        self.half_window = self.window_seconds / 2.0
        self.current_time = 0.0

        self.pitch_track: MappedPitchTrack | None = None
        self.pitch_mapper: PitchMapper | None = None

        self._manual_y_range = False
        self._reference_lines: list[pg.InfiniteLine] = []
        self._reference_labels: list[pg.TextItem] = []

        self._configure_plot()

    def _configure_plot(self) -> None:
        """Configure axes, grid, curve, and fixed playhead."""
        self.setBackground("white")

        plot_item = self.getPlotItem()
        plot_item.setLabel("bottom", "")
        plot_item.setLabel("left", "Pitch", units="cents")

        bottom_axis = plot_item.getAxis("bottom")
        bottom_axis.setPen("#777777")
        bottom_axis.setTextPen("#333333")

        left_axis = plot_item.getAxis("left")
        left_axis.setPen("#777777")
        left_axis.setTextPen("#333333")

        plot_item.showGrid(
            x=True,
            y=True,
            alpha=0.15,
        )

        self.setXRange(
            -self.half_window,
            self.half_window,
            padding=0,
        )

        self.pitch_curve = self.plot(
            pen=pg.mkPen(
                color="#1976D2",
                width=1.5,
            ),
            connect="finite",
        )

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

    def set_current_time(self, current_time: float) -> None:
        """Move playback position and scroll the absolute-time window."""
        self.current_time = float(current_time)

        view_start = self.current_time - self.half_window
        view_end = self.current_time + self.half_window

        self.setXRange(
            view_start,
            view_end,
            padding=0,
        )

        self.playhead.setPos(self.current_time)

        self._update_reference_label_positions()

        if not self._manual_y_range:
            self._update_y_range()

    def set_playback_position(self, current_time: float) -> None:
        """Alias used by PlayerController for playback synchronization."""
        self.set_current_time(current_time)

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
        if not np.isfinite(minimum) or not np.isfinite(maximum):
            raise ValueError("Y-axis limits must be finite.")

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
        """Draw the continuous mapped pitch curve."""
        if self.pitch_track is None:
            self.pitch_curve.clear()
            return

        times = self.pitch_track.times
        cents = self.pitch_track.cents_from_sa

        valid = (
            np.isfinite(times)
            & np.isfinite(cents)
        )

        if not np.any(valid):
            self.pitch_curve.clear()
            return

        self.pitch_curve.setData(
            times[valid],
            cents[valid],
        )

    def _clear_reference_items(self) -> None:
        """Remove currently displayed reference lines and labels."""
        plot_item = self.getPlotItem()

        for item in self._reference_lines:
            plot_item.removeItem(item)

        for item in self._reference_labels:
            plot_item.removeItem(item)

        self._reference_lines.clear()
        self._reference_labels.clear()

    def _update_reference_lines(self) -> None:
        """Draw active raga/svara reference lines across three octaves."""
        self._clear_reference_items()

        if self.pitch_mapper is None:
            return

        plot_item = self.getPlotItem()

        for cents, label in self.pitch_mapper.reference_lines(
            min_octave=-1,
            max_octave=1,
        ):
            line = pg.InfiniteLine(
                pos=cents,
                angle=0,
                movable=False,
                pen=pg.mkPen(
                    color="#999999",
                    width=1,
                ),
            )
            plot_item.addItem(line)
            self._reference_lines.append(line)

            text = pg.TextItem(
                text=str(label),
                color="#666666",
                anchor=(1.0, 0.5),
            )
            plot_item.addItem(text)
            self._reference_labels.append(text)

        self._update_reference_label_positions()

    def _update_reference_label_positions(self) -> None:
        """Keep reference-note labels at the right edge of the view."""
        if not self._reference_lines:
            return

        label_x = self.current_time + self.half_window

        for label, line in zip(
            self._reference_labels,
            self._reference_lines,
        ):
            label.setPos(
                label_x,
                line.value(),
            )

    def _update_y_range(self) -> None:
        """Fit Y to valid pitch data in the current visible time window."""
        if self.pitch_track is None:
            return

        times = self.pitch_track.times
        cents = self.pitch_track.cents_from_sa

        view_start = self.current_time - self.half_window
        view_end = self.current_time + self.half_window

        valid = (
            np.isfinite(times)
            & np.isfinite(cents)
            & (times >= view_start)
            & (times <= view_end)
        )

        if not np.any(valid):
            return

        visible_cents = cents[valid]

        minimum = float(np.min(visible_cents))
        maximum = float(np.max(visible_cents))

        if np.isclose(minimum, maximum):
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

    def wheelEvent(self, event) -> None:
        """Treat user Y zooming as switching to manual Y range control."""
        before = self.viewRange()[1]

        super().wheelEvent(event)

        after = self.viewRange()[1]

        if not np.allclose(before, after):
            self._manual_y_range = True

        self._update_reference_label_positions()
