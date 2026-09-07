from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
)

from metadata import format_seconds_as_time


class MarkerTable(QTableWidget):
    """Display and select metadata markers."""

    marker_selected = Signal(str)
    marker_double_clicked = Signal(str)

    # Context-menu actions.
    recenter_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    play_near_marker_requested = Signal(str)
    loop_near_marker_requested = Signal(str)

    ID_COLUMN = 0
    TIME_COLUMN = 1
    LABEL_COLUMN = 2

    RESERVED_MARKER_IDS = {"m000", "m999"}

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(3)
        self._playback_active = False
        self.setHorizontalHeaderLabels(
            ["ID", "Time", "Label"]
        )
        self._non_deletable_marker_ids = set()

        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        # Compact rows.
        self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().setVisible(False)

        # Do not use horizontal separator lines.
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

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

        # Label gets the remaining space.
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

        self.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.customContextMenuRequested.connect(
            self._show_context_menu
        )

        self._updating = False

    @staticmethod
    def _format_time_for_table(marker) -> str:
        """Format time so the MM:SS portion aligns vertically."""

        time_text = format_seconds_as_time(marker.seconds)

        # For times under one hour, HH is omitted by the canonical
        # formatter. Add three spaces so MM aligns with HH:MM:SS.
        if marker.seconds < 3600:
            return "   " + time_text

        return time_text

    def set_markers(
        self,
        markers,
        select_marker_id: str | None = None,
    ) -> None:
        """Refresh the table, sorted chronologically."""

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

                for item in (
                    id_item,
                    time_item,
                    label_item,
                ):
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        marker_id,
                    )

                # Keep numeric seconds available for future operations.
                time_item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    float(marker.seconds),
                )

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
        """Select the row belonging to marker_id."""

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
        # Editing is not allowed during playback.
        if self._playback_active:
            return

        item = self.item(
            row,
            self.ID_COLUMN,
        )

        if item is None:
            return

        marker_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        if marker_id is None:
            return

        marker_id = str(marker_id)

        # Reserved markers cannot be edited.
        if marker_id in self.RESERVED_MARKER_IDS:
            return

        self.marker_double_clicked.emit(marker_id)

    def _show_context_menu(self, position) -> None:
        """Show the marker context menu for the row under the cursor."""

        item = self.itemAt(position)

        if item is None:
            return

        # Right-click selects the row first.
        self.selectRow(item.row())

        marker_id = self.selected_marker_id()

        if marker_id is None:
            return

        menu = QMenu(self)

        play_near_marker_action = menu.addAction(
            "Play near marker"
        )
        play_near_marker_action.setEnabled(
            not self._playback_active
        )

        loop_near_marker_action = menu.addAction(
            "Loop near marker"
        )
        loop_near_marker_action.setEnabled(
            not self._playback_active
        )

        recenter_action = menu.addAction(
            "Recenter graph"
        )
        recenter_action.setEnabled(
            not self._playback_active
        )

        edit_action = menu.addAction(
            "Edit marker"
        )
        edit_action.setEnabled(
            marker_id not in self.RESERVED_MARKER_IDS
            and not self._playback_active
        )

        copy_id_action = menu.addAction(
            "Copy marker ID"
        )

        copy_time_action = menu.addAction(
            "Copy marker time"
        )

        menu.addSeparator()

        delete_action = menu.addAction(
            "Delete marker"
        )
        delete_action.setEnabled(
            marker_id not in self.RESERVED_MARKER_IDS
            and marker_id not in self._non_deletable_marker_ids
            and not self._playback_active
        )

        chosen_action = menu.exec(
            self.viewport().mapToGlobal(position)
        )

        if chosen_action == play_near_marker_action:
            self.play_near_marker_requested.emit(marker_id)

        elif chosen_action == loop_near_marker_action:
            self.loop_near_marker_requested.emit(marker_id)

        elif chosen_action == recenter_action:
            self.recenter_requested.emit(marker_id)

        elif chosen_action == edit_action:
            self.edit_requested.emit(marker_id)

        elif chosen_action == copy_id_action:
            QApplication.clipboard().setText(marker_id)

        elif chosen_action == copy_time_action:
            time_item = self.item(
                item.row(),
                self.TIME_COLUMN,
            )

            if time_item is not None:
                QApplication.clipboard().setText(
                    time_item.text().strip()
                )

        elif chosen_action == delete_action:
            self.delete_requested.emit(marker_id)

    def set_playback_active(self, active: bool) -> None:
        """Set whether playback is currently active."""
        self._playback_active = bool(active)

    def set_non_deletable_marker_ids(
        self,
        marker_ids: set[str],
    ) -> None:
        """Set marker IDs that must not be deletable."""

        self._non_deletable_marker_ids = {
            str(marker_id)
            for marker_id in marker_ids
        }