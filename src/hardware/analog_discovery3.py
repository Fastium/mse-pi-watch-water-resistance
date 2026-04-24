import os

import matplotlib.pyplot as plt
import numpy as np

os.environ["ADEPT_RT_LOGDETAIL"] = "0"
os.environ["ADEPT_RT_LOGFILE"] = os.devnull
import dwfpy as dwf

# Device
SCOPE_INDEX = 0
WAVEGEN_INDEX = 0


# This class provide an interface to setup the analog discovery device
class AD3:
    def __init__(self):
        self.device = dwf.AnalogDiscovery3()
        self.wavegen = None
        self.scope = None
        self.io = None

        # scope
        self.scope_range = 10
        self.scope_bandwidth = 1e3
        self.scope_coupling = "ac"
        self.scope_trigger = 1
        self.scope_hysteresis = 0.01

        self.scope_sample_rate = 300e3
        self.scope_buffer_size = 8192

        # wavegen
        self.wavegen_function = "triangle"
        self.wavegen_frequency = 50
        self.wavegen_amplitude = 200e-3
        self.wavegen_offset = -100e-3

        # gain
        self.gain_a0 = False
        self.gain_a1 = False
        self.gain_a2 = False

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

    # --- Wavegen setters ---
    def set_wavegen_function(self, function: str):
        self.wavegen_function = function

    def set_wavegen_frequency(self, frequency: float):
        self.wavegen_frequency = frequency

    def set_wavegen_amplitude(self, amplitude: float):
        self.wavegen_amplitude = amplitude

    def set_wavegen_offset(self, offset: float):
        self.wavegen_offset = offset

    # --- Gain setters ---
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
