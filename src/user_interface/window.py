from typing import Callable

import numpy as np
from PySide6.QtWidgets import (
    QHBoxLayout,  # Remplacement par un layout horizontal
    QMainWindow,
    QWidget,
)

from user_interface.parameters import ParametersPanel
from user_interface.scope import Scope


class Window(QMainWindow):
    def __init__(
        self,
        start_scope: Callable[[], None],
        stop_scope: Callable[[], None],
        # Scope
        set_range: Callable[[float], None],
        set_bandwidth: Callable[[float], None],
        set_coupling: Callable[[str], None],
        set_trigger: Callable[[float], None],
        set_trigger_hysteresis: Callable[[float], None],
        set_sample_rate: Callable[[float], None],
        set_buffer_size: Callable[[int], None],
        # Wavegen
        set_wavegen_function: Callable[[str], None],
        set_wavegen_frequency: Callable[[float], None],
        set_wavegen_amplitude: Callable[[float], None],
        set_wavegen_offset: Callable[[float], None],
        # Gain
        set_gain_a0: Callable[[bool], None],
        set_gain_a1: Callable[[bool], None],
        set_gain_a2: Callable[[bool], None],
    ):
        super().__init__()

        self.setWindowTitle("Oscilloscope Application")
        self.resize(1000, 600)  # On agrandit un peu la fenêtre pour la place du panel

        # Setup main widget and layout
        central_widget = QWidget()
        main_layout = QHBoxLayout()  # Horizontal

        # Instantiate and add the Scope widget (on lui donne un poids stretch plus grand)
        self.scope = Scope(start=start_scope, stop=stop_scope)
        main_layout.addWidget(self.scope, stretch=3)

        # Instantiate and add the Parameters panel on the right
        self.parameters = ParametersPanel(
            set_range_cb=set_range,
            set_bandwidth_cb=set_bandwidth,
            set_coupling_cb=set_coupling,
            set_trigger_cb=set_trigger,
            set_trigger_hysteresis_cb=set_trigger_hysteresis,
            set_sample_rate_cb=set_sample_rate,
            set_buffer_size_cb=set_buffer_size,
            set_wavegen_function_cb=set_wavegen_function,
            set_wavegen_frequency_cb=set_wavegen_frequency,
            set_wavegen_amplitude_cb=set_wavegen_amplitude,
            set_wavegen_offset_cb=set_wavegen_offset,
            set_gain_a0_cb=set_gain_a0,
            set_gain_a1_cb=set_gain_a1,
            set_gain_a2_cb=set_gain_a2,
        )
        main_layout.addWidget(self.parameters, stretch=1)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        self.scope.set_data(x_data, y_data)

    # --- Scope GUI Setters ---
    def set_scope_range(self, val: float):
        self.parameters.set_scope_range(val)

    def set_scope_bandwidth(self, val: float):
        self.parameters.set_scope_bandwidth(val)

    def set_scope_coupling(self, val: str):
        self.parameters.set_scope_coupling(val)

    def set_scope_trigger(self, val: float):
        self.parameters.set_scope_trigger(val)

    def set_scope_hysteresis(self, val: float):
        self.parameters.set_scope_hysteresis(val)

    def set_scope_sample_rate(self, val: float):
        self.parameters.set_scope_sample_rate(val)

    def set_scope_buffer_size(self, val: int):
        self.parameters.set_scope_buffer_size(val)

    # --- Wavegen GUI Setters ---
    def set_wavegen_function(self, val: str):
        self.parameters.set_wavegen_function(val)

    def set_wavegen_frequency(self, val: float):
        self.parameters.set_wavegen_frequency(val)

    def set_wavegen_amplitude(self, val: float):
        self.parameters.set_wavegen_amplitude(val)

    def set_wavegen_offset(self, val: float):
        self.parameters.set_wavegen_offset(val)

    # --- Gain GUI Setters ---
    def set_gain_a0(self, val: bool):
        self.parameters.set_gain_a0(val)

    def set_gain_a1(self, val: bool):
        self.parameters.set_gain_a1(val)

    def set_gain_a2(self, val: bool):
        self.parameters.set_gain_a2(val)
