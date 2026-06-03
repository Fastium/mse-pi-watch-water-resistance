# mse-pi-watch-water-resistance


This project focuses on developing a non-destructive optical measurement system using an infrared laser to detect moisture inside watch cases. Ensuring water resistance is crucial to prevent internal condensation and protect delicate components without needing to disassemble the watch.

The scope of the project encompasses:
* **Mechanical Design:** Creating mounts for the optical components.
* **Optical Analysis:** Studying the laser beam path.
* **Signal Processing:** Acquiring and processing data from the optical system.
* **Environmental Compensation:** Mitigating the impact of external ambient humidity to maintain measurement accuracy.

## Usage

Install the tool `uv` via [the website](https://docs.astral.sh/uv/getting-started/installation/)

Synchonise the dependencies (it creates automatically the python venv):

```bash
$ uv sync
```

Run the programm:
```bash
$ uv run ./src/main
```

## Setup

The configuration can be done in the file `src/application/appconfig.py`. It contains a class with all constants for the project.

If you don't have any Analog discovery, you can configure it with a mock:
```python
simulation = True
```

## Waveforms

A panel to vizualize in [Waveforms](https://digilent.com/shop/waveforms/) in the folder `waveforms/`.
