from __future__ import annotations

"""
Pipeline complet "laser -> HA" pour le projet PI etancheite.

Ce script:
1) lit les scans laser (.txt), construit I0(t), puis A(t),
2) extrait des features robustes sur A(t),
3) aligne scans et log bouton (index shift / temps / DTW),
4) calibre HA_ref ~ feature (sans temperature par defaut),
5) exporte CSV + figures de controle.

Usage standard (recommandé):
    python src/laser_matching_calibration.py

Option temperature (si besoin plus tard):
    python src/laser_matching_calibration.py --with-temperature
"""

import argparse
import os
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

# Avoid backend/cache issues in headless environments.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA_DIR = Path("data/raw/Mesures27062024")
XLSX_PATH = DATA_DIR / "HYGROBOUTON_LOCLE_DAS.xlsx"
SUMMARY_PATH = DATA_DIR / "Calibration27062024_summary.txt"
SIGNAL_PATTERN = "Mesures27062024_*.txt"

OUT_FIG_DIR = Path("outputs/figures/calibration")
OUT_REP_DIR = Path("outputs/reports")

# Choix metier: calibration sans temperature par defaut.
USE_TEMPERATURE_DEFAULT = False


def read_signal(path: Path) -> np.ndarray:
    """Lit un scan laser .txt et retourne I(t) en float."""
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


def moving_average_reflect(x: np.ndarray, window: int) -> np.ndarray:
    """Moyenne mobile avec padding miroir pour limiter les effets de bord."""
    if window % 2 == 0:
        raise ValueError("window must be odd")
    pad = window // 2
    x_pad = np.pad(x, pad_width=pad, mode="reflect")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(x_pad, kernel, mode="valid")


def compute_I0(I: np.ndarray, smooth_window: int = 41, k: float = 0.20) -> np.ndarray:
    """
    Construit la baseline triangulaire I0(t) a partir de I(t).

    Etapes:
    - separation gauche/droite autour du pic global,
    - selection des points "propres" via un critere quantile,
    - fit lineaire gauche + fit lineaire droite,
    - jonction a l'intersection des 2 droites,
    - contrainte I0 >= I pour eviter A negative.
    """
    t = np.arange(I.size, dtype=float)
    p = int(np.argmax(I))

    I_s = moving_average_reflect(I, smooth_window)
    D = I_s - I
    thr = np.quantile(D, 1 - k)
    good = D < thr

    left = (t <= p) & good
    right = (t >= p) & good
    if left.sum() < 10 or right.sum() < 10:
        raise ValueError("Not enough points for robust baseline fit.")

    coef_left = np.polyfit(t[left], I[left], deg=1)
    coef_right = np.polyfit(t[right], I[right], deg=1)

    m1, b1 = coef_left
    m2, b2 = coef_right
    if abs(m1 - m2) < 1e-12:
        p_join = p
    else:
        t_star = (b2 - b1) / (m1 - m2)
        p_join = int(np.clip(round(t_star), 1, I.size - 2))

    I0_left = np.polyval(coef_left, t)
    I0_right = np.polyval(coef_right, t)

    I0 = np.empty_like(I, dtype=float)
    I0[:p_join] = I0_left[:p_join]
    I0[p_join:] = I0_right[p_join:]
    I0 = np.maximum(I0, I)
    return I0


def compute_A_full(I: np.ndarray, I0: np.ndarray) -> np.ndarray:
    """Calcule l'absorbance point a point: A = -ln(I/I0)."""
    eps = 1e-9
    return -np.log(np.clip(I, eps, None) / np.clip(I0, eps, None))


