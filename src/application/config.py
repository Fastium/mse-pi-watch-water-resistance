from dataclasses import dataclass
from pickle import FALSE


@dataclass
class AppConfig:
    simulation = False

    # Scope
    scope_range: float = 2.0
    scope_bandwidth: float = 300e3
    scope_coupling: str = "ac"
    scope_trigger: float = 0.4
    scope_hysteresis: float = 0.1
    scope_sample_rate: float = 300e3
    scope_buffer_size: int = 8192

    # Wavegen
    wavegen_function: str = "triangle"
    wavegen_frequency: float = 50.0
    wavegen_amplitude: float = 1.5
    wavegen_offset: float = 0.0

    # Gain
    gain_a0: bool = False
    gain_a1: bool = False
    gain_a2: bool = False
