from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

BAR_WIDTH = 20


class HumidityDisplay(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)

        # --- Relative Humidity Panel ---
        rel_layout = QVBoxLayout()

        self.rel_title = QLabel("Relative humidity")
        rel_layout.addWidget(self.rel_title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.rel_bar = QProgressBar()
        self.rel_bar.setRange(0, 100)
        self.rel_bar.setTextVisible(False)
        self.rel_bar.setOrientation(Qt.Orientation.Vertical)
        self.rel_bar.setFixedWidth(BAR_WIDTH)
        self.rel_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 10px; /* Moitié de la largeur (20/2) pour un bout parfaitement rond */
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 8px; /* Rayon extérieur (10) - bordure (2) = 8 */
                /* On peut forcer les coins supérieurs à être plats si on veut l'effet d'un liquide qui monte :
                   border-top-left-radius: 0px;
                   border-top-right-radius: 0px; */
            }
        """)

        rel_layout.addWidget(self.rel_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.rel_value = QLabel("0.000")
        rel_layout.addWidget(self.rel_value, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(rel_layout)

        # Absolue humidity panel
        abs_layout = QVBoxLayout()

        self.abs_title = QLabel("Absolute humidity")
        abs_layout.addWidget(self.abs_title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.abs_bar = QProgressBar()
        self.abs_bar.setRange(0, 100)
        self.abs_bar.setOrientation(Qt.Orientation.Vertical)
        self.abs_bar.setTextVisible(False)
        self.abs_bar.setFixedWidth(BAR_WIDTH)
        self.abs_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 10px; /* Moitié de la largeur (20/2) pour un bout parfaitement rond */
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 8px; /* Rayon extérieur (10) - bordure (2) = 8 */
                /* On peut forcer les coins supérieurs à être plats si on veut l'effet d'un liquide qui monte :
                   border-top-left-radius: 0px;
                   border-top-right-radius: 0px; */
            }
        """)
        abs_layout.addWidget(self.abs_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.abs_value = QLabel("0.000")
        abs_layout.addWidget(self.abs_value, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(abs_layout)

    def set_values(self, relative: float, absolute: float):
        self.rel_bar.setValue(int(relative))
        self.rel_value.setText(f"{relative:.1f}%")
        self.abs_bar.setValue(int(absolute))
        self.abs_value.setText(f"{absolute:.1f}%")
