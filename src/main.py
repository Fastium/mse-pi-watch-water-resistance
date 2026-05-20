import sys
import time
from datetime import datetime

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from analysis.humidity_runtime import load_calibration_model, predict_ha_from_signal
from application.config import AppConfig
from middleware.controller import Controller
from user_interface.window import Window
from utils.file_utils import export_txt


class AcquisitionWorker(QObject):
    # Signal emitted when data is ready. Transmits X and Y arrays.
    data_ready = Signal(np.ndarray, np.ndarray)
    analysis_ready = Signal(dict)

    def __init__(self, controller,config, humidity_model=None, path_length: float | None = None):
        super().__init__()
        self.controller = controller
        self.config = config
        self.humidity_model = humidity_model
        self.path_length = path_length
        self._is_running = False

        # New flag to ensure mutual exclusivity
        self._is_busy = False

    @Slot()
    def run_continuous(self):
        """Continuous mode: runs in a loop until stopped."""
        # Mutual exclusion: Ignore if already doing something else
        if self._is_busy:
            return

        self._is_busy = True
        self._is_running = True
        self.controller.start()

        # Short delay to let the instrument initialize
        time.sleep(0.1)

        while self._is_running:
            data = self.controller.get_scope_data()
            self._emit_measurement(data)

            # Short pause to prevent 100% CPU usage
            time.sleep(0.01)

            # CRITICAL FIX: Process events so the thread can receive the "stop_working" signal!
            QCoreApplication.processEvents()

        self.controller.stop()

        # Free the worker for the next task
        self._is_busy = False

    def _emit_measurement(self, data: np.ndarray):
        x_data = np.arange(len(data))
        self.data_ready.emit(x_data, data)

        if self.humidity_model is None:
            return

        try:
            analysis = predict_ha_from_signal(
                signal=data,
                model=self.humidity_model,
                path_length=self.path_length,
            )
            self.analysis_ready.emit(analysis)
        except Exception as exc:
            # Le scope doit continuer a vivre meme si l'analyse echoue.
            print(f"[humidity-runtime] analysis failed: {exc}")

    @Slot()
    def stop_working(self):
        """Stops the continuous acquisition loop."""
        self._is_running = False

    @Slot()
    def single_run(self):
        data = self.controller.get_scope_data()
        self._emit_measurement(data)

    @Slot()
    def on_calibration(self):
        """Performs the series of measurements and exports them."""
        # Mutual exclusion
        if self._is_busy:
            return

        self._is_busy = True
        self.controller.start()

        # Initial stabilization
        time.sleep(0.2)

        for i in range(self.config.calibration_measurements):
            try:
                data = self.controller.get_scope_data()
                x_data = np.arange(len(data))

                # 1. Generate timestamp (Format: YYYYMMDD_HHMMSS)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_calibration_{i + 1}.txt"

                # 2. Export the data
                export_txt(data, self.config.calibration_output, filename)

                # 3. Update the UI with the latest measurement
                self.data_ready.emit(x_data, data)

            except RuntimeError:
                print(f"Calibration measurement {i + 1} failed.")

            # Short delay between captures to allow hardware to reset
            time.sleep(0.5)

            # Process events to keep the thread responsive if we ever want to interrupt it
            QCoreApplication.processEvents()

        self.controller.stop()
        self._is_busy = False

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
    window = Window()

    # --- Direct Wiring: UI -> Worker ---
    window.scope.start_requested.connect(worker.run_continuous)
    window.scope.stop_requested.connect(worker.stop_working)
    window.scope.single_start_requested.connect(worker.single_run)
    window.scope.calibration_requested.connect(worker.on_calibration)

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
    worker.data_ready.connect(window.set_data)
    worker.analysis_ready.connect(window.set_analysis)

    # 4. Cascade Initialization
    window.apply_config(config)

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
