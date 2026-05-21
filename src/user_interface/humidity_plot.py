# src/user_interface/humidity_plot.py
import pyqtgraph as pg
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from application.config import AppConfig


class HumidityPlotPanel(QGroupBox):
    def __init__(self, config: AppConfig):
        super().__init__("Real-time Absolute Humidity (HA) prediction")

        # Internal parameter to reduce plotting frequency (averaging)
        self.averaging_window = config.ha_averaging_window

        # Data buffers
        self.accumulator = []
        self.x_data = []
        self.y_data = []
        self.current_x = 0

        # UI setup
        self.layout = QVBoxLayout()
        self.graph = pg.PlotWidget()
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.graph.setLabel("left", "Absolute Humidity", units="g/m³")
        self.graph.setLabel("bottom", "Samples (Averaged)")

        # Plot curve
        self.curve = self.graph.plot(pen=pg.mkPen("#00ff00", width=2))

        self.layout.addWidget(self.graph)
        self.setLayout(self.layout)

        self.reset_plot()

    def reset_plot(self):
        """Clears the plot data and buffers. Called when a new acquisition starts."""
        self.accumulator.clear()
        self.x_data.clear()
        self.y_data.clear()
        self.current_x = 0
        self.curve.setData(self.x_data, self.y_data)

    def set_analysis(self, analysis: dict):
        """
        Slot to receive the analysis dictionary directly from the Worker.
        Extracts HA_pred, accumulates it, and plots the average.
        """
        ha_pred = analysis.get("HA_pred")
        if ha_pred is None:
            return

        self.accumulator.append(float(ha_pred))

        # Compute average when the window size is reached
        if len(self.accumulator) >= self.averaging_window:
            avg_ha = sum(self.accumulator) / len(self.accumulator)
            self.accumulator.clear()

            self.x_data.append(self.current_x)
            self.y_data.append(avg_ha)
            self.current_x += 1

            # Update the display with all accumulated points
            self.curve.setData(self.x_data, self.y_data)
