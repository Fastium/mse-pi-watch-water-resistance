import os
import time

import numpy as np


def export_txt(data: np.ndarray, path: str, filename: str):
    # test if the path exists, if not, create it
    if not os.path.exists(path):
        os.makedirs(path)

    full_path = os.path.join(path, filename)

    print(f"Exporting to {full_path}")
    np.savetxt(full_path, data, fmt="%f", delimiter="\n")
