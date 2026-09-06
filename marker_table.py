from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from metadata import format_seconds_as_time


class MarkerTable(QTableWidget):
    """Display metadata markers in chronological order."""

    marker_selected = Signal(str)
    marker_double_clicked = Signal(str)

    ID_COLUMN = 0
    TIME_COLUMN = 1
    LABEL_COLUMN = 2

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(
            ["ID", "Time", "Label"]
        )

        # Select complete rows with a single click.
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # Editing will be handled by the future double-click editor.
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        # Compact rows.
        self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)

        header = self.horizontalHeader()

        # Fixed-width ID column.
        header.setSectionResizeMode(
            self.ID_COLUMN,
            QHeaderView.ResizeMode.Fixed,
        )
        self.setColumnWidth(self.ID_COLUMN, 55)

        # Fixed-width Time column.
        header.setSectionResizeMode(
            self.TIME_COLUMN,
            QHeaderView.ResizeMode.Fixed,
        )
        self.setColumnWidth(self.TIME_COLUMN, 125)

        # Label uses the remaining width.
        header.setSectionResizeMode(
            self.LABEL_COLUMN,
            QHeaderView.ResizeMode.Stretch,
        )

        self.itemSelectionChanged.connect(
            self._selection_changed
        )
        self.cellDoubleClicked.connect(
            self._cell_double_clicked
        )

        self._updating = False

    @staticmethod
    def _format_time_for_table(marker) -> str:
        """Format marker time so the MM:SS portion aligns vertically."""

        time_text = format_seconds_as_time(marker.seconds)

        # For times under one hour, canonical formatting omits HH.
        # Add three spaces so the MM portion begins in the same
        # character position as HH:MM:SS.
        if marker.seconds < 3600:
            return "   " + time_text

        return time_text

    def set_markers(
        self,
        markers,
        select_marker_id: str | None = None,
    ) -> None:
        """Refresh the table, sorted chronologically by marker time."""

        self._updating = True

        try:
            self.setRowCount(0)

            if markers is None:
                return

            marker_values = (
                list(markers.values())
                if hasattr(markers, "values")
                else list(markers)
            )

            marker_values.sort(
                key=lambda marker: marker.seconds
            )

            self.setRowCount(len(marker_values))

            for row, marker in enumerate(marker_values):
                marker_id = str(marker.id)

                id_item = QTableWidgetItem(marker_id)

                time_item = QTableWidgetItem(
                    self._format_time_for_table(marker)
                )

                label_item = QTableWidgetItem(
                    getattr(marker, "label", None) or ""
                )

                # Keep the stable marker ID attached to every cell.
                for item in (
                    id_item,
                    time_item,
                    label_item,
                ):
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        marker_id,
                    )

                # Keep numeric time available for future operations.
                time_item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    float(marker.seconds),
                )

                # Monospace font keeps the time characters aligned.
                time_item.setFont(
                    QFontDatabase.systemFont(
                        QFontDatabase.SystemFont.FixedFont
                    )
                )

                time_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                )

                self.setItem(
                    row,
                    self.ID_COLUMN,
                    id_item,
                )

                self.setItem(
                    row,
                    self.TIME_COLUMN,
                    time_item,
                )

                self.setItem(
                    row,
                    self.LABEL_COLUMN,
                    label_item,
                )

        finally:
            self._updating = False

        if select_marker_id is not None:
            self.select_marker(select_marker_id)
        else:
            self.clearSelection()

    def select_marker(
        self,
        marker_id: str | None,
    ) -> None:
        """Select the table row belonging to marker_id."""

        if self._updating:
            return

        self.clearSelection()

        if marker_id is None:
            return

        marker_id = str(marker_id)

        for row in range(self.rowCount()):
            item = self.item(
                row,
                self.ID_COLUMN,
            )

            if item is None:
                continue

            stored_id = item.data(
                Qt.ItemDataRole.UserRole
            )

            if stored_id == marker_id:
                self.selectRow(row)
                return

    def selected_marker_id(self) -> str | None:
        """Return the selected marker ID, if any."""

        selected_rows = (
            self.selectionModel().selectedRows()
        )

        if not selected_rows:
            return None

        row = selected_rows[0].row()

        item = self.item(
            row,
            self.ID_COLUMN,
        )

        if item is None:
            return None

        return str(
            item.data(Qt.ItemDataRole.UserRole)
        )

    def _selection_changed(self) -> None:
        if self._updating:
            return

        marker_id = self.selected_marker_id()

        if marker_id is not None:
            self.marker_selected.emit(marker_id)

    def _cell_double_clicked(
        self,
        row: int,
        column: int,
    ) -> None:
        item = self.item(
            row,
            self.ID_COLUMN,
        )

        if item is None:
            return

        marker_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        if marker_id is not None:
            self.marker_double_clicked.emit(
                str(marker_id)
            )

