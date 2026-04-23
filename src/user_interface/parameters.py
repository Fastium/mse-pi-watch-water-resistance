from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ParametersPanel(QWidget):
    def __init__(
        self,
        # Scope callbacks
        set_range_cb: Callable[[float], None],
        set_bandwidth_cb: Callable[[float], None],
        set_coupling_cb: Callable[[str], None],
        set_trigger_cb: Callable[[float], None],
        set_trigger_hysteresis_cb: Callable[[float], None],
        set_sample_rate_cb: Callable[[float], None],
        set_buffer_size_cb: Callable[[int], None],
        # Wavegen callbacks
        set_wavegen_function_cb: Callable[[str], None],
        set_wavegen_frequency_cb: Callable[[float], None],
        set_wavegen_amplitude_cb: Callable[[float], None],
        set_wavegen_offset_cb: Callable[[float], None],
        # Gain callbacks
        set_gain_a0_cb: Callable[[bool], None],
        set_gain_a1_cb: Callable[[bool], None],
        set_gain_a2_cb: Callable[[bool], None],
    ):
        super().__init__()
        layout = QVBoxLayout()

        # --- SCOPE PARAMETERS ---
        scope_group = QGroupBox("Scope Parameters")
        scope_layout = QFormLayout()

        self.range_spin = QDoubleSpinBox()
        self.range_spin.setRange(0.0, 10.0)
        self.range_spin.setSingleStep(0.1)
        self.range_spin.valueChanged.connect(set_trigger_hysteresis_cb)
        scope_layout.addRow("Range:", self.range_spin)

        self.bandwidth_spin = QDoubleSpinBox()
        self.bandwidth_spin.setRange(0.0, 100e6)
        self.bandwidth_spin.setSingleStep(100e3)
        self.bandwidth_spin.valueChanged.connect(set_bandwidth_cb)
        scope_layout.addRow("Bandwidth:", self.bandwidth_spin)

        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(["dc", "ac"])
        self.coupling_combo.currentTextChanged.connect(set_coupling_cb)
        scope_layout.addRow("Coupling:", self.coupling_combo)

        self.trigger_spin = QDoubleSpinBox()
        self.trigger_spin.setRange(-10.0, 10)
        self.trigger_spin.setSingleStep(0.1)
        self.trigger_spin.valueChanged.connect(set_trigger_cb)
        scope_layout.addRow("Trigger Level (V):", self.trigger_spin)

        self.hysteresis_spin = QDoubleSpinBox()
        self.hysteresis_spin.setRange(0.0, 5.0)
        self.hysteresis_spin.setSingleStep(0.1)
        self.hysteresis_spin.valueChanged.connect(set_trigger_hysteresis_cb)
        scope_layout.addRow("Trigger Hysteresis (V):", self.hysteresis_spin)

        self.sample_rate_spin = QDoubleSpinBox()
        self.sample_rate_spin.setRange(1.0, 100e6)
        self.sample_rate_spin.setValue(300e3)
        self.sample_rate_spin.valueChanged.connect(set_sample_rate_cb)
        scope_layout.addRow("Sample Rate (Hz):", self.sample_rate_spin)

        self.buffer_size_spin = QSpinBox()
        self.buffer_size_spin.setRange(1, 32768)
        self.buffer_size_spin.setValue(8192)
        self.buffer_size_spin.valueChanged.connect(set_buffer_size_cb)
        scope_layout.addRow("Buffer Size:", self.buffer_size_spin)

        scope_group.setLayout(scope_layout)
        layout.addWidget(scope_group)

        # --- WAVEGEN PARAMETERS ---
        wavegen_group = QGroupBox("Wavegen Parameters")
        wavegen_layout = QFormLayout()

        self.function_combo = QComboBox()
        self.function_combo.addItems(
            ["sine", "square", "triangle", "ramp_up", "ramp_down", "dc"]
        )
        self.function_combo.setCurrentText("triangle")
        self.function_combo.currentTextChanged.connect(set_wavegen_function_cb)
        wavegen_layout.addRow("Function:", self.function_combo)

        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(0.1, 10e6)
        self.frequency_spin.setValue(50.0)
        self.frequency_spin.valueChanged.connect(set_wavegen_frequency_cb)
        wavegen_layout.addRow("Frequency (Hz):", self.frequency_spin)

        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(0.0, 5.0)
        self.amplitude_spin.setValue(0.2)
        self.amplitude_spin.valueChanged.connect(set_wavegen_amplitude_cb)
        wavegen_layout.addRow("Amplitude (V):", self.amplitude_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-5.0, 5.0)
        self.offset_spin.setValue(-0.1)
        self.offset_spin.valueChanged.connect(set_wavegen_offset_cb)
        wavegen_layout.addRow("Offset (V):", self.offset_spin)

        wavegen_group.setLayout(wavegen_layout)
        layout.addWidget(wavegen_group)

        # --- GAIN PARAMETERS ---
        gain_group = QGroupBox("Gain IO Parameters")
        gain_layout = QVBoxLayout()

        self.gain_a0_check = QCheckBox("Enable Gain A0")
        self.gain_a0_check.stateChanged.connect(
            lambda state: set_gain_a0_cb(bool(state))
        )
        gain_layout.addWidget(self.gain_a0_check)

        self.gain_a1_check = QCheckBox("Enable Gain A1")
        self.gain_a1_check.stateChanged.connect(
            lambda state: set_gain_a1_cb(bool(state))
        )
        gain_layout.addWidget(self.gain_a1_check)

        self.gain_a2_check = QCheckBox("Enable Gain A2")
        self.gain_a2_check.stateChanged.connect(
            lambda state: set_gain_a2_cb(bool(state))
        )
        gain_layout.addWidget(self.gain_a2_check)

        gain_group.setLayout(gain_layout)
        layout.addWidget(gain_group)

        layout.addStretch()
        self.setLayout(layout)

        # --- Scope GUI Setters ---

    def set_scope_range(self, val: float):
        self.range_spin.setValue(val)

    def set_scope_bandwidth(self, val: float):
        self.bandwidth_spin.setValue(val)

    def set_scope_coupling(self, val: str):
        self.coupling_combo.setCurrentText(val)

    def set_scope_trigger(self, val: float):
        self.trigger_spin.setValue(val)

    def set_scope_hysteresis(self, val: float):
        self.hysteresis_spin.setValue(val)

    def set_scope_sample_rate(self, val: float):
        self.sample_rate_spin.setValue(val)

    def set_scope_buffer_size(self, val: int):
        self.buffer_size_spin.setValue(val)

    # --- Wavegen GUI Setters ---
    def set_wavegen_function(self, val: str):
        self.function_combo.setCurrentText(val)

    def set_wavegen_frequency(self, val: float):
        self.frequency_spin.setValue(val)

    def set_wavegen_amplitude(self, val: float):
        self.amplitude_spin.setValue(val)

    def set_wavegen_offset(self, val: float):
        self.offset_spin.setValue(val)

    # --- Gain GUI Setters ---
    def set_gain_a0(self, val: bool):
        self.gain_a0_check.setChecked(val)

    def set_gain_a1(self, val: bool):
        self.gain_a1_check.setChecked(val)

    def set_gain_a2(self, val: bool):
        self.gain_a2_check.setChecked(val)