def _contiguous_true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Retourne les segments contigus [start, end) ou mask vaut True."""
    if not np.any(mask):
        return []
    idx = np.flatnonzero(mask)
    splits = np.where(np.diff(idx) > 1)[0] + 1
    groups = np.split(idx, splits)
    return [(int(g[0]), int(g[-1]) + 1) for g in groups if g.size > 0]


def extract_features(A_full: np.ndarray, edge: int = 20) -> dict[str, float]:
    """
    Extrait des features robustes depuis A(t).

    - quantiles hauts (p95/p99),
    - aire totale / moyenne,
    - aire du top 10%,
    - ROI principale (segment le plus "energetique" au-dessus du q90).
    """
    A_use = A_full[edge:-edge] if A_full.size > 2 * edge else A_full
    if A_use.size == 0:
        A_use = A_full

    q90 = float(np.quantile(A_use, 0.90))
    q95 = float(np.quantile(A_use, 0.95))
    q99 = float(np.quantile(A_use, 0.99))

    high_mask = A_use >= q90
    runs = _contiguous_true_runs(high_mask)

    if runs:
        run_scores = [float(np.sum(A_use[s:e] - q90)) for s, e in runs]
        best = int(np.argmax(run_scores))
        s0, e0 = runs[best]
        pad = 12
        s1 = max(0, s0 - pad)
        e1 = min(A_use.size, e0 + pad)
        roi = A_use[s1:e1]
    else:
        roi = A_use

    return {
        "F_area_total": float(np.sum(A_use)),
        "F_mean": float(np.mean(A_use)),
        "F_p95": q95,
        "F_p99": q99,
        "F_top10_area": float(np.sum(np.clip(A_use - q90, 0, None))),
        "F_main_roi_area": float(np.sum(roi)),
        "F_main_roi_mean": float(np.mean(roi)),
        "F_main_roi_peak": float(np.max(roi)),
    }


def build_laser_features() -> pd.DataFrame:
    """Construit le tableau de features pour tous les scans disponibles."""
    paths = sorted(
        DATA_DIR.glob(SIGNAL_PATTERN),
        key=lambda p: int(p.stem.split("_")[-1]),
    )
    if not paths:
        raise FileNotFoundError(f"No signal found under {DATA_DIR} with {SIGNAL_PATTERN}")

    rows = []
    # Pipeline scan par scan: lecture -> baseline -> absorbance -> features.
    for p in paths:
        scan_id = int(p.stem.split("_")[-1])
        I = read_signal(p)
        I0 = compute_I0(I, smooth_window=41, k=0.20)
        A_full = compute_A_full(I, I0)

        feat = extract_features(A_full, edge=20)
        rows.append({"scan_id": scan_id, **feat})

    return pd.DataFrame(rows).sort_values("scan_id").reset_index(drop=True)


def _excel_col_to_idx(col: str) -> int:
    """Convertit une colonne Excel (A, B, AA...) en index 0-based."""
    v = 0
    for ch in col:
        v = v * 26 + (ord(ch) - ord("A") + 1)
    return v - 1


def _parse_xlsx_sheet_1(path: Path) -> pd.DataFrame:
    """
    Parse sheet1 d'un .xlsx via XML (sans openpyxl).

    Utilise aussi les styles de cellule pour reconnaitre les dates/heures.
    """
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    with ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sroot.findall("a:si", ns):
                text = "".join(t.text or "" for t in si.findall(".//a:t", ns))
                shared.append(text)

        style_root = ET.fromstring(z.read("xl/styles.xml"))
        style_to_numfmt = []
        cellxfs = style_root.find("a:cellXfs", ns)
        if cellxfs is not None:
            for xf in cellxfs.findall("a:xf", ns):
                style_to_numfmt.append(int(xf.attrib.get("numFmtId", "0")))

        custom_numfmt = {}
        numfmts = style_root.find("a:numFmts", ns)
        if numfmts is not None:
            for numfmt in numfmts.findall("a:numFmt", ns):
                numfmt_id = int(numfmt.attrib["numFmtId"])
                custom_numfmt[numfmt_id] = (numfmt.attrib.get("formatCode") or "").lower()

        date_numfmt = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
        date_style_ids = set()
        for style_id, numfmt_id in enumerate(style_to_numfmt):
            if numfmt_id in date_numfmt:
                date_style_ids.add(style_id)
                continue
            code = custom_numfmt.get(numfmt_id, "")
            if any(tok in code for tok in ["yy", "dd", "hh", "ss"]):
                date_style_ids.add(style_id)

        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        max_col_idx = 0
        for row in root.findall(".//a:sheetData/a:row", ns):
            rid = int(row.attrib["r"])
            out = {"_row": rid}
            for cell in row.findall("a:c", ns):
                ref = cell.attrib["r"]
                col = "".join(ch for ch in ref if ch.isalpha())
                col_idx = _excel_col_to_idx(col)
                max_col_idx = max(max_col_idx, col_idx)

                style_id = int(cell.attrib.get("s", "0"))
                cell_type = cell.attrib.get("t")
                v = cell.find("a:v", ns)
                if v is None or v.text is None:
                    value = ""
                else:
                    txt = v.text
                    if cell_type == "s":
                        value = shared[int(txt)] if txt.isdigit() else txt
                    elif cell_type == "b":
                        value = txt == "1"
                    else:
                        if style_id in date_style_ids:
                            try:
                                serial = float(txt)
                                value = pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")
                            except Exception:
                                value = txt
                        else:
                            try:
                                value = float(txt)
                            except ValueError:
                                value = txt
                out[col] = value
            rows.append(out)

    cols = []
    for idx in range(max_col_idx + 1):
        if idx < 26:
            cols.append(chr(ord("A") + idx))
        else:
            q = idx // 26 - 1
            r = idx % 26
            cols.append(chr(ord("A") + q) + chr(ord("A") + r))

    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    return df.sort_values("_row").reset_index(drop=True)


def read_button_log_xlsx(path: Path, header_row: int = 9) -> pd.DataFrame:
    """
    Lit le log bouton et retourne un DataFrame normalise:
    btn_dt, T, HA_ref, Abs_ref, btn_idx.
    """
    if not path.exists():
        raise FileNotFoundError(path)

    raw = _parse_xlsx_sheet_1(path)
    header = raw.loc[raw["_row"] == header_row]
    if header.empty:
        raise ValueError(f"Header row {header_row} not found in {path}")
    header = header.iloc[0]

    rename_map = {}
    for col in raw.columns:
        if col == "_row":
            continue
        val = header.get(col, "")
        if pd.isna(val):
            continue
        name = str(val).strip()
        if name:
            rename_map[col] = name

    df = raw.loc[raw["_row"] > header_row].rename(columns=rename_map).copy()
    required = ["Date", "Heure", "Température", "Ha (g/m3)", "Absorbance"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in button log: {missing}")

    date_col = df["Date"]
    time_col = df["Heure"]

    if np.issubdtype(date_col.dtype, np.datetime64):
        date_str = pd.to_datetime(date_col, errors="coerce").dt.strftime("%d/%m/%Y")
    else:
        date_str = date_col.astype(str).str.strip()

    if np.issubdtype(time_col.dtype, np.datetime64):
        time_str = pd.to_datetime(time_col, errors="coerce").dt.strftime("%H:%M:%S")
    else:
        time_str = time_col.astype(str).str.strip()
        has_date = time_str.str.contains(" ", na=False)
        if has_date.any():
            time_str.loc[has_date] = pd.to_datetime(
                time_str.loc[has_date], errors="coerce"
            ).dt.strftime("%H:%M:%S")

    dt = pd.to_datetime(date_str + " " + time_str, dayfirst=True, errors="coerce")

    out = pd.DataFrame(
        {
            "btn_dt": dt,
            "T": pd.to_numeric(df["Température"], errors="coerce"),
            "HA_ref": pd.to_numeric(df["Ha (g/m3)"], errors="coerce"),
            "Abs_ref": pd.to_numeric(df["Absorbance"], errors="coerce"),
        }
    )
    out = out.dropna(subset=["btn_dt", "T", "HA_ref", "Abs_ref"]).reset_index(drop=True)
    out["btn_idx"] = np.arange(len(out))
    return out


def read_summary(path: Path) -> pd.DataFrame:
    """Lit Calibration27062024_summary.txt (timestamp + absorbance summary)."""
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, sep="\t", header=None, names=["scan_dt", "summary_abs"])
    df["scan_dt"] = pd.to_datetime(df["scan_dt"], format="%d.%m.%Y %H:%M:%S")
    df["summary_abs"] = pd.to_numeric(df["summary_abs"], errors="coerce")
    df["scan_id"] = np.arange(len(df))
    return df.dropna(subset=["scan_dt", "summary_abs"]).reset_index(drop=True)


def corr_safe(x: pd.Series, y: pd.Series) -> float:
    """Corr robuste: ignore NaN et evite les cas sans variance."""
    x = pd.to_numeric(x, errors="coerce")
    y = pd.to_numeric(y, errors="coerce")
    mask = x.notna() & y.notna()
    if mask.sum() < 10:
        return float("nan")
    xx = x[mask].to_numpy(dtype=float)
    yy = y[mask].to_numpy(dtype=float)
    if np.std(xx) < 1e-12 or np.std(yy) < 1e-12:
        return float("nan")
    return float(np.corrcoef(xx, yy)[0, 1])


def compute_feature_correlations(
    aligned: pd.DataFrame, feature_cols: list[str]
) -> pd.DataFrame:
    """Calcule corr(feature, HA_ref) et corr(feature, Abs_ref) pour chaque feature."""
    rows = []
    for feat in feature_cols:
        sub = aligned[[feat, "HA_ref", "Abs_ref"]].dropna()
        if len(sub) < 10:
            continue
        rows.append(
            {
                "feature": feat,
                "corr_HA": corr_safe(sub[feat], sub["HA_ref"]),
                "corr_Abs": corr_safe(sub[feat], sub["Abs_ref"]),
                "n": int(len(sub)),
            }
        )
    return pd.DataFrame(rows)


def mapping_score(corr_df: pd.DataFrame) -> float:
    """Score global d'un mapping (plus grand = meilleur alignement)."""
    if corr_df.empty:
        return float("-inf")
    return float(corr_df["corr_HA"].abs().median() + 0.5 * corr_df["corr_Abs"].abs().median())


