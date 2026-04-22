import os
import sys

os.environ["QT_API"] = "pyside6"

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qt_material import apply_stylesheet


class Oscilloscope(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Oscilloscope Interactif Temps Réel")
        self.resize(1000, 600)

        # Création du widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # --- ARCHITECTURE DE L'INTERFACE ---
        # Layout principal horizontal (Gauche = Graphique, Droite = Colonne de contrôles)
        main_layout = QHBoxLayout(central_widget)

        # 1. LA PARTIE GAUCHE (Le Graphique)
        self.graph = pg.PlotWidget(title="Signal d'entrée")
        self.graph.setYRange(-2.5, 2.5)
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.graph.plot(pen="y")

        # On ajoute le graphique au layout principal (stretch=3 pour qu'il prenne 3/4 de la largeur)
        main_layout.addWidget(self.graph, stretch=3)

        # 2. LA PARTIE DROITE (Les Contrôles)
        controls_layout = QVBoxLayout()
        # On ajoute cette colonne au layout principal (stretch=1 pour le dernier 1/4)
        main_layout.addLayout(controls_layout, stretch=1)

        # --- HAUT À DROITE : Boutons Start / Stop ---
        self.btn_start = QPushButton("Démarrer")
        self.btn_stop = QPushButton("Arrêter")

        # On désactive le bouton Stop au lancement puisqu'on va démarrer en mode "Pause"
        self.btn_stop.setEnabled(False)

        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_stop)

        # --- L'ASTUCE : Un "Ressort" ---
        # addStretch agit comme un ressort invisible qui pousse ce qui est au-dessus vers le haut,
        # et ce qui est en dessous vers le bas.
        controls_layout.addStretch()

        # --- BAS À DROITE : Paramètres du signal ---
        self.label_signal = QLabel("Type de signal :")
        self.combo_signal = QComboBox()
        self.combo_signal.addItems(["Sinusoïdal", "Carré", "Bruit Aléatoire"])

        controls_layout.addWidget(self.label_signal)
        controls_layout.addWidget(self.combo_signal)

        # --- LOGIQUE ET DONNÉES ---
        self.x_data = np.linspace(0, 10, 1000)
        self.phase = 0.0

        # Configuration du Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

        # Connexion des boutons à leurs fonctions respectives
        self.btn_start.clicked.connect(self.start_timer)
        self.btn_stop.clicked.connect(self.stop_timer)

        # On démarre automatiquement au lancement
        self.start_timer()

    def start_timer(self):
        """Démarre l'acquisition et gère l'état des boutons."""
        self.timer.start(16)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_timer(self):
        """Arrête l'acquisition et gère l'état des boutons."""
        self.timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def update_plot(self):
        """Calcule et affiche la nouvelle onde en fonction des paramètres."""
        self.phase += 0.1

        # On lit la valeur sélectionnée dans le menu déroulant
        signal_type = self.combo_signal.currentText()

        # Génération du signal avec NumPy
        if signal_type == "Sinusoïdal":
            y_data = np.sin(self.x_data + self.phase)
        elif signal_type == "Carré":
            # On transforme le sinus en onde carrée (1 ou -1)
            y_data = np.where(np.sin(self.x_data + self.phase) > 0, 1.0, -1.0)
        elif signal_type == "Bruit Aléatoire":
            y_data = np.random.normal(0, 0.5, len(self.x_data))
        else:
            y_data = np.zeros(len(self.x_data))

        self.curve.setData(self.x_data, y_data)


def main():
    app = QApplication(sys.argv)

    apply_stylesheet(app, theme="light_blue.xml")

    window = Oscilloscope()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
