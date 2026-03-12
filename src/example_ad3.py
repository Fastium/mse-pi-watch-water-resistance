import matplotlib.pyplot as plt
import os

# Deactivate log runtime Digilent Adept
# must be set before importing dwfpy
os.environ["ADEPT_RT_LOGDETAIL"] = "0"
os.environ["ADEPT_RT_LOGFILE"] = os.devnull
import dwfpy as dwf


def main():

    device =  dwf.AnalogDiscovery3()

    device.open()

    print(f"Found an Analog Discovery 3: {device.user_name} ({device.serial_number})")

    wavegen = device.analog_output
    wavegen[0].setup(function="triangle", frequency=1e3, amplitude=1.0, start=True)

    scope = device.analog_input
    scope[0].setup(range=2.0)
    scope.single(sample_rate=1e6, buffer_size=4096, configure=True, start=True)

    # input("Waiting for acquisition to complete... Press Enter to continue.")

    samples = scope[0].get_data()

    plt.plot(samples)
    plt.show()

    device.close()


    print(samples)


if __name__ == "__main__":
    main()