def align_by_shift(df_laser: pd.DataFrame, df_btn: pd.DataFrame, shift: int) -> pd.DataFrame:
    """Mapping indexe: btn_idx = scan_id + shift."""
    tmp = df_laser.copy()
    tmp["btn_idx"] = tmp["scan_id"] + shift
    out = tmp.merge(df_btn, on="btn_idx", how="inner")
    return out.sort_values("scan_id").reset_index(drop=True)


def evaluate_shift_candidates(
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    feature_cols: list[str],
    shift_min: int = -40,
    shift_max: int = 40,
) -> tuple[pd.DataFrame, int, pd.DataFrame, pd.DataFrame]:
    """Teste une plage de shifts et retourne le meilleur."""
    rows = []
    best_shift = 0
    best_score = float("-inf")
    best_aligned = pd.DataFrame()
    best_corr = pd.DataFrame()

    # On evalue chaque shift avec les correlations des features.
    for shift in range(shift_min, shift_max + 1):
        aligned = align_by_shift(df_laser, df_btn, shift)
        corr_df = compute_feature_correlations(aligned, feature_cols)
        score = mapping_score(corr_df)
        if corr_df.empty:
            continue
        best_row = corr_df.iloc[corr_df["corr_HA"].abs().idxmax()]
        rows.append(
            {
                "shift": shift,
                "score": score,
                "n_pairs": int(len(aligned)),
                "best_feature_HA": best_row["feature"],
                "best_corr_HA": best_row["corr_HA"],
                "best_corr_Abs": best_row["corr_Abs"],
            }
        )

        if score > best_score:
            best_score = score
            best_shift = shift
            best_aligned = aligned
            best_corr = corr_df

    return pd.DataFrame(rows), best_shift, best_aligned, best_corr


