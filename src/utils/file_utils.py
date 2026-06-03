import os

import numpy as np


def export_txt(data: np.ndarray, path: str, filename: str):
    # test if the path exists, if not, create it
    if not os.path.exists(path):
        os.makedirs(path)

    full_path = os.path.join(path, filename)

    print(f"Exporting to {full_path}")
    np.savetxt(full_path, data, fmt="%f", delimiter="\n")


def export_csv_lines(header: str, lines: list[str], path: str, filename: str):
    """Exports a list of formatted strings to a file with an optional header."""
    if not os.path.exists(path):
        os.makedirs(path)

    full_path = os.path.join(path, filename)
    print(f"Exporting HA data to {full_path}")

    with open(full_path, "w", encoding="utf-8") as f:
        if header:
            f.write(header + "\n")
        for line in lines:
            f.write(line + "\n")
