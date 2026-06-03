# src/user_interface/actions.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
)


class ActionsPanel(QGroupBox):
    # Signal Declarations
    start_requested = Signal()
    stop_requested = Signal()
    single_start_requested = Signal()
    reset_plot_requested = Signal()
    export_requested = Signal()
    export_abs_requested = Signal()
    export_ha_requested = Signal()
    calibration_requested = Signal()
    enable_trigger_requested = Signal()
    disable_trigger_requested = Signal()

    def __init__(self):
        super().__init__("Controls")

        layout = QHBoxLayout()

        # Setup the toggle button
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)

        # Setup reset button
        self.reset_btn = QPushButton("Reset Plot")
        self.reset_btn.clicked.connect(self.reset_plot_requested.emit)
        layout.addWidget(self.reset_btn)

        # setup single start button
        self.single_start_btn = QPushButton("Single Start")
        self.single_start_btn.clicked.connect(self.single_start_requested.emit)
        layout.addWidget(self.single_start_btn)

        # Calibration Button
        self.calibration_btn = QPushButton("Data Calibration")
        self.calibration_btn.clicked.connect(self.calibration_requested.emit)
        layout.addWidget(self.calibration_btn)

        # export button (Scope)
        self.export_btn = QPushButton("Export Scope")
        self.export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.export_btn)

        # export button (Absorbance)
        self.export_abs_btn = QPushButton("Export Absorbance")
        self.export_abs_btn.clicked.connect(self.export_abs_requested.emit)
        layout.addWidget(self.export_abs_btn)

        # export button (HA)
        self.export_ha_btn = QPushButton("Export HA Plot")
        self.export_ha_btn.clicked.connect(self.export_ha_requested.emit)
        layout.addWidget(self.export_ha_btn)

        # runtime analysis labels
        self.ha_label = QLabel("HA: --")
        layout.addWidget(self.ha_label)

        self.feature_label = QLabel("Feature: --")
        layout.addWidget(self.feature_label)

        layout.addStretch()
        self.setLayout(layout)

    def _on_toggle(self, checked: bool):
        if checked:
            self.toggle_btn.setText("Stop")
            self.start_requested.emit()
            self.single_start_btn.setEnabled(False)
            self.calibration_btn.setEnabled(False)
            self.disable_trigger_requested.emit()
        else:
            self.toggle_btn.setText("Start")
            self.stop_requested.emit()
            self.single_start_btn.setEnabled(True)
            self.calibration_btn.setEnabled(True)
            self.enable_trigger_requested.emit()

    def set_analysis_labels(self, analysis: dict):
        """Update HA/feature labels from the analysis dict."""
        ha_pred = analysis.get("HA_pred")
        feature_name = analysis.get("feature_name", "--")
        feature_value = analysis.get("feature_value")

        if ha_pred is None:
            self.ha_label.setText("HA: --")
        else:
            self.ha_label.setText(f"HA: {float(ha_pred):.3f} g/m3")

        if feature_value is None:
            self.feature_label.setText(f"{feature_name}: --")
        else:
            self.feature_label.setText(f"{feature_name}: {float(feature_value):.5f}")
