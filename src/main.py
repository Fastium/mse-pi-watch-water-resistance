import sys
import time

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from middleware.controller import Controller
from user_interface.window import Window

DEFAULT_SCOPE_RANGE_STR = 2
DEFAULT_SCOPE_BANDWIDTH_STR = 300e3
DEFAULT_SCOPE_COUPLING_STR = "ac"
DEFAULT_SCOPE_TRIGGER = 1.0
DEFAULT_SCOPE_HYSTERESIS = 0.1
DEFAULT_SCOPE_SAMPLE_RATE = 300e3
DEFAULT_SCOPE_BUFFER_SIZE = 8192

DEFAULT_WAVEGEN_FUNCTION = "triangle"
DEFAULT_WAVEGEN_FREQUENCY = 50.0
DEFAULT_WAVEGEN_AMPLITUDE = 1.5
DEFAULT_WAVEGEN_OFFSET = 0

DEFAULT_GAIN_A0 = False
DEFAULT_GAIN_A1 = False
DEFAULT_GAIN_A2 = False


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


def setup_default(c: Controller, w: Window):
    c.set_scope_range(DEFAULT_SCOPE_RANGE_STR)  # Correspond à "10 V"
    c.set_scope_bandwidth(DEFAULT_SCOPE_BANDWIDTH_STR)  # Correspond à "Full"
    c.set_scope_coupling(DEFAULT_SCOPE_COUPLING_STR)
    c.set_scope_trigger(DEFAULT_SCOPE_TRIGGER)
    c.set_scope_hysteresis(DEFAULT_SCOPE_HYSTERESIS)
    c.set_scope_sample_rate(DEFAULT_SCOPE_SAMPLE_RATE)
    c.set_scope_buffer_size(DEFAULT_SCOPE_BUFFER_SIZE)

    c.set_wavegen_function(DEFAULT_WAVEGEN_FUNCTION)
    c.set_wavegen_frequency(DEFAULT_WAVEGEN_FREQUENCY)
    c.set_wavegen_amplitude(DEFAULT_WAVEGEN_AMPLITUDE)
    c.set_wavegen_offset(DEFAULT_WAVEGEN_OFFSET)

    c.set_gain_a0(DEFAULT_GAIN_A0)
    c.set_gain_a1(DEFAULT_GAIN_A1)
    c.set_gain_a2(DEFAULT_GAIN_A2)

    # 2. Configuration de l'Interface Graphique (UI)
    w.set_scope_range(DEFAULT_SCOPE_RANGE_STR)
    w.set_scope_bandwidth(DEFAULT_SCOPE_BANDWIDTH_STR)
    w.set_scope_coupling(DEFAULT_SCOPE_COUPLING_STR)
    w.set_scope_trigger(DEFAULT_SCOPE_TRIGGER)
    w.set_scope_hysteresis(DEFAULT_SCOPE_HYSTERESIS)
    w.set_scope_sample_rate(DEFAULT_SCOPE_SAMPLE_RATE)
    w.set_scope_buffer_size(DEFAULT_SCOPE_BUFFER_SIZE)

    w.set_wavegen_function(DEFAULT_WAVEGEN_FUNCTION)
    w.set_wavegen_frequency(DEFAULT_WAVEGEN_FREQUENCY)
    w.set_wavegen_amplitude(DEFAULT_WAVEGEN_AMPLITUDE)
    w.set_wavegen_offset(DEFAULT_WAVEGEN_OFFSET)

    w.set_gain_a0(DEFAULT_GAIN_A0)
    w.set_gain_a1(DEFAULT_GAIN_A1)
    w.set_gain_a2(DEFAULT_GAIN_A2)


def main():
    app = QApplication(sys.argv)

    controller = Controller()
    controller.connect()
    controller.setup()

    # Mise en place du Worker et du Thread
    worker = AcquisitionWorker(controller)
    thread = QThread()
    worker.moveToThread(thread)

    # Le thread exécute la fonction 'run' du worker quand il démarre
    thread.started.connect(worker.run)

    # Fonctions encapsulées pour démarrer le hardware ET le thread
    def start_acquisition():
        controller.start()
        worker.start_working()
        if not thread.isRunning():
            thread.start()

    def stop_acquisition():
        worker.stop_working()
        # On attend poliment que le thread finisse sa boucle en cours
        # (Attention : si get_scope_data est bloqué indéfiniment, quit/wait peut bloquer ici aussi)
        thread.quit()
        thread.wait(100)  # Attente max de 100ms
        controller.stop()

    window = Window(
        start_scope=start_acquisition,
        stop_scope=stop_acquisition,
        # Scope parameters
        set_range=controller.set_scope_range,
        set_bandwidth=controller.set_scope_bandwidth,
        set_coupling=controller.set_scope_coupling,
        set_trigger=controller.set_scope_trigger,
        set_trigger_hysteresis=controller.set_scope_hysteresis,
        set_sample_rate=controller.set_scope_sample_rate,
        set_buffer_size=controller.set_scope_buffer_size,
        # Wavegen parameters
        set_wavegen_function=controller.set_wavegen_function,
        set_wavegen_frequency=controller.set_wavegen_frequency,
        set_wavegen_amplitude=controller.set_wavegen_amplitude,
        set_wavegen_offset=controller.set_wavegen_offset,
        # Gain parameters
        set_gain_a0=controller.set_gain_a0,
        set_gain_a1=controller.set_gain_a1,
        set_gain_a2=controller.set_gain_a2,
    )

    setup_default(controller, window)

    # Connexion du signal de données du worker à l'affichage de la fenêtre
    worker.data_ready.connect(window.set_data)

    window.show()

    # Disconnect the controller when the application is closed
    def on_quit():
        stop_acquisition()
        controller.disconnect()

    app.aboutToQuit.connect(on_quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
