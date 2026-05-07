import numpy as np


def export_txt(data: np.ndarray, filename: str):
    print(f"Exporting to {filename}")
    np.savetxt(filename, data, fmt="%f", delimiter="\n")
