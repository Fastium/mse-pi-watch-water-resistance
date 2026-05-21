# src/user_interface/window.py
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QWidget,
)

from application.config import AppConfig
from user_interface.humidity_plot import HumidityPlotPanel
from user_interface.parameters import ParametersPanel
from user_interface.scope import Scope


class Window(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()

        self.setWindowTitle("Scope Application")
        self.resize(1500, 600)  # Increased width to fit the new panel

        # Setup main widget and layout
        central_widget = QWidget()
        main_layout = QHBoxLayout()  # Horizontal

        # Instantiate panels directly with config
        self.parameters = ParametersPanel(config)
        self.scope = Scope()
        self.humidity_plot = HumidityPlotPanel(config)

        # Add widgets to layout
        main_layout.addWidget(self.parameters, stretch=1)
        main_layout.addWidget(self.scope, stretch=3)
        main_layout.addWidget(self.humidity_plot, stretch=3)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
