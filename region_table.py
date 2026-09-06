from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


class RegionTable(QTableWidget):
    """Display metadata regions in chronological order."""

    region_selected = Signal(str)
    region_double_clicked = Signal(str)

    ID_COLUMN = 0
    START_MARKER_COLUMN = 1
    END_MARKER_COLUMN = 2
    LABEL_COLUMN = 3

    RESERVED_REGION_IDS = {"rall"}

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(4)

        self.setHorizontalHeaderLabels(
            [
                "ID",
                "Start",
                "End",
                "Label",
            ]
        )

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

        # No horizontal grid lines; use alternating rows.
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

        header = self.horizontalHeader()

        # ID column.
        header.setSectionResizeMode(
            self.ID_COLUMN,
            QHeaderView.ResizeMode.Fixed,
        )
        self.setColumnWidth(
            self.ID_COLUMN,
            55,
        )

        # Start marker column.
        header.setSectionResizeMode(
            self.START_MARKER_COLUMN,
            QHeaderView.ResizeMode.Fixed,
        )
        self.setColumnWidth(
            self.START_MARKER_COLUMN,
            75,
        )

        # End marker column.
        header.setSectionResizeMode(
            self.END_MARKER_COLUMN,
            QHeaderView.ResizeMode.Fixed,
        )
        self.setColumnWidth(
            self.END_MARKER_COLUMN,
            75,
        )

        # Label gets remaining space.
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

    def set_regions(
        self,
        metadata,
        select_region_id: str | None = None,
    ) -> None:
        """Refresh the table, sorted by resolved start time."""

        self._updating = True

        try:
            self.setRowCount(0)

            if metadata is None:
                return

            regions = list(
                getattr(metadata, "regions", [])
            )

            regions.sort(
                key=lambda region:
                metadata.get_region_start_seconds(region)
            )

            self.setRowCount(len(regions))

            for row, region in enumerate(regions):
                region_id = str(region.id)

                start_seconds = (
                    metadata.get_region_start_seconds(
                        region
                    )
                )

                end_seconds = (
                    metadata.get_region_end_seconds(
                        region
                    )
                )

                start_marker_id = str(region.start)
                end_marker_id = str(region.end)

                id_item = QTableWidgetItem(
                    region_id
                )

                start_item = QTableWidgetItem(
                    start_marker_id
                )

                end_item = QTableWidgetItem(
                    end_marker_id
                )

                label_item = QTableWidgetItem(
                    getattr(
                        region,
                        "label",
                        None,
                    )
                    or ""
                )

                # Store the region ID on every cell.
                for item in (
                    id_item,
                    start_item,
                    end_item,
                    label_item,
                ):
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        region_id,
                    )

                # Store resolved timing on marker cells.
                start_item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    float(start_seconds),
                )

                end_item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    float(end_seconds),
                )

                tooltip = self._build_region_tooltip(
                    start_seconds,
                    end_seconds,
                )

                start_item.setToolTip(tooltip)
                end_item.setToolTip(tooltip)

                self.setItem(
                    row,
                    self.ID_COLUMN,
                    id_item,
                )

                self.setItem(
                    row,
                    self.START_MARKER_COLUMN,
                    start_item,
                )

                self.setItem(
                    row,
                    self.END_MARKER_COLUMN,
                    end_item,
                )

                self.setItem(
                    row,
                    self.LABEL_COLUMN,
                    label_item,
                )

        finally:
            self._updating = False

        if select_region_id is not None:
            self.select_region(select_region_id)
        else:
            self.clearSelection()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds for a tooltip."""

        total_milliseconds = round(
            float(seconds) * 1000
        )

        total_seconds, milliseconds = divmod(
            total_milliseconds,
            1000,
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds_part = divmod(
            remainder,
            60,
        )

        if milliseconds:
            seconds_text = (
                f"{seconds_part:02d}."
                f"{milliseconds:03d}"
            )
        else:
            seconds_text = f"{seconds_part:02d}"

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds_text}"
            )

        return (
            f"{minutes:02d}:"
            f"{seconds_text}"
        )

    @classmethod
    def _build_region_tooltip(
        cls,
        start_seconds: float,
        end_seconds: float,
    ) -> str:
        """Build the timing tooltip for a region."""

        duration = max(
            0.0,
            float(end_seconds) - float(start_seconds),
        )

        return (
            f"Start: {cls._format_time(start_seconds)}\n"
            f"End: {cls._format_time(end_seconds)}\n"
            f"Duration: {cls._format_time(duration)}"
        )

    def select_region(
        self,
        region_id: str | None,
    ) -> None:
        """Select the row belonging to region_id."""

        if self._updating:
            return

        self.clearSelection()

        if region_id is None:
            return

        region_id = str(region_id)

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

            if stored_id == region_id:
                self.selectRow(row)
                return

    def selected_region_id(self) -> str | None:
        """Return the selected region ID, if any."""

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

        region_id = self.selected_region_id()

        if region_id is not None:
            self.region_selected.emit(region_id)

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

        region_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        if region_id is None:
            return

        region_id = str(region_id)

        # The default full-track region is structural.
        if region_id in self.RESERVED_REGION_IDS:
            return

        self.region_double_clicked.emit(
            region_id
        )

