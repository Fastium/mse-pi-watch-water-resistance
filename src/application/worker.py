import sys
import time
from datetime import datetime

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from analysis.humidity_runtime import load_calibration_model, predict_ha_from_signal
from utils.file_utils import export_txt


class AcquisitionWorker(QObject):
    # Signal emitted when data is ready. Transmits X and Y arrays.
    data_ready = Signal(np.ndarray, np.ndarray)
    analysis_ready = Signal(dict)

    def __init__(
        self, controller, config, humidity_model=None, path_length: float | None = None
    ):
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

            # Add full datetime string for future export
            analysis["timestamp_str"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Add raw unix timestamp (in seconds) for plotting
            analysis["timestamp"] = time.time()

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
        """Performs a single acquisition."""
        # Mutual exclusion
        if self._is_busy:
            return

        self._is_busy = True

        # 1. Start the generator
        self.controller.start()

        # 2. Wait for hardware to generate the wave and stabilize
        time.sleep(0.1)

        # 3. Capture the synchronized data
        data = self.controller.get_scope_data()
        self._emit_measurement(data)

        # 4. Stop the generator
        self.controller.stop()

        self._is_busy = False

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
