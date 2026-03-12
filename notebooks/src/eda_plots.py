# Imports
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Chemins et sorties
DATA_DIR = Path("data/raw/Mesures27062024")
PATTERN = "Mesures27062024_*.txt"

OUT_FIG_DIR = Path("outputs/figures/eda")
OUT_REP_DIR = Path("outputs/reports")


# Lecture fichier .txt et conversion en array numpy de float
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


# Moyenne mobile simple pour lisser un signal
def moving_average(y: np.ndarray, w: int = 21) -> np.ndarray:
    if w <= 1:
        return y.copy()
    w = min(w, len(y))
    kernel = np.ones(w) / w
    return np.convolve(y, kernel, mode="same")


# Calcul de features basiques d'un signal
def basic_features(y: np.ndarray) -> dict:
    return {
        "n": int(len(y)),
        "mean": float(np.mean(y)),
        "std": float(np.std(y)),
        "min": float(np.min(y)),
        "max": float(np.max(y)),
        "p5": float(np.percentile(y, 5)),
        "p95": float(np.percentile(y, 95)),
        "range": float(np.max(y) - np.min(y)),
        "rms": float(np.sqrt(np.mean(y**2))),
    }

# Pour créer des noms de fichiers sûrs pour les figures
def safe_name(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")

# Main
def main():
    # Création des dossiers de sortie
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_REP_DIR.mkdir(parents=True, exist_ok=True)

    # Liste des fichiers à lire
    paths = sorted(DATA_DIR.glob(PATTERN))
    if not paths:
        raise FileNotFoundError(f"Aucun fichier trouvé dans {DATA_DIR} avec {PATTERN}")

    # Lecture des signaux et calcul des features
    signals = []
    feats = []
    names = []

    for p in paths:
        y = read_signal(p)
        if len(y) == 0:
            continue
        signals.append(y)
        feats.append(basic_features(y))
        names.append(p.name)

    # Mise à longueur identique pour tous les signaux (troncature au minimum)
    min_len = min(len(y) for y in signals)
    signals = [y[:min_len] for y in signals]
    x = np.arange(min_len)

    # Export du tableau de features en CSV
    df = pd.DataFrame(feats)
    df.insert(0, "file", names)
    df.to_csv(OUT_REP_DIR / "eda_features_summary.csv", index=False)

    # Plot 1: un signal brut
    y0 = signals[0]
    plt.figure()
    plt.plot(x, y0)
    plt.title(f"Signal brut: {names[0]}")
    plt.xlabel("sample index")
    plt.ylabel("amplitude")
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / f"signal_exemple_{safe_name(names[0])}.png", dpi=200)

    # Plot 2: overlay de 30 signaux espacés
    k = min(30, len(signals))
    idx = np.linspace(0, len(signals) - 1, k, dtype=int)

    plt.figure()
    for i in idx:
        plt.plot(x, signals[i], alpha=0.35)
    plt.title(f"Overlay de {k} signaux")
    plt.xlabel("sample index")
    plt.ylabel("amplitude")
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "overlay_30_signaux.png", dpi=200)

    # Plot 3: heatmap
    M = np.vstack(signals)
    plt.figure()
    plt.imshow(M, aspect="auto")
    plt.title("Heatmap: lignes=fichiers, colonnes=samples")
    plt.xlabel("sample index")
    plt.ylabel("file index")
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "heatmap_signaux.png", dpi=200)

    # Plot 4: histogrammes de stats
    for col in ["mean", "std", "range", "max", "min"]:
        if col not in df.columns:
            continue
        plt.figure()
        plt.hist(df[col].values, bins=40)
        plt.title(f"Histogramme: {col}")
        plt.xlabel(col)
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(OUT_FIG_DIR / f"hist_{col}.png", dpi=200)

    # Plot 5: brut vs lissé
    y0_s = moving_average(y0, w=21)
    plt.figure()
    plt.plot(x, y0, alpha=0.6, label="brut")
    plt.plot(x, y0_s, label="moyenne mobile (w=21)")
    plt.title(f"Brut vs lissé: {names[0]}")
    plt.xlabel("sample index")
    plt.ylabel("amplitude")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / f"brut_vs_lisse_{safe_name(names[0])}.png", dpi=200)

    plt.close("all")

    print("OK ")
    print(f"- Figures: {OUT_FIG_DIR}")
    print(f"- Features CSV: {OUT_REP_DIR / 'eda_features_summary.csv'}")
    print(f"- Nb fichiers lus: {len(signals)}")
    print(f"- Nb samples par fichier: {min_len}")

if __name__ == "__main__":
    main()