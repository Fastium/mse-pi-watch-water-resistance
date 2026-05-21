# src/main.py
import sys
import time
from datetime import datetime

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from analysis.humidity_runtime import load_calibration_model, predict_ha_from_signal
from application.config import AppConfig
from application.worker import AcquisitionWorker
from middleware.controller import Controller
from user_interface.window import Window
from utils.file_utils import export_txt


def main():
    app = QApplication(sys.argv)

    # 1. Main components instantiation
    config = AppConfig()
    controller = Controller()

    # Hardware initialization
    controller.connect()
    controller.setup()

    # --- Thread and Worker Management ---
    try:
        humidity_model = load_calibration_model()
        print(
            "[humidity-runtime] loaded model "
            f"{humidity_model.feature_name} -> HA from {humidity_model.calibration_metrics_path}"
        )
    except Exception as exc:
        humidity_model = None
        print(f"[humidity-runtime] disabled: {exc}")

    # Mise en place du Worker et du Thread
    worker = AcquisitionWorker(controller, humidity_model=humidity_model, config=config)
    thread = QThread()
    worker.moveToThread(thread)

    # Start the thread in the background once and for all.
    thread.start()

    # 2. UI Instantiation
    window = Window(config)

    # --- Direct Wiring: UI -> Worker ---
    window.scope.start_requested.connect(worker.run_continuous)
    window.scope.stop_requested.connect(worker.stop_working)
    window.scope.single_start_requested.connect(worker.single_run)
    window.scope.calibration_requested.connect(worker.on_calibration)

    # -> Real-time plot reset wiring
    # Ensures the HA graph is cleared whenever a new continuous or single acquisition begins.
    window.scope.start_requested.connect(window.humidity_plot.reset_plot)
    window.scope.single_start_requested.connect(window.humidity_plot.reset_plot)

    # Standard wiring that remains in the main thread
    window.scope.export_requested.connect(export_txt)

    # -> Scope Parameters Wiring
    window.parameters.range_changed.connect(controller.set_scope_range)
    window.parameters.bandwidth_changed.connect(controller.set_scope_bandwidth)
    window.parameters.coupling_changed.connect(controller.set_scope_coupling)
    window.parameters.trigger_changed.connect(controller.set_scope_trigger)
    window.parameters.trigger_hysteresis_changed.connect(
        controller.set_scope_hysteresis
    )
    window.parameters.sample_rate_changed.connect(controller.set_scope_sample_rate)
    window.parameters.buffer_size_changed.connect(controller.set_scope_buffer_size)

    # -> Wavegen Parameters Wiring
    window.parameters.wavegen_function_changed.connect(controller.set_wavegen_function)
    window.parameters.wavegen_frequency_changed.connect(
        controller.set_wavegen_frequency
    )
    window.parameters.wavegen_amplitude_changed.connect(
        controller.set_wavegen_amplitude
    )
    window.parameters.wavegen_offset_changed.connect(controller.set_wavegen_offset)

    # -> Gain Parameters Wiring
    window.parameters.gain_a0_changed.connect(controller.set_gain_a0)
    window.parameters.gain_a1_changed.connect(controller.set_gain_a1)
    window.parameters.gain_a2_changed.connect(controller.set_gain_a2)

    # -> Data feedback (Worker -> UI)
    # The worker sends data arrays directly to the scope graph
    worker.data_ready.connect(window.scope.set_data)

    # The worker sends the analysis dict to BOTH the scope and the new HA plot
    worker.analysis_ready.connect(window.scope.set_analysis)
    worker.analysis_ready.connect(window.humidity_plot.set_analysis)

    # -> Real-time plot reset wiring
    # Ensures the HA graph is cleared whenever a new continuous or single acquisition begins.
    window.scope.start_requested.connect(window.humidity_plot.reset_plot)
    window.scope.single_start_requested.connect(window.humidity_plot.reset_plot)

    # Display
    window.show()

    # Disconnect the controller and thread when the application is closed
    def on_quit():
        # Clean shutdown
        worker.stop_working()
        thread.quit()
        thread.wait(500)
        controller.disconnect()

    app.aboutToQuit.connect(on_quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
