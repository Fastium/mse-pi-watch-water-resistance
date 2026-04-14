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


# This class provide an interface to setup the analog discovery device
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
        amplitude: float = 200e-3,
        offset: float = -100e-3,
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
        trigger: float = 1,
        hysteresis: float = 0.01,
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
                level=trigger,
                hysteresis=hysteresis,
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

    def setup_io(self, A2: bool = True, A1: bool = True, A0: bool = True):
        if self.io is None:
            raise RuntimeError("IO not initialized")
        else:
            self.io[0].setup(enabled=True, state=A0, configure=True)
            self.io[1].setup(enabled=True, state=A1, configure=True)
            self.io[2].setup(enabled=True, state=A2, configure=True)


def main():

    ad3 = AD3()
    ad3.open()
    ad3.setup_io(False, True, False)
    ad3.setup_wavegen()
    ad3.setup_scope(trigger=0.2, hysteresis=0.05)

    ad3.start_wavegens()

    plt.ion()
    fig, ax = plt.subplots()

    for i in range(10000):
        data = ad3.get_scope_data()
        name = "glass_with_water_" + str(i) + ".txt"
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
