from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from metadata import format_seconds_as_time, parse_time_to_seconds


class MarkerDialog(QDialog):
    """Dialog for editing a marker's user-editable properties."""

    def __init__(self, marker, parent=None):
        super().__init__(parent)

        self.marker = marker

        self.setWindowTitle("Edit Marker")
        self.setModal(True)

        # ---------------------------------------------------------
        # Widgets
        # ---------------------------------------------------------

        self.id_edit = QLineEdit(marker.id)
        self.id_edit.setReadOnly(True)

        self.time_edit = QLineEdit(
            format_seconds_as_time(marker.seconds)
        )

        self.label_edit = QLineEdit(
            marker.label or ""
        )

        self.description_edit = QPlainTextEdit(
            marker.description or ""
        )

        # ---------------------------------------------------------
        # Form
        # ---------------------------------------------------------

        form = QFormLayout()
        form.addRow("ID:", self.id_edit)
        form.addRow("Time:", self.time_edit)
        form.addRow("Label:", self.label_edit)
        form.addRow(
            "Description:",
            self.description_edit,
        )

        # ---------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        # ---------------------------------------------------------
        # Layout
        # ---------------------------------------------------------

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        """Validate the edited values and update the marker."""

        time_text = self.time_edit.text().strip()

        try:
            seconds = parse_time_to_seconds(time_text)
        except ValueError as exc:
            self.time_edit.setFocus()
            self.time_edit.selectAll()

            self._show_error(
                str(exc)
            )
            return

        # Normalize the time to canonical millisecond format.
        self.marker.set_time(seconds)

        label = self.label_edit.text()
        self.marker.label = label if label else None

        self.marker.description = (
            self.description_edit.toPlainText()
        )

        self.accept()

    def _show_error(self, message: str) -> None:
        """Display a validation error without losing the dialog."""

        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            self,
            "Invalid Marker Time",
            message,
        )

