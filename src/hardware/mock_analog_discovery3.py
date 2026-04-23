import numpy as np


class MockAD3:
    """Mock class for Analog Discovery 3 to test UI without hardware."""

    def __init__(self):
        self.is_open = False
        self.wavegen_running = False

        # scope
        self.scope_range = 10.0
        self.scope_bandwidth = 1e3
        self.scope_coupling = "ac"
        self.scope_trigger = 1.0
        self.scope_hysteresis = 0.01

        self.scope_sample_rate = 300e3
        self.scope_buffer_size = 8192

        # wavegen
        self.wavegen_function = "triangle"
        self.wavegen_frequency = 50.0
        self.wavegen_amplitude = 200e-3
        self.wavegen_offset = -100e-3

        # gain
        self.gain_a0 = False
        self.gain_a1 = False
        self.gain_a2 = False

        self.t = 0.0  # Used to simulate continuous time

    def open(self):
        print("[MockAD3] Device opened")
        self.is_open = True

    def close(self):
        print("[MockAD3] Device closed")
        self.is_open = False

    def setup_wavegen(self):
        if self.is_open:
            print(
                f"[MockAD3] SETUP WAVEGEN -> func={self.wavegen_function}, freq={self.wavegen_frequency}Hz, "
                f"amp={self.wavegen_amplitude}V, offset={self.wavegen_offset}V"
            )
        else:
            print("[MockAD3] SETUP WAVEGEN -> Device not opened")

    def setup_scope(self):
        if self.is_open:
            print(
                f"[MockAD3] SETUP SCOPE -> range={self.scope_range}V, bw={self.scope_bandwidth}Hz, "
                f"coupling={self.scope_coupling}, trigger={self.scope_trigger}V, hyst={self.scope_hysteresis}V, "
                f"sample_rate={self.scope_sample_rate}Hz, buffer_size={self.scope_buffer_size}"
            )
        else:
            print("[MockAD3] SETUP SCOPE -> Device not opened")

    def start_wavegens(self):
        if self.is_open:
            print("[MockAD3] Wavegen STARTED")
            self.wavegen_running = True
        else:
            print("[MockAD3] Wavegen STARTED -> Device not opened")

    def stop_wavegen(self):
        if self.is_open:
            print("[MockAD3] Wavegen STOPPED")
            self.wavegen_running = False
        else:
            print("[MockAD3] Wavegen STOPPED -> Device not opened")

    def get_scope_data(self) -> np.ndarray:
        import time

        if not self.is_open:
            raise RuntimeError("Device not opened")

        # --- SIMULATION DU TRIGGER ---
        # On vérifie si le niveau de trigger demandé est dans les bornes de notre signal
        while True:
            is_triggered = False
            if self.wavegen_running:
                sig_max = self.wavegen_offset + self.wavegen_amplitude
                sig_min = self.wavegen_offset - self.wavegen_amplitude
                if sig_min <= self.scope_trigger <= sig_max:
                    is_triggered = True
            else:
                # S'il n'y a que du bruit, le trigger doit être très proche de 0
                noise_amp = self.scope_range * 0.02
                if -noise_amp <= self.scope_trigger <= noise_amp:
                    is_triggered = True

            if is_triggered:
                break  # Le trigger est bon, on sort de l'attente

            print(
                f"[MockAD3] Waiting for trigger at {self.scope_trigger}V... (Signal out of bounds)"
            )
            time.sleep(
                1.0
            )  # Bloque le thread courant pendant 1 seconde avant de réessayer

        # Calculate time array for the buffer
        t_array = np.linspace(
            self.t,
            self.t + self.scope_buffer_size / self.scope_sample_rate,
            self.scope_buffer_size,
        )
        self.t = t_array[-1]  # Update time for the next call

        # Generate base signal based on wavegen settings
        if self.wavegen_running:
            if self.wavegen_function == "sine":
                signal = np.sin(2 * np.pi * self.wavegen_frequency * t_array)
            elif self.wavegen_function == "square":
                signal = np.sign(np.sin(2 * np.pi * self.wavegen_frequency * t_array))
            else:  # default to a simple sine for the mock if triangle/ramp
                signal = np.sin(2 * np.pi * self.wavegen_frequency * t_array)

            signal = signal * self.wavegen_amplitude + self.wavegen_offset
        else:
            signal = np.zeros(self.scope_buffer_size)

        # Add random noise scaled to 2% of the scope range
        noise = np.random.normal(0, self.scope_range * 0.02, self.scope_buffer_size)

        # Combine and clip the data to the scope limits (-range to +range)
        data = np.clip(signal + noise, -self.scope_range, self.scope_range)

        return data

    def setup_io(self):
        if self.is_open:
            print(
                f"[MockAD3] SETUP IO -> A0={self.gain_a0}, A1={self.gain_a1}, A2={self.gain_a2}"
            )
        else:
            print("[MockAD3] SETUP IO -> Device not opened")

    # Setters
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

    def set_wavegen_function(self, function: str):
        self.wavegen_function = function

    def set_wavegen_frequency(self, frequency: float):
        self.wavegen_frequency = frequency

    def set_wavegen_amplitude(self, amplitude: float):
        self.wavegen_amplitude = amplitude

    def set_wavegen_offset(self, offset: float):
        self.wavegen_offset = offset

    def set_gain_a0(self, state: bool):
        self.gain_a0 = state

    def set_gain_a1(self, state: bool):
        self.gain_a1 = state

    def set_gain_a2(self, state: bool):
        self.gain_a2 = state
