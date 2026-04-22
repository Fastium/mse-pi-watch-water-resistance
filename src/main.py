import sys

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from middleware.controller import Controller
from user_interface.window import Window


def main():
    app = QApplication(sys.argv)

    controller = Controller()
    controller.connect()
    controller.setup()
    # Création du timer pour mettre à jour l'affichage
    update_timer = QTimer()

    def update_data():
        try:
            data = controller.get_scope_data()
            x_data = np.arange(len(data))
            window.set_data(x_data, data)
        except RuntimeError:
            pass  # Ignore si l'appareil n'est pas encore prêt

    update_timer.timeout.connect(update_data)

    # Fonctions encapsulées pour démarrer le hardware ET le rafraîchissement
    def start_acquisition():
        controller.start()
        update_timer.start(50)  # Rafraîchissement toutes les 50ms (20 FPS)

    def stop_acquisition():
        update_timer.stop()
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

    data = controller.get_scope_data()
    x_data = np.arange(len(data))
    window.set_data(x_data, data)

    window.show()

    # Disconnect the controller when the application is closed
    app.aboutToQuit.connect(controller.disconnect)

    def on_quit():
        update_timer.stop()
        controller.disconnect()

    app.aboutToQuit.connect(on_quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