def validate_shift_with_summary(
    df_summary: pd.DataFrame, df_btn: pd.DataFrame, shift_min: int = -20, shift_max: int = 20
) -> tuple[int, float, int]:
    """Valide le shift via la corr(summary_abs, Abs_ref)."""
    best_shift = 0
    best_corr = float("nan")
    best_n = 0
    for shift in range(shift_min, shift_max + 1):
        tmp = df_summary.copy()
        tmp["btn_idx"] = tmp["scan_id"] - shift
        merged = tmp.merge(df_btn[["btn_idx", "Abs_ref"]], on="btn_idx", how="inner")
        corr = corr_safe(merged["summary_abs"], merged["Abs_ref"])
        if np.isnan(corr):
            continue
        if np.isnan(best_corr) or abs(corr) > abs(best_corr):
            best_shift = shift
            best_corr = corr
            best_n = len(merged)
    return best_shift, best_corr, best_n


def align_by_time(
    df_laser: pd.DataFrame, df_btn: pd.DataFrame, df_summary: pd.DataFrame, tol_s: int = 12
) -> pd.DataFrame:
    """Mapping temporel par voisin le plus proche (merge_asof)."""
    scan = df_laser.merge(df_summary[["scan_id", "scan_dt"]], on="scan_id", how="inner")
    scan = scan.sort_values("scan_dt")
    btn = df_btn.sort_values("btn_dt")

    merged = pd.merge_asof(
        scan,
        btn,
        left_on="scan_dt",
        right_on="btn_dt",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=tol_s),
    )
    merged = merged.dropna(subset=["btn_idx"]).copy()
    merged["btn_idx"] = merged["btn_idx"].astype(int)
    merged["time_err_s"] = (merged["scan_dt"] - merged["btn_dt"]).dt.total_seconds().abs()
    merged = merged.sort_values(["btn_idx", "time_err_s"]).drop_duplicates("btn_idx", keep="first")
    return merged.sort_values("scan_id").reset_index(drop=True)


