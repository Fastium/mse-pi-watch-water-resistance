import os

import matplotlib.pyplot as plt
import numpy as np

from application.config import AppConfig

os.environ["ADEPT_RT_LOGDETAIL"] = "0"
os.environ["ADEPT_RT_LOGFILE"] = os.devnull
import dwfpy as dwf

# Device
SCOPE_INDEX = 0
WAVEGEN_INDEX = 0


class AD3:
    """
    Hardware driver wrapper for the Digilent Analog Discovery 3 device using dwfpy.
    Handles configuration and control of the scope, wavegen, and digital IO components.
    """

    def __init__(self):
        self.device = dwf.AnalogDiscovery3()
        self.wavegen = None
        self.scope = None
        self.io = None

        config = AppConfig()

        # scope
        self.scope_range = config.scope_range
        self.scope_bandwidth = config.scope_bandwidth
        self.scope_coupling = config.scope_coupling
        self.scope_trigger = config.scope_trigger
        self.scope_hysteresis = config.scope_hysteresis

        self.scope_sample_rate = config.scope_sample_rate
        self.scope_buffer_size = config.scope_buffer_size

        # wavegen
        self.wavegen_function = config.wavegen_function
        self.wavegen_frequency = config.wavegen_frequency
        self.wavegen_amplitude = config.wavegen_amplitude
        self.wavegen_offset = config.wavegen_offset

        # gain
        self.gain_a0 = config.gain_a0
        self.gain_a1 = config.gain_a1
        self.gain_a2 = config.gain_a2

    def open(self):
        self.device.open()
        self.wavegen = self.device.analog_output
        self.scope = self.device.analog_input
        self.io = self.device.digital_io

    def close(self):
        self.device.close()

    def setup_wavegen(self):
        if self.wavegen is None:
            raise RuntimeError("Wavegen not initialized")
        else:
            self.wavegen[WAVEGEN_INDEX].setup(
                function=self.wavegen_function,
                frequency=self.wavegen_frequency,
                amplitude=self.wavegen_amplitude,
                offset=self.wavegen_offset,
                configure=True,
                start=False,
            )

    def setup_scope(self):
        if self.scope is None:
            raise RuntimeError("Scope not initialized")
        else:
            self.scope[SCOPE_INDEX].setup(
                range=self.scope_range,
                bandwidth=self.scope_bandwidth,
                coupling=self.scope_coupling,
            )

            self.scope.setup_edge_trigger(
                mode="auto",
                channel=SCOPE_INDEX,
                slope="rising",
                level=self.scope_trigger,
                hysteresis=self.scope_hysteresis,
            )

    def start_wavegens(self):
        if self.wavegen is None:
            raise RuntimeError("Wavegen or scope not initialized")
        else:
            self.wavegen[WAVEGEN_INDEX].setup(start=True, configure=True)

    def stop_wavegen(self):
        if self.wavegen is None:
            raise RuntimeError("Wavegen or scope not initialized")
        else:
            self.wavegen[WAVEGEN_INDEX].setup(start=False, configure=True)

    def get_scope_data(self) -> np.ndarray:
        if self.scope is None:
            raise RuntimeError("Scope not initialized")

        self.setup_scope()

        self.scope.single(
            sample_rate=self.scope_sample_rate,
            buffer_size=self.scope_buffer_size,
            configure=True,
            start=True,
        )

        return np.array(self.scope[SCOPE_INDEX].get_data())

    def setup_io(self):
        if self.io is None:
            raise RuntimeError("IO not initialized")
        else:
            self.io[0].setup(enabled=True, state=self.gain_a0, configure=True)
            self.io[1].setup(enabled=True, state=self.gain_a1, configure=True)
            self.io[2].setup(enabled=True, state=self.gain_a2, configure=True)

    def set_scope_range(self, range: float):
        self.scope_range = range

    def set_scope_bandwidth(self, bandwidth: float):
        self.scope_bandwidth = bandwidth

    def set_scope_coupling(self, coupling: str):
        self.scope_coupling = coupling

    def set_scope_trigger(self, trigger: float):
        self.scope_trigger = trigger

    def set_scope_hysteresis(self, hysteresis: float):
        self.scope_hysteresis = hysteresis

    def set_scope_sample_rate(self, sample_rate: float):
        self.scope_sample_rate = sample_rate

    def set_scope_buffer_size(self, buffer_size: int):
        self.scope_buffer_size = buffer_size

    # Wavegen setters
    def set_wavegen_function(self, function: str):
        self.wavegen_function = function

    def set_wavegen_frequency(self, frequency: float):
        self.wavegen_frequency = frequency

    def set_wavegen_amplitude(self, amplitude: float):
        self.wavegen_amplitude = amplitude

    def set_wavegen_offset(self, offset: float):
        self.wavegen_offset = offset

    # Gain setters
    def set_gain_a0(self, state: bool):
        self.gain_a0 = state

    def set_gain_a1(self, state: bool):
        self.gain_a1 = state

    def set_gain_a2(self, state: bool):
        self.gain_a2 = state


def main():

    ad3 = AD3()
    ad3.open()
    ad3.setup_io()
    ad3.setup_wavegen()
    ad3.setup_scope()

    ad3.start_wavegens()

    plt.ion()
    fig, ax = plt.subplots()

    for i in range(10):
        data = ad3.get_scope_data()
        # name = "glass_witout_water_" + str(i) + ".txt"
        # np.savetxt(name, data, fmt="%f")

        ax.clear()
        ax.plot(data)
        # ax.set_ylim(-3, 3)

        plt.show()
        plt.pause(0.01)

    plt.ioff()
    plt.show()

    ad3.close()


if __name__ == "__main__":
    main()
