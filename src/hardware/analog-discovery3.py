import os
import time

import matplotlib.pyplot as plt
import numpy as np

os.environ["ADEPT_RT_LOGDETAIL"] = "0"
os.environ["ADEPT_RT_LOGFILE"] = os.devnull
import dwfpy as dwf

# Device
SCOPE_INDEX = 0
WAVEGEN_INDEX = 0


class AD3:
    def __init__(self):
        self.device = dwf.AnalogDiscovery3()
        self.wavegen = None
        self.scope = None
        self.io = None

    def open(self):
        self.device.open()
        self.wavegen = self.device.analog_output
        self.scope = self.device.analog_input
        self.io = self.device.digital_io

    def close(self):
        self.device.close()

    def setup_wavegen(
        self,
        function: str = "triangle",
        frequence: float = 50,
        amplitude: float = 100e-3,
        offset: float = -70e-3,
    ):

        if self.wavegen is None:
            raise RuntimeError("Wavegen not initialized")
        else:
            self.wavegen[WAVEGEN_INDEX].setup(
                function=function,
                frequency=frequence,
                amplitude=amplitude,
                offset=offset,
                start=False,
            )

    def setup_scope(
        self,
        range: float = 10,
        bandwidth: float = 1e3,
        coupling: str = "ac",
    ):
        if self.scope is None:
            raise RuntimeError("Scope not initialized")
        else:
            self.scope[SCOPE_INDEX].setup(
                range=range,
                bandwidth=bandwidth,
                coupling=coupling,
            )
            self.scope.setup_edge_trigger(
                mode="normal",
                channel=SCOPE_INDEX,
                slope="rising",
                level=1,
                hysteresis=0.1,
            )

    def start_wavegens(self):
        if self.wavegen is None:
            raise RuntimeError("Wavegen or scope not initialized")
        else:
            self.wavegen[WAVEGEN_INDEX].setup(start=True)

    def get_scope_data(self) -> np.ndarray:
        if self.scope is None:
            raise RuntimeError("Scope not initialized")

        self.scope.single(
            sample_rate=300e3, buffer_size=8192, configure=True, start=True
        )

        return np.array(self.scope[SCOPE_INDEX].get_data())

    def setup_io(self):
        if self.io is None:
            raise RuntimeError("IO not initialized")
        else:
            self.io[0].setup(enabled=True, state=False)
            self.io[1].setup(enabled=True, state=False)
            self.io[2].setup(enabled=True, state=False)


def main():
    ad3 = AD3()
    ad3.open()
    ad3.setup_wavegen()
    ad3.setup_scope()
    ad3.start_wavegens()

    plt.ion()
    fig, ax = plt.subplots()

    for i in range(1000):
        data = ad3.get_scope_data()
        ax.clear()
        ax.plot(data)
        ax.set_ylim(-3, 3)

        plt.show()
        plt.pause(0.001)

    plt.ioff()

    ad3.close()


if __name__ == "__main__":
    main()