def _zscore(x: np.ndarray) -> np.ndarray:
    """Standardisation (x - moyenne) / ecart-type."""
    mu = float(np.mean(x))
    sd = float(np.std(x))
    if sd < 1e-12:
        return np.zeros_like(x)
    return (x - mu) / sd


def dtw_path(x: np.ndarray, y: np.ndarray, window: int | None = None) -> list[tuple[int, int]]:
    """Calcule le chemin DTW (avec contrainte de fenetre)."""
    n = len(x)
    m = len(y)
    if window is None:
        window = max(n, m)
    window = max(window, abs(n - m))

    D = np.full((n + 1, m + 1), np.inf, dtype=float)
    D[0, 0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - window)
        j_end = min(m, i + window)
        for j in range(j_start, j_end + 1):
            cost = (x[i - 1] - y[j - 1]) ** 2
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])

    path = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        prev = np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]])
        if prev == 0:
            i -= 1
            j -= 1
        elif prev == 1:
            i -= 1
        else:
            j -= 1

    while i > 0:
        i -= 1
        path.append((i, 0))
    while j > 0:
        j -= 1
        path.append((0, j))

    path.reverse()
    return path


def align_by_dtw(
    df_laser: pd.DataFrame, df_btn: pd.DataFrame, feature_col: str = "F_p95", window: int = 35
) -> pd.DataFrame:
    """Mapping alternatif par DTW (diagnostic/fallback)."""
    scan = df_laser.sort_values("scan_id").reset_index(drop=True).copy()
    btn = df_btn.sort_values("btn_idx").reset_index(drop=True).copy()

    x = _zscore(scan[feature_col].to_numpy(dtype=float))
    y = _zscore(btn["HA_ref"].to_numpy(dtype=float))
    path = dtw_path(x, y, window=window)

    pairs = pd.DataFrame(path, columns=["scan_pos", "btn_pos"])
    map_pos = (
        pairs.groupby("scan_pos", as_index=False)["btn_pos"].median().round().astype(int)
    )
    map_pos["btn_pos"] = map_pos["btn_pos"].clip(lower=0, upper=len(btn) - 1)

    scan["scan_pos"] = np.arange(len(scan))
    scan = scan.merge(map_pos, on="scan_pos", how="left")
    scan["btn_idx"] = scan["btn_pos"].fillna(0).astype(int)

    aligned = scan.merge(btn, on="btn_idx", how="inner")
    return aligned.sort_values("scan_id").reset_index(drop=True)


