import sys
import time

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from application.config import AppConfig
from middleware.controller import Controller
from user_interface.window import Window
from utils.file_utils import export_txt


class AcquisitionWorker(QObject):
    # Signal émis quand les données sont prêtes. Transmet les tableaux X et Y.
    data_ready = Signal(np.ndarray, np.ndarray)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._is_running = False

    def start_working(self):
        self._is_running = True

    def stop_working(self):
        self._is_running = False

    def run(self):
        while self._is_running:
            try:
                data = self.controller.get_scope_data()
                x_data = np.arange(len(data))
                self.data_ready.emit(x_data, data)
            except RuntimeError:
                pass  # Ignore si l'appareil n'est pas encore prêt

            # Petite pause pour éviter de monopoliser le CPU à 100%
            # si get_scope_data n'est pas bloquant
            time.sleep(0.01)

    def single_run(self):
        data = self.controller.get_scope_data()
        x_data = np.arange(len(data))
        self.data_ready.emit(x_data, data)


def main():
    app = QApplication(sys.argv)

    # 1. Instanciation des composants principaux
    config = AppConfig()
    controller = Controller()

    # Initialisation du Hardware
    controller.connect()
    controller.setup()

    # Mise en place du Worker et du Thread
    worker = AcquisitionWorker(controller)
    thread = QThread()
    worker.moveToThread(thread)

    # Fonctions encapsulées pour démarrer le hardware ET le thread
    def start_acquisition():
        thread.started.connect(worker.run)
        controller.start()
        worker.start_working()
        if not thread.isRunning():
            thread.start()

    def stop_acquisition():
        worker.stop_working()
        thread.quit()
        thread.wait(100)  # Attente max de 100ms
        controller.stop()

    def single_acquisition():
        thread.started.connect(worker.single_run)
        controller.start()
        worker.start_working()
        if not thread.isRunning():
            thread.start()

        worker.stop_working()
        thread.quit()
        thread.wait(100)  # Attente max de 100ms
        controller.stop()

    # 2. Instanciation de l'UI (Maintenant très propre !)
    window = Window()

    # 3. Câblage des Signaux (Architecture Orientée Événements)

    # -> Câblage du Scope
    window.scope.start_requested.connect(start_acquisition)
    window.scope.stop_requested.connect(stop_acquisition)
    window.scope.single_start_requested.connect(single_acquisition)
    window.scope.export_requested.connect(export_txt)

    # -> Câblage des Paramètres Scope
    window.parameters.range_changed.connect(controller.set_scope_range)
    window.parameters.bandwidth_changed.connect(controller.set_scope_bandwidth)
    window.parameters.coupling_changed.connect(controller.set_scope_coupling)
    window.parameters.trigger_changed.connect(controller.set_scope_trigger)
    window.parameters.trigger_hysteresis_changed.connect(
        controller.set_scope_hysteresis
    )
    window.parameters.sample_rate_changed.connect(controller.set_scope_sample_rate)
    window.parameters.buffer_size_changed.connect(controller.set_scope_buffer_size)

    # -> Câblage des Paramètres Wavegen
    window.parameters.wavegen_function_changed.connect(controller.set_wavegen_function)
    window.parameters.wavegen_frequency_changed.connect(
        controller.set_wavegen_frequency
    )
    window.parameters.wavegen_amplitude_changed.connect(
        controller.set_wavegen_amplitude
    )
    window.parameters.wavegen_offset_changed.connect(controller.set_wavegen_offset)

    # -> Câblage des Paramètres de Gain
    window.parameters.gain_a0_changed.connect(controller.set_gain_a0)
    window.parameters.gain_a1_changed.connect(controller.set_gain_a1)
    window.parameters.gain_a2_changed.connect(controller.set_gain_a2)

    # -> Câblage du retour de données (Worker -> UI)
    worker.data_ready.connect(window.set_data)

    # 4. Initialisation en "Cascade"
    # On applique la config à l'UI. L'UI met à jour ses widgets.
    # Les widgets émettent leurs signaux qui configurent le Hardware via les connexions ci-dessus.
    window.apply_config(config)

    # Affichage
    window.show()

    # Disconnect the controller when the application is closed
    def on_quit():
        stop_acquisition()
        controller.disconnect()

    app.aboutToQuit.connect(on_quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
