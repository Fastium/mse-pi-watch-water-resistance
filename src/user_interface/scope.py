# src/user_interface/scope.py
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout

from application.config import AppConfig


class Scope(QGroupBox):
    def __init__(self, config: AppConfig):
        super().__init__("Graphs")

        # Setup layouts
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()

        # 1. Setup scope graph (Left column, Top)
        self.graph = pg.PlotWidget(title="Scope")
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.graph.plot(pen="y")
        left_layout.addWidget(self.graph)

        # 2. Setup absorbance graph (Left column, Bottom)
        self.abs_graph = pg.PlotWidget(title="Absorbance A(t)")
        self.abs_graph.showGrid(x=True, y=True, alpha=0.3)
        self.abs_curve = self.abs_graph.plot(pen=pg.mkPen("#ff8c00", width=2))
        left_layout.addWidget(self.abs_graph)

        # 3. Setup HA plot (Right column)
        self.ha_averaging_window = config.ha_averaging_window
        self.ha_accumulator = []
        self.ha_x_data = []
        self.ha_y_data = []
        self.ha_current_x = 0

        self.ha_graph = pg.PlotWidget(title="Real-time Absolute Humidity (HA)")
        self.ha_graph.showGrid(x=True, y=True, alpha=0.3)
        self.ha_graph.setLabel("left", "Absolute Humidity", units="g/m³")
        self.ha_graph.setLabel("bottom", "Samples (Averaged)")
        self.ha_curve = self.ha_graph.plot(pen=pg.mkPen("#00ff00", width=2))

        # Assemble layouts
        main_layout.addLayout(left_layout, stretch=3)
        main_layout.addWidget(self.ha_graph, stretch=3)

        self.setLayout(main_layout)

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Update the displayed values on the main scope."""
        self.curve.setData(x_data, y_data)

    def get_current_data(self):
        """Helper to get current data for export."""
        data = self.curve.getData()
        if data is not None:
            return np.array(data)[1]
        return None

    def reset_ha_plot(self):
        """Clears the HA plot data and buffers."""
        self.ha_accumulator.clear()
        self.ha_x_data.clear()
        self.ha_y_data.clear()
        self.ha_current_x = 0
        self.ha_curve.setData(self.ha_x_data, self.ha_y_data)

    def set_analysis(self, analysis: dict):
        """Update absorbance plot and HA plot."""
        absorbance = analysis.get("A")
        if absorbance is not None:
            a = np.asarray(absorbance, dtype=float).reshape(-1)
            x = np.arange(len(a), dtype=float)
            self.abs_curve.setData(x, a)
        else:
            self.abs_curve.setData([], [])

        ha_pred = analysis.get("HA_pred")
        if ha_pred is not None:
            self.ha_accumulator.append(float(ha_pred))
            if len(self.ha_accumulator) >= self.ha_averaging_window:
                avg_ha = sum(self.ha_accumulator) / len(self.ha_accumulator)
                self.ha_accumulator.clear()

                self.ha_x_data.append(self.ha_current_x)
                self.ha_y_data.append(avg_ha)
                self.ha_current_x += 1

                self.ha_curve.setData(self.ha_x_data, self.ha_y_data)
