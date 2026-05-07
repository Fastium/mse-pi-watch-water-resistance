import numpy as np
import scipy.signal

from application.config import AppConfig


class MockAD3:
    """Mock class for Analog Discovery 3 to test UI without hardware."""

    def __init__(self):
        self.is_open = False
        self.wavegen_running = False

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

        self.t = 0.0  # Used to simulate continuous time (untriggered mode)

    def open(self):
        print("[MockAD3] Device opened")
        self.is_open = True

    def close(self):
        print("[MockAD3] Device closed")
        self.is_open = False

    def setup_wavegen(self):
        if self.is_open:
            pass  # Keep terminal clean
        else:
            print("[MockAD3] SETUP WAVEGEN -> Device not opened")

    def setup_scope(self):
        if self.is_open:
            pass  # Keep terminal clean
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
        if not self.is_open:
            raise RuntimeError("Device not opened")

        import time

        # Simulate hardware delay for data acquisition
        time.sleep(0.02)

        is_triggered = False
        v_norm = 0.0

        # --- MATH TRIGGER STRATEGY ---
        if self.wavegen_running and self.wavegen_amplitude > 0:
            # Check if trigger level is within the wavegen signal bounds
            v_norm = (self.scope_trigger - self.wavegen_offset) / self.wavegen_amplitude
            if -1.0 <= v_norm <= 1.0:
                is_triggered = True
        elif not self.wavegen_running:
            # If no signal, trigger only on pure noise around 0V
            noise_amp = self.scope_range * 0.002
            if -noise_amp <= self.scope_trigger <= noise_amp:
                is_triggered = True

        duration = self.scope_buffer_size / self.scope_sample_rate

        if is_triggered and self.wavegen_running:
            # Calculate the exact phase where the signal crosses the trigger level
            if self.wavegen_function == "sine":
                phase_trig = np.arcsin(v_norm)
            elif self.wavegen_function == "square":
                phase_trig = 0.0 if v_norm >= 0 else np.pi
            elif self.wavegen_function == "triangle":
                phase_trig = v_norm * (np.pi / 2)
            else:
                phase_trig = np.arcsin(v_norm)

            # Convert phase to time, and offset it so the trigger point is at the center of the screen1
            t_trig = (
                phase_trig / (2 * np.pi * self.wavegen_frequency)
                if self.wavegen_frequency > 0
                else 0
            )

            t_start = t_trig - (duration / 2)  # Center the buffer around t_trig
            t_array = np.linspace(
                t_start, t_start + duration, self.scope_buffer_size, endpoint=False
            )
        else:
            # Untriggered Mode (Free Run / Auto) -> The wave will visually scroll
            t_array = np.linspace(
                self.t, self.t + duration, self.scope_buffer_size, endpoint=False
            )
            self.t = t_array[-1]

        # Generate base signal
        if self.wavegen_running:
            if self.wavegen_function == "sine":
                signal = np.sin(2 * np.pi * self.wavegen_frequency * t_array)
            elif self.wavegen_function == "square":
                signal = scipy.signal.square(
                    2 * np.pi * self.wavegen_frequency * t_array
                )
            elif self.wavegen_function == "triangle":
                # Le paramètre 0.5 indique qu'il s'agit d'un triangle symétrique
                signal = scipy.signal.sawtooth(
                    2 * np.pi * self.wavegen_frequency * t_array, width=0.5
                )
            else:
                signal = np.sin(2 * np.pi * self.wavegen_frequency * t_array)

            signal = signal * self.wavegen_amplitude + self.wavegen_offset

        # Add random noise scaled to 2% of the scope range
        noise = np.random.normal(0, self.scope_range, self.scope_buffer_size) * 0.02
        data = np.clip(signal + noise, -self.scope_range, self.scope_range)

        return data

    def setup_io(self):
        if not self.is_open:
            print("[MockAD3] SETUP IO -> Device not opened")

    # --- Scope Setters (Protected during run) ---
    def set_scope_range(self, range_val: float):
        if self.wavegen_running:
            return
        self.scope_range = range_val

    def set_scope_bandwidth(self, bandwidth: float):
        if self.wavegen_running:
            return
        self.scope_bandwidth = bandwidth

    def set_scope_coupling(self, coupling: str):
        if self.wavegen_running:
            return
        self.scope_coupling = coupling

    def set_scope_trigger(self, trigger: float):
        if self.wavegen_running:
            return
        self.scope_trigger = trigger

    def set_scope_hysteresis(self, hysteresis: float):
        if self.wavegen_running:
            return
        self.scope_hysteresis = hysteresis

    def set_scope_sample_rate(self, sample_rate: float):
        if self.wavegen_running:
            return
        self.scope_sample_rate = sample_rate

    def set_scope_buffer_size(self, buffer_size: int):
        if self.wavegen_running:
            return
        self.scope_buffer_size = buffer_size

    # --- Wavegen & Gain setters ---
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
