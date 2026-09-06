from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)


class RegionDialog(QDialog):
    """Dialog for editing an existing metadata region."""

    def __init__(self, region, metadata, parent=None):
        super().__init__(parent)

        self.region = region
        self.metadata = metadata

        self.setWindowTitle(f"Edit Region: {region.id}")
        self.setModal(True)

        self._build_ui()
        self._populate_marker_combos()
        self._load_region()

    def _build_ui(self) -> None:
        self.id_label = QLabel(str(self.region.id))

        self.start_marker_combo = QComboBox()
        self.end_marker_combo = QComboBox()

        self.label_edit = QLineEdit()

        self.description_edit = QTextEdit()
        self.description_edit.setAcceptRichText(False)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.addRow("ID:", self.id_label)
        form.addRow("Start marker:", self.start_marker_combo)
        form.addRow("End marker:", self.end_marker_combo)
        form.addRow("Label:", self.label_edit)
        form.addRow("Description:", self.description_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.button_box)

    def _populate_marker_combos(self) -> None:
        """Populate marker selectors in chronological order."""

        markers = list(self.metadata.markers.values())
        markers.sort(key=lambda marker: marker.seconds)

        for marker in markers:
            marker_id = str(marker.id)
            text = f"{marker_id}    {marker.time}"

            self.start_marker_combo.addItem(
                text,
                marker_id,
            )
            self.end_marker_combo.addItem(
                text,
                marker_id,
            )

    def _load_region(self) -> None:
        """Load the current region values into the dialog."""

        self._select_marker(
            self.start_marker_combo,
            self.region.start,
        )
        self._select_marker(
            self.end_marker_combo,
            self.region.end,
        )

        self.label_edit.setText(
            self.region.label or ""
        )

        self.description_edit.setPlainText(
            self.region.description or ""
        )

    @staticmethod
    def _select_marker(
        combo: QComboBox,
        marker_id: str,
    ) -> None:
        """Select a marker by its ID."""

        index = combo.findData(str(marker_id))

        if index >= 0:
            combo.setCurrentIndex(index)

    def _save(self) -> None:
        """Validate and commit the edited region."""

        start_marker_id = self.start_marker_combo.currentData()
        end_marker_id = self.end_marker_combo.currentData()

        if start_marker_id is None or end_marker_id is None:
            QMessageBox.warning(
                self,
                "Invalid region",
                "A start marker and end marker must be selected.",
            )
            return

        start_marker = self.metadata.markers.get(
            str(start_marker_id)
        )
        end_marker = self.metadata.markers.get(
            str(end_marker_id)
        )

        if start_marker is None or end_marker is None:
            QMessageBox.warning(
                self,
                "Invalid region",
                "The selected marker could not be found.",
            )
            return

        if end_marker.seconds < start_marker.seconds:
            QMessageBox.warning(
                self,
                "Invalid region",
                "The end marker must not occur before the start marker.",
            )
            return

        self.region.start = str(start_marker_id)
        self.region.end = str(end_marker_id)
        self.region.label = self.label_edit.text().strip() or None
        self.region.description = (
            self.description_edit.toPlainText().strip()
        )

        self.accept()
