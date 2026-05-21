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
from utils.file_utils import export_csv_lines, export_txt


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
    window.actions_panel.start_requested.connect(worker.run_continuous)
    window.actions_panel.stop_requested.connect(worker.stop_working)
    window.actions_panel.single_start_requested.connect(worker.single_run)
    window.actions_panel.calibration_requested.connect(worker.on_calibration)

    # -> Export wiring (custom function to get data from scope)
    def handle_export_scope():
        data = window.scope.get_current_data()
        if data is not None:
            # Génération du nom de fichier horodaté
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"measure_{timestamp}_scope.txt"
            export_txt(data, ".", filename)
        else:
            print("No data to export yet.")

    def handle_export_abs():
        data = window.scope.get_abs_current_data()
        if data is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"measure_{timestamp}_absorbance.txt"
            export_txt(data, ".", filename)
        else:
            print("No absorbance data to export yet.")

    def handle_export_ha():
        data_lines = window.scope.get_ha_export_data()
        if data_lines:
            # Génération du nom de fichier horodaté
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"measure_{timestamp}_HA.txt"

            header = "Timestamp, Relative_Time_s, Absolute_Humidity"
            export_csv_lines(header, data_lines, ".", filename)
        else:
            print("No HA data to export yet.")

    window.actions_panel.export_requested.connect(handle_export_scope)
    window.actions_panel.export_ha_requested.connect(handle_export_ha)
    window.actions_panel.export_abs_requested.connect(handle_export_abs)

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
    worker.data_ready.connect(window.scope.set_data)

    # Analysis feedback to Labels AND Graphs
    worker.analysis_ready.connect(window.actions_panel.set_analysis_labels)
    worker.analysis_ready.connect(window.scope.set_analysis)

    # -> Real-time plot reset wiring
    window.actions_panel.reset_plot_requested.connect(window.scope.reset_ha_plot)

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
