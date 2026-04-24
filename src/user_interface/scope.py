from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class Scope(QGroupBox):
    def __init__(
        self,
        start: Callable[[], None],
        stop: Callable[[], None],
        enable_trigger: Callable[[], None],
        disable_trigger: Callable[[], None],
        single_start: Callable[[], None],
        export: Callable[[np.ndarray, str], None],
    ):
        super().__init__()

        # Setup callbacks for the toggle button
        if start is not None:
            self.start_callback = start
        else:
            raise ValueError("start must be a callable")

        if stop is not None:
            self.stop_callback = stop
        else:
            raise ValueError("stop must be a callable")

        if enable_trigger is not None:
            self.enable_trigger_callback = enable_trigger
        else:
            raise ValueError("enable_trigger must be a callable")

        if disable_trigger is not None:
            self.disable_trigger_callback = disable_trigger
        else:
            raise ValueError("disable_trigger must be a callable")

        if single_start is not None:
            self.single_start_callback = single_start
        else:
            raise ValueError("single_start must be a callable")

        if export is not None:
            self.export_callback = export
        else:
            raise ValueError("export must be a callable")

        # Setup the toggle button (top-left)
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle)

        # setup single start button
        self.single_start_btn = QPushButton("Single Start")
        self.single_start_btn.clicked.connect(self._on_single_start)

        # export button
        self.export_btn = QPushButton("Export as txt")
        self.export_btn.setText("Export as txt")
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
            self.start_callback()
            # disable single start
            self.single_start_btn.setEnabled(False)
            self.disable_trigger_callback()
        else:
            self.toggle_btn.setText("Start")
            self.stop_callback()
            # enable single start
            self.single_start_btn.setEnabled(True)
            self.enable_trigger_callback()

    def _on_export(self):
        print("Export :")
        y_data = self.curve.getData()
        name = self.export_filename.text() + ".txt"

        if y_data is not None:
            self.export_callback(np.array(y_data), name)
        else:
            print("No data to export yet.")

    def _on_single_start(self):
        if self.single_start_callback is not None:
            self.single_start_callback()
        else:
            print("No single start callback set.")

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Update the displayed values on the scope."""
        self.curve.setData(x_data, y_data)
