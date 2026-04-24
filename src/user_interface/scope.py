import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class Scope(QGroupBox):
    # --- Déclaration des Signaux ---
    start_requested = Signal()
    stop_requested = Signal()
    single_start_requested = Signal()
    export_requested = Signal(np.ndarray, str)
    enable_trigger_requested = Signal()
    disable_trigger_requested = Signal()

    def __init__(self):
        super().__init__()

        # Setup the toggle button (top-left)
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle)

        # setup single start button
        self.single_start_btn = QPushButton("Single Start")
        # On émet directement le signal lors du clic
        self.single_start_btn.clicked.connect(self.single_start_requested.emit)

        # export button
        self.export_btn = QPushButton("Export as txt")
        self.export_btn.clicked.connect(self._on_export)

        # export filename
        self.export_filename = QLineEdit()
        self.export_filename.setText("measure-")

        # Setup scope graph (center)
        self.graph = pg.PlotWidget(title="Scope")
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.graph.plot(pen="y")

        # Setup layouts
        main_layout = QVBoxLayout()

        # Top layout for the button (aligned left)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.toggle_btn)
        top_layout.addWidget(self.single_start_btn)
        top_layout.addWidget(self.export_btn)
        top_layout.addWidget(self.export_filename)
        top_layout.addStretch()

        # Middle layout for the graph and Y-slider
        mid_layout = QHBoxLayout()
        mid_layout.addWidget(self.graph)

        # Assemble the main layout
        main_layout.addLayout(top_layout)
        main_layout.addLayout(mid_layout)

        self.setLayout(main_layout)

    def _on_toggle(self, checked: bool):
        """Handle button toggle state to start/stop the scope."""
        if checked:
            self.toggle_btn.setText("Stop")
            self.start_requested.emit()

            # disable single start
            self.single_start_btn.setEnabled(False)
            self.disable_trigger_requested.emit()
        else:
            self.toggle_btn.setText("Start")
            self.stop_requested.emit()

            # enable single start
            self.single_start_btn.setEnabled(True)
            self.enable_trigger_requested.emit()

    def _on_export(self):
        print("Export :")
        data = self.curve.getData()
        name = self.export_filename.text() + ".txt"

        if data is not None:
            # getData() renvoie un tuple (x, y), on le convertit en array comme dans ton code original
            self.export_requested.emit(np.array(data), name)
        else:
            print("No data to export yet.")

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Update the displayed values on the scope."""
        self.curve.setData(x_data, y_data)
