from dataclasses import dataclass


@dataclass
class AppConfig:
    # Enable mock for simulation
    simulation = True

    # Calibration
    calibration_measurements: int = 100
    calibration_output: str = "calibration-files"

    # Scope
    scope_range: float = 2.0
    scope_bandwidth: float = 300e3
    scope_coupling: str = "ac"
    scope_trigger: float = 0.6
    scope_hysteresis: float = 0.05
    scope_sample_rate: float = 440000.0
    scope_buffer_size: int = 9200

    # Wavegen
    wavegen_function: str = "triangle"
    wavegen_frequency: float = 50.0
    wavegen_amplitude: float = 1.5
    wavegen_offset: float = 0.0

    # Gain
    gain_a0: bool = False
    gain_a1: bool = False
    gain_a2: bool = False

    # HA Plot Configuration
    ha_averaging_window: int = 1
