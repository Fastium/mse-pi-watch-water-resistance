# src/user_interface/window.py
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from application.config import AppConfig
from user_interface.actions import ActionsPanel
from user_interface.parameters import ParametersPanel
from user_interface.scope import Scope


class Window(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()

        self.setWindowTitle("Scope Application")
        self.resize(1600, 800)

        # Setup main widget and layout
        central_widget = QWidget()
        main_layout = QHBoxLayout()  # Principal Horizontal

        # Left Column : Actions (Top) + Scope/Graphs (Bottom)
        left_layout = QVBoxLayout()
        self.actions_panel = ActionsPanel()
        self.scope = Scope(config)
        left_layout.addWidget(self.actions_panel, stretch=0)
        left_layout.addWidget(self.scope, stretch=1)

        # Right Column : Parameters
        self.parameters = ParametersPanel(config)

        # Add everything to main layout
        main_layout.addLayout(left_layout, stretch=4)
        main_layout.addWidget(self.parameters, stretch=1)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