def fit_linear_model(df: pd.DataFrame, x_cols: list[str], y_col: str = "HA_ref") -> tuple[np.ndarray, np.ndarray]:
    """Ajuste une regression lineaire (moindres carres) et retourne (coef, y_pred)."""
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(dtype=float) for c in x_cols])
    y = df[y_col].to_numpy(dtype=float)
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    y_pred = X @ coef
    return coef, y_pred


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Metriques de performance: RMSE, MAE, R2."""
    err = y_true - y_pred
    mse = float(np.mean(err**2))
    rmse = float(np.sqrt(mse))
    mae = float(np.mean(np.abs(err)))
    den = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = float(1 - np.sum(err**2) / den) if den > 0 else float("nan")
    return {"rmse": rmse, "mae": mae, "r2": r2}


def run_calibration(
    aligned: pd.DataFrame, feature_col: str, include_temperature: bool = USE_TEMPERATURE_DEFAULT
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Lance la calibration avec split chronologique:
    - train = 70% debut de serie
    - test  = 30% fin de serie

    Le mode par defaut est SANS temperature (HA ~ feature).
    """
    data = aligned.sort_values("scan_id")[[feature_col, "T", "HA_ref", "scan_id"]].dropna().reset_index(drop=True)
    n = len(data)
    cut = int(0.7 * n)
    train = data.iloc[:cut].copy()
    test = data.iloc[cut:].copy()

    models: list[tuple[str, list[str]]] = [("HA ~ feature", [feature_col])]
    if include_temperature:
        models.append(("HA ~ feature + T", [feature_col, "T"]))

    metrics_rows = []
    pred_test_selected = pd.DataFrame()
    selected_model_name = "HA ~ feature + T" if include_temperature else "HA ~ feature"

    # On evalue modele(s) avec coefficients appris uniquement sur train pour test_30.
    for model_name, cols in models:
        coef_all, pred_all = fit_linear_model(data, cols, y_col="HA_ref")
        coef_train, pred_train = fit_linear_model(train, cols, y_col="HA_ref")

        X_test = np.column_stack([np.ones(len(test))] + [test[c].to_numpy(dtype=float) for c in cols])
        pred_test = X_test @ coef_train

        m_all = metrics(data["HA_ref"].to_numpy(dtype=float), pred_all)
        m_train = metrics(train["HA_ref"].to_numpy(dtype=float), pred_train)
        m_test = metrics(test["HA_ref"].to_numpy(dtype=float), pred_test)

        metrics_rows.append(
            {
                "model": model_name,
                "split": "all",
                "n": len(data),
                **m_all,
                "coef_intercept": float(coef_all[0]),
                "coef_feature": float(coef_all[1]) if len(coef_all) > 1 else np.nan,
                "coef_T": float(coef_all[2]) if len(coef_all) > 2 else np.nan,
                "feature_col": feature_col,
            }
        )
        metrics_rows.append(
            {
                "model": model_name,
                "split": "train_70",
                "n": len(train),
                **m_train,
                "coef_intercept": float(coef_train[0]),
                "coef_feature": float(coef_train[1]) if len(coef_train) > 1 else np.nan,
                "coef_T": float(coef_train[2]) if len(coef_train) > 2 else np.nan,
                "feature_col": feature_col,
            }
        )
        metrics_rows.append(
            {
                "model": model_name,
                "split": "test_30",
                "n": len(test),
                **m_test,
                "coef_intercept": float(coef_train[0]),
                "coef_feature": float(coef_train[1]) if len(coef_train) > 1 else np.nan,
                "coef_T": float(coef_train[2]) if len(coef_train) > 2 else np.nan,
                "feature_col": feature_col,
            }
        )

        if model_name == selected_model_name:
            pred_test_selected = pd.DataFrame(
                {
                    "scan_id": test["scan_id"].to_numpy(dtype=int),
                    "HA_ref": test["HA_ref"].to_numpy(dtype=float),
                    "HA_pred": pred_test.astype(float),
                    "residual": (test["HA_ref"].to_numpy(dtype=float) - pred_test).astype(float),
                    "model": model_name,
                }
            )

    return pd.DataFrame(metrics_rows), pred_test_selected, selected_model_name


