import sys
from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QVBoxLayout,
)


class Scope(QGroupBox):
    def __init__(self, start: Callable[[], None], stop: Callable[[], None]):
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

        # Setup the toggle button (top-left)
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle)

        # Setup scope graph (center)
        self.graph = pg.PlotWidget(title="Scope")
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.graph.plot(pen="y")

        # Setup layouts
        main_layout = QVBoxLayout()

        # Top layout for the button (aligned left)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.toggle_btn)
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
            self.toggle_btn.setText("Disable")
            self.start_callback()
        else:
            self.toggle_btn.setText("Enable")
            self.stop_callback()

    def _update_x_range(self, value: int):
        """Update the X-axis range based on the slider value."""
        self.graph.setXRange(0, value)

    def _update_y_range(self, value: int):
        """Update the Y-axis range based on the slider value."""
        self.graph.setYRange(-value, value)

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Update the displayed values on the scope."""
        self.curve.setData(x_data, y_data)
