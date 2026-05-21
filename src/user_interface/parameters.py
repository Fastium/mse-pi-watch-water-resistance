# src/user_interface/parameters.py
from PySide6.QtCore import Signal
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

from application.config import AppConfig


class ParametersPanel(QWidget):
    # --- Déclaration des Signaux ---
    range_changed = Signal(float)
    bandwidth_changed = Signal(float)
    coupling_changed = Signal(str)
    trigger_changed = Signal(float)
    trigger_hysteresis_changed = Signal(float)
    sample_rate_changed = Signal(float)
    buffer_size_changed = Signal(int)

    wavegen_function_changed = Signal(str)
    wavegen_frequency_changed = Signal(float)
    wavegen_amplitude_changed = Signal(float)
    wavegen_offset_changed = Signal(float)

    gain_a0_changed = Signal(bool)
    gain_a1_changed = Signal(bool)
    gain_a2_changed = Signal(bool)

    def __init__(self, config: AppConfig):
        super().__init__()

        layout = QVBoxLayout()

        # --- SCOPE PARAMETERS ---
        scope_group = QGroupBox("Scope Parameters")
        scope_layout = QFormLayout()

        self.range_spin = QDoubleSpinBox()
        self.range_spin.setRange(0.0, 10.0)
        self.range_spin.setSingleStep(0.1)
        self.range_spin.setValue(config.scope_range)
        self.range_spin.valueChanged.connect(self.range_changed.emit)
        scope_layout.addRow("Range:", self.range_spin)

        self.bandwidth_spin = QDoubleSpinBox()
        self.bandwidth_spin.setRange(0.0, 100e6)
        self.bandwidth_spin.setSingleStep(100e3)
        self.bandwidth_spin.setValue(config.scope_bandwidth)
        self.bandwidth_spin.valueChanged.connect(self.bandwidth_changed.emit)
        scope_layout.addRow("Bandwidth:", self.bandwidth_spin)

        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(["dc", "ac"])
        self.coupling_combo.setCurrentText(config.scope_coupling)
        self.coupling_combo.currentTextChanged.connect(self.coupling_changed.emit)
        scope_layout.addRow("Coupling:", self.coupling_combo)

        self.trigger_spin = QDoubleSpinBox()
        self.trigger_spin.setRange(-10.0, 10)
        self.trigger_spin.setSingleStep(0.01)
        self.trigger_spin.setValue(config.scope_trigger)
        self.trigger_spin.valueChanged.connect(self.trigger_changed.emit)
        scope_layout.addRow("Trigger (V):", self.trigger_spin)

        self.hysteresis_spin = QDoubleSpinBox()
        self.hysteresis_spin.setRange(0.0, 5.0)
        self.hysteresis_spin.setSingleStep(0.1)
        self.hysteresis_spin.setValue(config.scope_hysteresis)
        self.hysteresis_spin.valueChanged.connect(self.trigger_hysteresis_changed.emit)
        scope_layout.addRow("Trigger Hysteresis (V):", self.hysteresis_spin)

        self.sample_rate_spin = QDoubleSpinBox()
        self.sample_rate_spin.setRange(1.0, 100e6)
        self.sample_rate_spin.setSingleStep(1.0e4)
        self.sample_rate_spin.setValue(config.scope_sample_rate)
        self.sample_rate_spin.valueChanged.connect(self.sample_rate_changed.emit)
        scope_layout.addRow("Sample Rate (Hz):", self.sample_rate_spin)

        self.buffer_size_spin = QSpinBox()
        self.buffer_size_spin.setRange(1, 32768)
        self.buffer_size_spin.setSingleStep(25)
        self.buffer_size_spin.setValue(config.scope_buffer_size)
        self.buffer_size_spin.valueChanged.connect(self.buffer_size_changed.emit)
        scope_layout.addRow("Buffer Size:", self.buffer_size_spin)

        scope_group.setLayout(scope_layout)
        layout.addWidget(scope_group)

        # --- WAVEGEN PARAMETERS ---
        wavegen_group = QGroupBox("Wavegen Parameters")
        wavegen_layout = QFormLayout()

        self.function_combo = QComboBox()
        self.function_combo.addItems(["sine", "square", "triangle"])
        self.function_combo.setCurrentText(config.wavegen_function)
        self.function_combo.currentTextChanged.connect(
            self.wavegen_function_changed.emit
        )
        wavegen_layout.addRow("Function:", self.function_combo)

        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(0.1, 10e6)
        self.frequency_spin.setValue(config.wavegen_frequency)
        self.frequency_spin.valueChanged.connect(self.wavegen_frequency_changed.emit)
        wavegen_layout.addRow("Frequency (Hz):", self.frequency_spin)

        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(0.0, 5.0)
        self.amplitude_spin.setValue(config.wavegen_amplitude)
        self.amplitude_spin.valueChanged.connect(self.wavegen_amplitude_changed.emit)
        wavegen_layout.addRow("Amplitude (V):", self.amplitude_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-5.0, 5.0)
        self.offset_spin.setValue(config.wavegen_offset)
        self.offset_spin.valueChanged.connect(self.wavegen_offset_changed.emit)
        wavegen_layout.addRow("Offset (V):", self.offset_spin)

        wavegen_group.setLayout(wavegen_layout)
        layout.addWidget(wavegen_group)

        # --- GAIN PARAMETERS ---
        gain_group = QGroupBox("Gain IO Parameters")
        gain_layout = QVBoxLayout()

        self.gain_a0_check = QCheckBox("Enable Gain A0")
        self.gain_a0_check.setChecked(config.gain_a0)
        self.gain_a0_check.toggled.connect(self.gain_a0_changed.emit)
        gain_layout.addWidget(self.gain_a0_check)

        self.gain_a1_check = QCheckBox("Enable Gain A1")
        self.gain_a1_check.setChecked(config.gain_a1)
        self.gain_a1_check.toggled.connect(self.gain_a1_changed.emit)
        gain_layout.addWidget(self.gain_a1_check)

        self.gain_a2_check = QCheckBox("Enable Gain A2")
        self.gain_a2_check.setChecked(config.gain_a2)
        self.gain_a2_check.toggled.connect(self.gain_a2_changed.emit)
        gain_layout.addWidget(self.gain_a2_check)

        gain_group.setLayout(gain_layout)
        layout.addWidget(gain_group)

        layout.addStretch()
        self.setLayout(layout)