def make_plots(
    shift_scores: pd.DataFrame,
    aligned: pd.DataFrame,
    feature_col: str,
    calib_pred: pd.DataFrame,
    best_shift: int,
    calibration_model_name: str,
) -> None:
    """Genere les figures de controle du matching et de la calibration."""
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Shift score curve
    plt.figure(figsize=(10, 4))
    plt.plot(shift_scores["shift"], shift_scores["score"], marker="o", ms=3)
    plt.axvline(best_shift, color="tab:red", linestyle="--", label=f"best shift={best_shift}")
    plt.xlabel("Index shift (btn_idx = scan_id + shift)")
    plt.ylabel("Matching score")
    plt.title("Shift search for scan-button matching")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "matching_shift_score.png", dpi=200)
    plt.close()

    # Z-scored aligned timeline
    a = aligned.sort_values("scan_id")
    x = a["scan_id"].to_numpy(dtype=int)
    y1 = _zscore(a[feature_col].to_numpy(dtype=float))
    y2 = _zscore(a["HA_ref"].to_numpy(dtype=float))
    plt.figure(figsize=(11, 4))
    plt.plot(x, y1, label=f"{feature_col} (z-score)")
    plt.plot(x, y2, label="HA_ref (z-score)", alpha=0.8)
    plt.xlabel("scan_id")
    plt.ylabel("z-score")
    plt.title("Aligned series check (laser feature vs HA_ref)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "aligned_feature_vs_HA_timeseries.png", dpi=200)
    plt.close()

    # Feature scatter with line
    x_feat = a[feature_col].to_numpy(dtype=float)
    y_ha = a["HA_ref"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x_feat, y_ha, deg=1)
    xx = np.linspace(np.min(x_feat), np.max(x_feat), 200)
    yy = slope * xx + intercept
    plt.figure(figsize=(6, 5))
    plt.scatter(x_feat, y_ha, s=14, alpha=0.65)
    plt.plot(xx, yy, color="tab:red", linewidth=2)
    plt.xlabel(feature_col)
    plt.ylabel("HA_ref (g/m3)")
    plt.title("Best feature vs HA_ref")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "best_feature_vs_HA_scatter.png", dpi=200)
    plt.close()

    # Prediction vs truth on holdout
    p = calib_pred.sort_values("scan_id")
    plt.figure(figsize=(11, 4))
    plt.plot(p["scan_id"], p["HA_ref"], label="HA_ref", linewidth=2)
    plt.plot(p["scan_id"], p["HA_pred"], label="HA_pred", linewidth=2)
    plt.xlabel("scan_id")
    plt.ylabel("HA (g/m3)")
    plt.title(f"Calibration holdout (30%) - model: {calibration_model_name}")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "calibration_holdout_timeseries.png", dpi=200)
    plt.close()

    # Residuals
    plt.figure(figsize=(6, 5))
    plt.scatter(p["HA_pred"], p["residual"], s=14, alpha=0.65)
    plt.axhline(0.0, color="k", linewidth=1)
    plt.xlabel("HA_pred (g/m3)")
    plt.ylabel("Residual (HA_ref - HA_pred)")
    plt.title(f"Residuals on holdout ({calibration_model_name})")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "calibration_holdout_residuals.png", dpi=200)
    plt.close()


def parse_args() -> argparse.Namespace:
    """Arguments CLI simples pour activer/desactiver l'usage de T."""
    parser = argparse.ArgumentParser(
        description="Calibration laser->HA avec matching robuste scan/bouton."
    )
    parser.add_argument(
        "--with-temperature",
        action="store_true",
        help="Ajoute T dans la calibration (HA ~ feature + T). Par defaut: desactive.",
    )
    return parser.parse_args()


