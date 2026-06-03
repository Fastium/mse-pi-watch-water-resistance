from application.config import AppConfig
from hardware.analog_discovery3 import AD3
from hardware.mock_analog_discovery3 import MockAD3


class Controller:
    """
    Middleware layer that acts as an interface between the application logic and the hardware.
    Instantiates the real or mock Analog Discovery 3 (AD3) based on configuration.
    """

    def __init__(self):

        if AppConfig.simulation:
            self.ad3 = MockAD3()
        else:
            self.ad3 = AD3()

    def connect(self):
        """Opens the connection to the hardware device."""
        print("Connect")
        self.ad3.open()

    def setup(self):
        """Configures the Digital I/O, Wavegen, and Scope on the hardware."""
        print("Setup")
        self.ad3.setup_io()
        self.ad3.setup_wavegen()
        self.ad3.setup_scope()

    def disconnect(self):
        """Stops hardware components safely and closes the connection."""
        print("Close")
        self.ad3.stop_wavegen()
        self.ad3.close()

    def start(self):
        print("Start")
        self.ad3.start_wavegens()

    def get_scope_data(self):
        return self.ad3.get_scope_data()

    def stop(self):
        print("Stop")
        self.ad3.stop_wavegen()

    # Scope setters
    def set_scope_range(self, range_val: float):
        self.ad3.set_scope_range(range_val)

    def set_scope_bandwidth(self, bandwidth: float):
        self.ad3.set_scope_bandwidth(bandwidth)

    def set_scope_coupling(self, coupling: str):
        self.ad3.set_scope_coupling(coupling)

    def set_scope_trigger(self, trigger: float):
        self.ad3.set_scope_trigger(trigger)

    def set_scope_hysteresis(self, hysteresis: float):
        self.ad3.set_scope_hysteresis(hysteresis)

    def set_scope_sample_rate(self, sample_rate: float):
        self.ad3.set_scope_sample_rate(sample_rate)

    def set_scope_buffer_size(self, buffer_size: int):
        self.ad3.set_scope_buffer_size(buffer_size)

    # Wavegen setters
    def set_wavegen_function(self, function: str):
        self.ad3.set_wavegen_function(function)
        self.ad3.setup_wavegen()
        self.ad3.start_wavegens()

    def set_wavegen_frequency(self, frequency: float):
        self.ad3.set_wavegen_frequency(frequency)
        self.ad3.setup_wavegen()
        self.ad3.start_wavegens()

    def set_wavegen_amplitude(self, amplitude: float):
        self.ad3.set_wavegen_amplitude(amplitude)
        self.ad3.setup_wavegen()
        self.ad3.start_wavegens()

    def set_wavegen_offset(self, offset: float):
        self.ad3.set_wavegen_offset(offset)
        self.ad3.setup_wavegen()
        self.ad3.start_wavegens()

    # Gain setters
    def set_gain_a0(self, state: bool):
        self.ad3.set_gain_a0(state)
        self.ad3.setup_io()

    def set_gain_a1(self, state: bool):
        self.ad3.set_gain_a1(state)
        self.ad3.setup_io()

    def set_gain_a2(self, state: bool):
        self.ad3.set_gain_a2(state)
        self.ad3.setup_io()
