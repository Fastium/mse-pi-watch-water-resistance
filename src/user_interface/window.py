import numpy as np
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QWidget,
)

from application.config import AppConfig
from user_interface.parameters import ParametersPanel
from user_interface.scope import Scope


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.latest_analysis = None

        self.setWindowTitle("Scope Application")
        self.resize(1000, 600)

        # Setup main widget and layout
        central_widget = QWidget()
        main_layout = QHBoxLayout()  # Horizontal

        # Instantiate panels without any callbacks!
        self.parameters = ParametersPanel()
        self.scope = Scope()

        # Add widgets to layout
        main_layout.addWidget(self.scope, stretch=3)
        main_layout.addWidget(self.parameters, stretch=1)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def apply_config(self, config: AppConfig):
        """Met à jour les panneaux avec la configuration initiale."""
        self.parameters.apply_config(config)

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Transfère les nouvelles données au graphique."""
        self.scope.set_data(x_data, y_data)

    def set_analysis(self, analysis: dict):
        """Stocke et affiche le dernier résultat d'analyse dans la GUI."""
        self.latest_analysis = analysis
        self.scope.set_analysis(analysis)