def main(include_temperature: bool = USE_TEMPERATURE_DEFAULT) -> None:
    OUT_REP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    df_laser = build_laser_features()
    df_btn = read_button_log_xlsx(XLSX_PATH, header_row=9)
    df_summary = read_summary(SUMMARY_PATH)

    feature_cols = [c for c in df_laser.columns if c != "scan_id"]

    # 1) Shift search on index mapping.
    shift_scores, best_shift, aligned_shift, corr_shift = evaluate_shift_candidates(
        df_laser, df_btn, feature_cols, shift_min=-40, shift_max=40
    )

    # 2) Time mapping (if timestamps available) for validation.
    aligned_time = align_by_time(df_laser, df_btn, df_summary, tol_s=12)
    corr_time = compute_feature_correlations(aligned_time, feature_cols)
    score_time = mapping_score(corr_time)

    # 3) DTW mapping as fallback/diagnostic.
    aligned_dtw = align_by_dtw(df_laser, df_btn, feature_col="F_p95", window=35)
    corr_dtw = compute_feature_correlations(aligned_dtw, feature_cols)
    score_dtw = mapping_score(corr_dtw)

    # Summary-based shift validation between summary_abs and Abs_ref.
    summary_shift, summary_corr, summary_n = validate_shift_with_summary(
        df_summary, df_btn, shift_min=-20, shift_max=20
    )

    # Pick final mapping:
    # - if summary confirms a near-perfect shift, use it (most interpretable),
    # - otherwise use the highest score among index/time/dtw.
    if abs(summary_corr) >= 0.98:
        final_shift = -summary_shift
        aligned_final = align_by_shift(df_laser, df_btn, final_shift)
        corr_final = compute_feature_correlations(aligned_final, feature_cols)
        final_method = f"index_shift_from_summary({final_shift})"
    else:
        candidates = [
            ("index_shift", mapping_score(corr_shift), aligned_shift, corr_shift),
            ("time_nearest", score_time, aligned_time, corr_time),
            ("dtw", score_dtw, aligned_dtw, corr_dtw),
        ]
        final_method, _, aligned_final, corr_final = max(candidates, key=lambda x: x[1])
        final_shift = best_shift

    best_feature_row = corr_final.iloc[corr_final["corr_HA"].abs().idxmax()]
    best_feature = str(best_feature_row["feature"])

    calib_metrics, calib_pred, selected_model_name = run_calibration(
        aligned_final,
        feature_col=best_feature,
        include_temperature=include_temperature,
    )
    make_plots(
        shift_scores,
        aligned_final,
        best_feature,
        calib_pred,
        best_shift=final_shift,
        calibration_model_name=selected_model_name,
    )

    # Save tables.
    df_laser.to_csv(OUT_REP_DIR / "laser_features_all_scans.csv", index=False)
    shift_scores.to_csv(OUT_REP_DIR / "matching_shift_scores.csv", index=False)
    corr_final.sort_values("corr_HA", key=lambda s: s.abs(), ascending=False).to_csv(
        OUT_REP_DIR / "matching_feature_correlations.csv", index=False
    )
    aligned_final.to_csv(OUT_REP_DIR / "aligned_laser_button.csv", index=False)
    calib_metrics.to_csv(OUT_REP_DIR / "calibration_metrics.csv", index=False)
    calib_pred.to_csv(OUT_REP_DIR / "calibration_holdout_predictions.csv", index=False)

    # Save compact run summary for quick notebook import.
    run_summary = pd.DataFrame(
        [
            {
                "n_scans": len(df_laser),
                "n_button_rows": len(df_btn),
                "n_summary_rows": len(df_summary),
                "best_shift_index_score": best_shift,
                "summary_validated_shift": summary_shift,
                "summary_corr_absorbance": summary_corr,
                "summary_pairs": summary_n,
                "final_method": final_method,
                "final_shift_used": final_shift,
                "final_pairs": len(aligned_final),
                "best_feature": best_feature,
                "best_corr_HA": float(best_feature_row["corr_HA"]),
                "best_corr_Abs": float(best_feature_row["corr_Abs"]),
                "calibration_model": selected_model_name,
                "use_temperature": bool(include_temperature),
            }
        ]
    )
    run_summary.to_csv(OUT_REP_DIR / "laser_matching_run_summary.csv", index=False)

    # Console summary.
    print("OK")
    print(f"- Laser scans: {len(df_laser)}")
    print(f"- Button rows: {len(df_btn)}")
    print(f"- Summary rows: {len(df_summary)}")
    print(f"- Best shift by index score: {best_shift}")
    print(
        f"- Summary Abs_ref validation: shift={summary_shift}, corr={summary_corr:.4f}, n={summary_n}"
    )
    print(f"- Final matching method: {final_method}")
    print(f"- Final pairs: {len(aligned_final)}")
    print(f"- Best feature for HA: {best_feature} (corr={float(best_feature_row['corr_HA']):.4f})")
    print(f"- Calibration model: {selected_model_name}")
    print("- Saved reports:")
    print(f"  {OUT_REP_DIR / 'laser_matching_run_summary.csv'}")
    print(f"  {OUT_REP_DIR / 'matching_feature_correlations.csv'}")
    print(f"  {OUT_REP_DIR / 'calibration_metrics.csv'}")
    print("- Saved figures:")
    print(f"  {OUT_FIG_DIR / 'matching_shift_score.png'}")
    print(f"  {OUT_FIG_DIR / 'aligned_feature_vs_HA_timeseries.png'}")
    print(f"  {OUT_FIG_DIR / 'best_feature_vs_HA_scatter.png'}")
    print(f"  {OUT_FIG_DIR / 'calibration_holdout_timeseries.png'}")


if __name__ == "__main__":
    args = parse_args()
    main(include_temperature=bool(args.with_temperature))
