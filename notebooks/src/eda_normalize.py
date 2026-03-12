from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

DATA_DIR = Path("data/raw/Mesures27062024")
PATTERN = "Mesures27062024_*.txt"

OUT_FIG_DIR = Path("outputs/figures/eda_normalized")

def read_signal(path: Path) -> np.ndarray:
    values = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                values.append(float(s.replace(",", ".")))
            except ValueError:
                continue
    return np.array(values, dtype=float)

def normalize_minmax(y: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    y_min = float(np.min(y))
    y_max = float(np.max(y))
    denom = (y_max - y_min)
    if abs(denom) < eps:
        return np.zeros_like(y)
    return (y - y_min) / denom

def normalize_zscore(y: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    mu = float(np.mean(y))
    sigma = float(np.std(y))
    if sigma < eps:
        return np.zeros_like(y)
    return (y - mu) / sigma

def sample_indices(n_files: int, k: int = 30) -> np.ndarray:
    k = min(k, n_files)
    return np.linspace(0, n_files - 1, k, dtype=int)

def save_overlay(signals, x, title, out_path):
    plt.figure()
    for y in signals:
        plt.plot(x, y, alpha=0.35)
    plt.title(title)
    plt.xlabel("sample index")
    plt.ylabel("amplitude")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()

def save_heatmap(matrix, title, out_path):
    plt.figure()
    plt.imshow(matrix, aspect="auto")
    plt.title(title)
    plt.xlabel("sample index")
    plt.ylabel("file index")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()

def main():
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    paths = sorted(DATA_DIR.glob(PATTERN))
    if not paths:
        raise FileNotFoundError(f"Aucun fichier trouvé dans {DATA_DIR} avec {PATTERN}")

    signals = []
    for p in paths:
        y = read_signal(p)
        if len(y) > 0:
            signals.append(y)

    min_len = min(len(y) for y in signals)
    signals = [y[:min_len] for y in signals]
    x = np.arange(min_len)

    # Sélection de 30 fichiers répartis sur tout le dataset
    idx = sample_indices(len(signals), k=30)
    raw_subset = [signals[i] for i in idx]

    # Normalisations
    minmax_subset = [normalize_minmax(y) for y in raw_subset]
    zscore_subset = [normalize_zscore(y) for y in raw_subset]

    # Overlays
    save_overlay(raw_subset, x, "Overlay (brut) - 30 signaux", OUT_FIG_DIR / "overlay_raw_30.png")
    save_overlay(minmax_subset, x, "Overlay (min-max) - 30 signaux", OUT_FIG_DIR / "overlay_minmax_30.png")
    save_overlay(zscore_subset, x, "Overlay (z-score) - 30 signaux", OUT_FIG_DIR / "overlay_zscore_30.png")

    # Heatmaps sur tout le dataset
    M_raw = np.vstack(signals)
    M_minmax = np.vstack([normalize_minmax(y) for y in signals])
    M_zscore = np.vstack([normalize_zscore(y) for y in signals])

    save_heatmap(M_raw, "Heatmap (brut) - tous les fichiers", OUT_FIG_DIR / "heatmap_raw.png")
    save_heatmap(M_minmax, "Heatmap (min-max) - tous les fichiers", OUT_FIG_DIR / "heatmap_minmax.png")
    save_heatmap(M_zscore, "Heatmap (z-score) - tous les fichiers", OUT_FIG_DIR / "heatmap_zscore.png")

    print("OK ")
    print("Regarde ces fichiers:")
    print("- outputs/figures/overlay_raw_30.png")
    print("- outputs/figures/overlay_minmax_30.png")
    print("- outputs/figures/overlay_zscore_30.png")
    print("- outputs/figures/heatmap_raw.png")
    print("- outputs/figures/heatmap_minmax.png")
    print("- outputs/figures/heatmap_zscore.png")

if __name__ == "__main__":
    main()