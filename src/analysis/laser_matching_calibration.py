from __future__ import annotations

"""
Pipeline complet "laser -> HA" pour le projet PI etancheite.

Ce script:
1) lit les scans laser (.txt), construit I0(t), puis A(t),
2) extrait des features robustes sur A(t),
3) lit le log bouton (.xlsx XML ou .xls BIFF ancien),
4) aligne scans et log bouton:
   - ancien jeu: validation summary + shift d'index
   - jeu actuel: recherche d'offset temporel + agregat laser par mesure bouton
5) choisit la feature la plus correlee a HA_ref,
6) calibre (fit) HA_ref ~ feature (sans temperature par defaut),
7) evalue la calibration avec:
   - un split chronologique 70/30
   - un split blocked_balanced plus adapte a un protocole "monotone sec -> humide" comme ce qu'à fait Yann
8) exporte CSV + figures de controle.

Usage standard (jeu de calibration actuel):
    python src/analysis/laser_matching_calibration.py

Option temperature (si besoin plus tard):
    python src/analysis/laser_matching_calibration.py --with-temperature

Exemple pour rerun explicitement l'ancien jeu du prof:
    python src/analysis/laser_matching_calibration.py \
      --data-dir data/raw/Mesures27062024 \
      --button-path data/raw/Mesures27062024/HYGROBOUTON_LOCLE_DAS.xlsx \
      --summary-path data/raw/Mesures27062024/Calibration27062024_summary.txt \
      --signal-pattern "Mesures27062024_*.txt"
"""

import argparse
import os
import re
import struct
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
import pandas as pd

# Use inline rendering in notebooks, and Agg only for headless/script contexts.
try:
    from IPython import get_ipython
except Exception:
    get_ipython = None

ip = get_ipython() if get_ipython else None
if ip is not None:
    matplotlib.use("module://matplotlib_inline.backend_inline", force=True)
else:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_DATA_DIR = Path("data/raw/calibration")
DEFAULT_BUTTON_PATH = DEFAULT_DATA_DIR / "button-test-1.xls"
DEFAULT_SUMMARY_PATH = None
DEFAULT_SIGNAL_PATTERN = "*_calibration_*.txt"

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


def parse_scan_datetime(path: Path) -> pd.Timestamp | pd.NaT:
    """Extrait un timestamp depuis le nom du scan si le prefixe est au format YYYYMMDD_HHMMSS."""
    m = re.match(r"^(\d{8}_\d{6})_", path.stem)
    if not m:
        return pd.NaT
    try:
        return pd.to_datetime(m.group(1), format="%Y%m%d_%H%M%S")
    except Exception:
        return pd.NaT


def parse_trailing_int(stem: str) -> int | None:
    """Extrait le dernier entier d'un stem si present."""
    m = re.search(r"(\d+)$", stem)
    return int(m.group(1)) if m else None


def signal_sort_key(path: Path) -> tuple:
    """Tri robuste des fichiers de scan: timestamp si present, sinon entier final, sinon nom."""
    scan_dt = parse_scan_datetime(path)
    tail_num = parse_trailing_int(path.stem)
    if pd.notna(scan_dt):
        return (0, scan_dt.to_pydatetime(), tail_num if tail_num is not None else -1, path.name)
    if tail_num is not None:
        return (1, tail_num, path.name)
    return (2, path.name)


def moving_average_reflect(x: np.ndarray, window: int) -> np.ndarray:
    """Moyenne mobile avec padding miroir pour limiter les effets de bord."""
    if window % 2 == 0:
        raise ValueError("window must be odd")
    pad = window // 2
    x_pad = np.pad(x, pad_width=pad, mode="reflect")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(x_pad, kernel, mode="valid")


def detect_main_support(
    I: np.ndarray, peak_index: int | None = None, smooth_window: int = 101
) -> tuple[int, int]:
    """
    Detecte la zone utile du triangle via les minima lateraux autour du pic principal.

    Les petits bouts parasites avant le minimum gauche et apres le minimum droit
    sont exclus ensuite du calcul d'absorbance.
    """
    if I.size < 3:
        return 0, max(0, I.size - 1)

    win = min(smooth_window, I.size if I.size % 2 == 1 else I.size - 1)
    if win < 3:
        win = 3 if I.size >= 3 else I.size
    if win % 2 == 0:
        win -= 1

    I_s = moving_average_reflect(I, win) if win >= 3 else I
    p = int(np.argmax(I_s if peak_index is None else I))
    if peak_index is not None:
        p = int(np.clip(peak_index, 1, I.size - 2))

    left_min = int(np.argmin(I_s[: p + 1]))
    right_min = int(p + np.argmin(I_s[p:]))
    left_min = max(0, min(left_min, p - 1))
    right_min = min(I.size - 1, max(right_min, p + 1))
    return left_min, right_min


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
    left_bound, right_bound = detect_main_support(I, peak_index=p, smooth_window=101)

    I_s = moving_average_reflect(I, smooth_window)
    D = I_s - I
    thr = np.quantile(D, 1 - k)
    good = D < thr

    left = (t >= left_bound) & (t <= p) & good
    right = (t >= p) & (t <= right_bound) & good
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
    # Hors de la zone utile, on annule l'absorbance plus tard en posant I0 = I.
    I0[:left_bound] = I[:left_bound]
    I0[right_bound + 1 :] = I[right_bound + 1 :]
    I0[left_bound:p_join] = I0_left[left_bound:p_join]
    I0[p_join : right_bound + 1] = I0_right[p_join : right_bound + 1]
    I0 = np.maximum(I0, I)
    return I0


def compute_A_full(
    I: np.ndarray,
    I0: np.ndarray,
    support_margin: int | None = None,
) -> np.ndarray:
    """
    Calcule l'absorbance point a point: A = -ln(I/I0).

    Le signal brut et sa baseline peuvent etre centres autour de zero par
    l'electronique. On applique donc un offset positif commun avant le log,
    sinon les passages par zero creent des pics artificiels.
    """
    eps = 1e-9
    offset = max(0.0, -min(float(np.min(I)), float(np.min(I0))) + 1e-6)
    I_pos = I + offset
    I0_pos = I0 + offset
    A = -np.log(np.clip(I_pos, eps, None) / np.clip(I0_pos, eps, None))

    left_bound, right_bound = detect_main_support(I)
    span = max(1, right_bound - left_bound)
    if support_margin is None:
        support_margin = max(25, int(round(0.01 * span)))

    left_use = min(right_bound, left_bound + support_margin)
    right_use = max(left_use, right_bound - support_margin)
    A[:left_use] = 0.0
    A[right_use + 1 :] = 0.0
    return A


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


def build_laser_features(data_dir: Path, signal_pattern: str) -> pd.DataFrame:
    """Construit le tableau de features pour tous les scans disponibles."""
    paths = sorted(data_dir.glob(signal_pattern), key=signal_sort_key)
    if not paths:
        raise FileNotFoundError(
            f"No signal found under {data_dir} with {signal_pattern}"
        )

    rows = []
    # Pipeline scan par scan: lecture -> baseline -> absorbance -> features.
    for scan_id, p in enumerate(paths):
        I = read_signal(p)
        I0 = compute_I0(I, smooth_window=41, k=0.20)
        A_full = compute_A_full(I, I0)

        feat = extract_features(A_full, edge=20)
        rows.append(
            {
                "scan_id": scan_id,
                "scan_name": p.name,
                "scan_stem": p.stem,
                "scan_dt": parse_scan_datetime(p),
                "scan_local_idx": parse_trailing_int(p.stem),
                **feat,
            }
        )

    return pd.DataFrame(rows).sort_values("scan_id").reset_index(drop=True)


def _excel_col_to_idx(col: str) -> int:
    """Convertit une colonne Excel (A, B, AA...) en index 0-based."""
    v = 0
    for ch in col:
        v = v * 26 + (ord(ch) - ord("A") + 1)
    return v - 1


def _normalize_label(label: str) -> str:
    """Normalise un nom de colonne pour des recherches robustes."""
    txt = unicodedata.normalize("NFKD", str(label))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.lower().strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    """Retourne la colonne qui matche l'un des alias normalises."""
    alias_set = {_normalize_label(a) for a in aliases}
    for col in columns:
        if _normalize_label(col) in alias_set:
            return col
    return None


def compute_absolute_humidity_gm3(
    temperature_c: pd.Series | np.ndarray,
    rh_pct: pd.Series | np.ndarray,
) -> np.ndarray:
    """Calcule HA en g/m3 a partir de T (C) et RH (%)."""
    t = np.asarray(temperature_c, dtype=float)
    rh = np.asarray(rh_pct, dtype=float)
    sat_vapor_hpa = 6.112 * np.exp((17.67 * t) / (t + 243.5))
    vapor_hpa = (rh / 100.0) * sat_vapor_hpa
    return 216.7 * vapor_hpa / (t + 273.15)


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
                custom_numfmt[numfmt_id] = (
                    numfmt.attrib.get("formatCode") or ""
                ).lower()

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
                                value = pd.Timestamp("1899-12-30") + pd.to_timedelta(
                                    serial, unit="D"
                                )
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


def _parse_xls_biff_sheet_1(path: Path) -> pd.DataFrame:
    """
    Parse un ancien .xls au format BIFF direct (sans xlrd).

    Le fichier bouton recu sur le nouveau banc est dans ce format.
    Les cellules utiles sont portees par les records:
    - 0x0004: LABEL (chaine)
    - 0x0003: NUMBER (float64)
    - 0x0002: INTEGER (uint16)
    """
    rows: dict[int, dict[int, object]] = {}
    data = path.read_bytes()
    pos = 0
    while pos + 4 <= len(data):
        rid, ln = struct.unpack_from("<HH", data, pos)
        body = data[pos + 4 : pos + 4 + ln]
        pos += 4 + ln
        if len(body) < 7:
            continue
        if rid == 0x0004:
            row_idx, col_idx = struct.unpack_from("<HH", body, 0)
            n = body[7]
            value = body[8 : 8 + n].decode("latin1", errors="ignore")
        elif rid == 0x0003:
            row_idx, col_idx = struct.unpack_from("<HH", body, 0)
            value = struct.unpack_from("<d", body, 7)[0]
        elif rid == 0x0002:
            row_idx, col_idx = struct.unpack_from("<HH", body, 0)
            value = struct.unpack_from("<H", body, 7)[0]
        else:
            continue
        rows.setdefault(row_idx, {})[col_idx] = value

    if not rows:
        raise ValueError(f"No BIFF cell parsed from {path}")

    max_row = max(rows)
    max_col = max(max(row.keys()) for row in rows.values())
    arr = []
    for row_idx in range(max_row + 1):
        rec = {"_row": row_idx + 1}
        for col_idx in range(max_col + 1):
            rec[col_idx] = rows.get(row_idx, {}).get(col_idx, np.nan)
        arr.append(rec)
    return pd.DataFrame(arr)


def _normalize_button_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise un tableau bouton heterogene vers btn_dt/T/HA_ref/Abs_ref/btn_idx."""
    cols = list(df.columns)
    date_name = _find_column(cols, ["Date"])
    time_name = _find_column(cols, ["Heure", "Time"])
    temp_name = _find_column(cols, ["Température", "Temperature", "Temp"])
    rh_name = _find_column(cols, ["Humidité", "Humidite", "RH", "HR"])
    ha_name = _find_column(cols, ["Ha (g/m3)", "HA", "Ha g/m3"])
    abs_name = _find_column(cols, ["Absorbance"])
    dew_name = _find_column(cols, ["Point de Rosée", "Point de Rosee", "Dew point"])

    required = {"Date": date_name, "Heure": time_name, "Température": temp_name}
    missing = [label for label, found in required.items() if found is None]
    if missing:
        raise ValueError(f"Missing columns in button log: {missing}")
    if ha_name is None and rh_name is None:
        raise ValueError(
            "Button log must contain either absolute humidity or relative humidity."
        )

    date_col = df[date_name]
    time_col = df[time_name]
    temp_col = pd.to_numeric(df[temp_name], errors="coerce")

    if pd.api.types.is_datetime64_any_dtype(date_col):
        date_str = pd.to_datetime(date_col, errors="coerce").dt.strftime("%d/%m/%Y")
    else:
        date_str = date_col.astype(str).str.strip()

    if pd.api.types.is_datetime64_any_dtype(time_col):
        time_str = pd.to_datetime(time_col, errors="coerce").dt.strftime("%H:%M:%S")
    else:
        time_str = time_col.astype(str).str.strip()
        has_date = time_str.str.contains(" ", na=False)
        if has_date.any():
            time_str.loc[has_date] = pd.to_datetime(
                time_str.loc[has_date], errors="coerce"
            ).dt.strftime("%H:%M:%S")

    dt = pd.to_datetime(date_str + " " + time_str, dayfirst=True, errors="coerce")
    rh_col = pd.to_numeric(df[rh_name], errors="coerce") if rh_name is not None else np.nan
    if ha_name is not None:
        ha_col = pd.to_numeric(df[ha_name], errors="coerce")
    else:
        ha_col = pd.Series(
            compute_absolute_humidity_gm3(temp_col, rh_col),
            index=df.index,
            dtype=float,
        )
    abs_col = pd.to_numeric(df[abs_name], errors="coerce") if abs_name is not None else np.nan
    dew_col = pd.to_numeric(df[dew_name], errors="coerce") if dew_name is not None else np.nan

    out = pd.DataFrame(
        {
            "btn_dt": dt,
            "T": temp_col,
            "RH_ref": rh_col,
            "dew_ref": dew_col,
            "HA_ref": ha_col,
            "Abs_ref": abs_col,
        }
    )
    out = out.dropna(subset=["btn_dt", "T", "HA_ref"]).reset_index(drop=True)
    out["btn_idx"] = np.arange(len(out))
    return out


def _extract_table_from_header_row(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Extrait un tableau de donnees a partir d'une ligne d'en-tete."""
    header = raw.loc[raw["_row"] == header_row]
    if header.empty:
        raise ValueError(f"Header row {header_row} not found in button log")
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

    return raw.loc[raw["_row"] > header_row].rename(columns=rename_map).copy()


def read_button_log(path: Path, header_row_xlsx: int = 9, header_row_xls: int = 4) -> pd.DataFrame:
    """
    Lit le log bouton quel que soit le format:
    - .xlsx XML (ancien jeu)
    - .xls BIFF direct (nouveau jeu)
    """
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        raw = _parse_xlsx_sheet_1(path)
        df = _extract_table_from_header_row(raw, header_row=header_row_xlsx)
        return _normalize_button_table(df)
    if suffix == ".xls":
        raw = _parse_xls_biff_sheet_1(path)
        df = _extract_table_from_header_row(raw, header_row=header_row_xls)
        return _normalize_button_table(df)
    raise ValueError(f"Unsupported button log format: {path}")


def read_summary(path: Path | None) -> pd.DataFrame:
    """Lit Calibration27062024_summary.txt (timestamp + absorbance summary)."""
    if path is None:
        return pd.DataFrame(columns=["scan_dt", "summary_abs", "scan_id"])
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
        sub_ha = aligned[[feat, "HA_ref"]].dropna()
        sub_abs = (
            aligned[[feat, "Abs_ref"]].dropna()
            if "Abs_ref" in aligned.columns
            else pd.DataFrame()
        )
        corr_ha = (
            corr_safe(sub_ha[feat], sub_ha["HA_ref"]) if len(sub_ha) >= 10 else float("nan")
        )
        corr_abs = (
            corr_safe(sub_abs[feat], sub_abs["Abs_ref"]) if len(sub_abs) >= 10 else float("nan")
        )
        if np.isnan(corr_ha) and np.isnan(corr_abs):
            continue
        rows.append(
            {
                "feature": feat,
                "corr_HA": corr_ha,
                "corr_Abs": corr_abs,
                "n_HA": int(len(sub_ha)),
                "n_Abs": int(len(sub_abs)),
                "n": int(max(len(sub_ha), len(sub_abs))),
            }
        )
    return pd.DataFrame(rows)


def mapping_score(corr_df: pd.DataFrame) -> float:
    """Score global d'un mapping (plus grand = meilleur alignement)."""
    if corr_df.empty:
        return float("-inf")
    corr_ha = corr_df["corr_HA"].abs().dropna()
    corr_abs = corr_df["corr_Abs"].abs().dropna()
    score = 0.0
    has_any = False
    if not corr_ha.empty:
        score += float(corr_ha.median())
        has_any = True
    if not corr_abs.empty:
        score += 0.5 * float(corr_abs.median())
        has_any = True
    return score if has_any else float("-inf")


def align_by_shift(
    df_laser: pd.DataFrame, df_btn: pd.DataFrame, shift: int
) -> pd.DataFrame:
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
    df_summary: pd.DataFrame,
    df_btn: pd.DataFrame,
    shift_min: int = -20,
    shift_max: int = 20,
) -> tuple[int, float, int]:
    """Valide le shift via la corr(summary_abs, Abs_ref)."""
    if df_summary.empty or "Abs_ref" not in df_btn.columns or df_btn["Abs_ref"].dropna().empty:
        return 0, float("nan"), 0
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
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    scan_dt_col: str = "scan_dt",
    tol_s: int = 12,
) -> pd.DataFrame:
    """Mapping temporel par voisin le plus proche (merge_asof)."""
    scan = df_laser.dropna(subset=[scan_dt_col]).sort_values(scan_dt_col).copy()
    btn = df_btn.sort_values("btn_dt")

    merged = pd.merge_asof(
        scan,
        btn,
        left_on=scan_dt_col,
        right_on="btn_dt",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=tol_s),
    )
    merged = merged.dropna(subset=["btn_idx"]).copy()
    merged["btn_idx"] = merged["btn_idx"].astype(int)
    merged["time_err_s"] = (
        (merged[scan_dt_col] - merged["btn_dt"]).dt.total_seconds().abs()
    )
    merged = merged.sort_values(["btn_idx", "time_err_s"]).drop_duplicates(
        "btn_idx", keep="first"
    )
    return merged.sort_values("scan_id").reset_index(drop=True)


def align_by_time_offset(
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    offset_s: int,
    tol_s: float = 1.25,
) -> pd.DataFrame:
    """Applique un offset aux timestamps scan puis aligne sur btn_dt."""
    if "scan_dt" not in df_laser.columns or df_laser["scan_dt"].dropna().empty:
        raise ValueError("scan_dt is required for time-offset alignment.")
    scan = df_laser.copy()
    scan["scan_dt_aligned"] = scan["scan_dt"] - pd.to_timedelta(offset_s, unit="s")
    return align_by_time(scan, df_btn, scan_dt_col="scan_dt_aligned", tol_s=tol_s)


def estimate_button_period_seconds(df_btn: pd.DataFrame) -> float:
    """Estime la periode temporelle typique du bouton a partir des timestamps."""
    d = (
        df_btn["btn_dt"]
        .sort_values()
        .diff()
        .dt.total_seconds()
        .dropna()
    )
    d = d[d > 0]
    if d.empty:
        return 1.0
    return float(d.median())


def align_by_time_offset_aggregate(
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    feature_cols: list[str],
    offset_s: int,
    half_window_s: float | None = None,
) -> pd.DataFrame:
    """
    Aligne par temps puis agrege plusieurs scans laser sur une meme mesure bouton.

    Chaque scan est rattache a la mesure bouton temporellement la plus proche
    (dans une tolerance fixee), puis les features laser sont moyennees par btn_idx.
    """
    if "scan_dt" not in df_laser.columns or df_laser["scan_dt"].dropna().empty:
        raise ValueError("scan_dt is required for time-offset aggregation.")

    scan = df_laser.dropna(subset=["scan_dt"]).copy()
    scan["scan_dt_aligned"] = scan["scan_dt"] - pd.to_timedelta(offset_s, unit="s")
    scan = scan.sort_values("scan_dt_aligned")

    btn = df_btn.sort_values("btn_dt").copy()
    if half_window_s is None:
        half_window_s = max(0.5, estimate_button_period_seconds(btn) / 2.0)

    merged = pd.merge_asof(
        scan,
        btn[["btn_idx", "btn_dt"]],
        left_on="scan_dt_aligned",
        right_on="btn_dt",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=half_window_s),
    )
    merged = merged.dropna(subset=["btn_idx"]).copy()
    if merged.empty:
        return pd.DataFrame()

    merged["btn_idx"] = merged["btn_idx"].astype(int)
    merged["time_err_s"] = (
        (merged["scan_dt_aligned"] - merged["btn_dt"]).dt.total_seconds().abs()
    )

    agg_map: dict[str, str] = {feat: "mean" for feat in feature_cols}
    agg_map.update(
        {
            "scan_id": "min",
            "scan_dt_aligned": "min",
            "time_err_s": "mean",
        }
    )
    if "scan_dt" in merged.columns:
        agg_map["scan_dt"] = "min"

    grouped = merged.groupby("btn_idx", as_index=False).agg(agg_map)
    grouped["laser_scans_per_btn"] = (
        merged.groupby("btn_idx").size().reindex(grouped["btn_idx"]).to_numpy(dtype=int)
    )

    out = grouped.merge(df_btn, on="btn_idx", how="inner", suffixes=("", "_btn"))
    return out.sort_values("btn_idx").reset_index(drop=True)


def estimate_offset_search_window(
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    pad_s: int = 240,
) -> tuple[int, int]:
    """Construit une fenetre de recherche plausible pour l'offset temporel."""
    scan_dt = df_laser["scan_dt"].dropna().sort_values()
    btn_dt = df_btn["btn_dt"].dropna().sort_values()
    if scan_dt.empty or btn_dt.empty:
        raise ValueError("Timestamps required to estimate offset window.")
    start_delta = int((scan_dt.iloc[0] - btn_dt.iloc[0]).total_seconds())
    end_delta = int((scan_dt.iloc[-1] - btn_dt.iloc[-1]).total_seconds())
    center = int(round((start_delta + end_delta) / 2.0))
    half_span = int(abs(start_delta - end_delta) / 2) + pad_s
    return center - half_span, center + half_span


def evaluate_time_offset_candidates(
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    feature_cols: list[str],
    offset_min_s: int,
    offset_max_s: int,
    tol_s: float | None = None,
    half_window_s: float | None = None,
) -> tuple[pd.DataFrame, int, pd.DataFrame, pd.DataFrame]:
    """Teste une plage d'offsets temporels et retourne le meilleur, apres agregation par ligne bouton."""
    if half_window_s is None and tol_s is not None:
        half_window_s = tol_s
    rows = []
    best_offset = 0
    best_score = float("-inf")
    best_aligned = pd.DataFrame()
    best_corr = pd.DataFrame()

    for offset_s in range(offset_min_s, offset_max_s + 1):
        aligned = align_by_time_offset_aggregate(
            df_laser,
            df_btn,
            feature_cols=feature_cols,
            offset_s=offset_s,
            half_window_s=half_window_s,
        )
        corr_df = compute_feature_correlations(aligned, feature_cols)
        score = mapping_score(corr_df)
        if corr_df.empty:
            continue
        best_row = corr_df.iloc[corr_df["corr_HA"].abs().fillna(-np.inf).idxmax()]
        rows.append(
            {
                "offset_s": offset_s,
                "score": score,
                "n_pairs": int(len(aligned)),
                "best_feature_HA": best_row["feature"],
                "best_corr_HA": best_row["corr_HA"],
                "best_corr_Abs": best_row["corr_Abs"],
            }
        )
        if score > best_score:
            best_score = score
            best_offset = offset_s
            best_aligned = aligned
            best_corr = corr_df

    return pd.DataFrame(rows), best_offset, best_aligned, best_corr


def _zscore(x: np.ndarray) -> np.ndarray:
    """Standardisation (x - moyenne) / ecart-type."""
    mu = float(np.mean(x))
    sd = float(np.std(x))
    if sd < 1e-12:
        return np.zeros_like(x)
    return (x - mu) / sd


def dtw_path(
    x: np.ndarray, y: np.ndarray, window: int | None = None
) -> list[tuple[int, int]]:
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
    df_laser: pd.DataFrame,
    df_btn: pd.DataFrame,
    feature_col: str = "F_p95",
    window: int = 35,
) -> pd.DataFrame:
    """Mapping alternatif par DTW (diagnostic/fallback)."""
    scan = df_laser.sort_values("scan_id").reset_index(drop=True).copy()
    btn = df_btn.sort_values("btn_idx").reset_index(drop=True).copy()

    x = _zscore(scan[feature_col].to_numpy(dtype=float))
    y = _zscore(btn["HA_ref"].to_numpy(dtype=float))
    path = dtw_path(x, y, window=window)

    pairs = pd.DataFrame(path, columns=["scan_pos", "btn_pos"])
    map_pos = (
        pairs.groupby("scan_pos", as_index=False)["btn_pos"]
        .median()
        .round()
        .astype(int)
    )
    map_pos["btn_pos"] = map_pos["btn_pos"].clip(lower=0, upper=len(btn) - 1)

    scan["scan_pos"] = np.arange(len(scan))
    scan = scan.merge(map_pos, on="scan_pos", how="left")
    scan["btn_idx"] = scan["btn_pos"].fillna(0).astype(int)

    aligned = scan.merge(btn, on="btn_idx", how="inner")
    return aligned.sort_values("scan_id").reset_index(drop=True)


def fit_linear_model(
    df: pd.DataFrame, x_cols: list[str], y_col: str = "HA_ref"
) -> tuple[np.ndarray, np.ndarray]:
    """Ajuste une regression lineaire (moindres carres) et retourne (coef, y_pred)."""
    X = np.column_stack(
        [np.ones(len(df))] + [df[c].to_numpy(dtype=float) for c in x_cols]
    )
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


def make_blocked_balanced_split(
    data: pd.DataFrame,
    y_col: str = "HA_ref",
    test_frac: float = 0.30,
    block_size: int | None = None,
    n_bins: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """
    Split d'evaluation adapte aux series monotones:
    - blocs temporels contigus pour limiter la fuite d'information,
    - repartition des blocs sur plusieurs niveaux d'humidite afin que
      train et test couvrent chacun le bas / milieu / haut de la gamme.
    """
    n = len(data)
    if n < 12:
        cut = max(1, int(round((1 - test_frac) * n)))
        train = data.iloc[:cut].copy()
        test = data.iloc[cut:].copy()
        return train, test, {
            "block_size": float("nan"),
            "n_blocks": float("nan"),
            "n_bins": float("nan"),
            "test_frac_real": len(test) / max(1, n),
        }

    if block_size is None:
        block_size = max(8, min(24, int(round(0.04 * n))))

    row_block = np.arange(n) // block_size
    block_df = (
        pd.DataFrame(
            {
                "row_idx": np.arange(n),
                "block_id": row_block,
                y_col: data[y_col].to_numpy(dtype=float),
            }
        )
        .groupby("block_id", as_index=False)
        .agg(
            row_start=("row_idx", "min"),
            row_end=("row_idx", "max"),
            y_mean=(y_col, "mean"),
            n_rows=("row_idx", "size"),
        )
    )

    if len(block_df) < 3:
        cut = max(1, int(round((1 - test_frac) * n)))
        train = data.iloc[:cut].copy()
        test = data.iloc[cut:].copy()
        return train, test, {
            "block_size": float(block_size),
            "n_blocks": float(len(block_df)),
            "n_bins": float("nan"),
            "test_frac_real": len(test) / max(1, n),
        }

    q = min(n_bins, len(block_df))
    block_df["ha_bin"] = pd.qcut(block_df["y_mean"], q=q, duplicates="drop").astype(str)
    n_bins_eff = int(block_df["ha_bin"].nunique())

    test_blocks: set[int] = set()
    for _, grp in block_df.groupby("ha_bin", sort=False):
        grp = grp.sort_values("row_start").reset_index(drop=True)
        m = len(grp)
        if m <= 1:
            continue
        n_test_blocks = max(1, int(round(test_frac * m)))
        n_test_blocks = min(n_test_blocks, m - 1)
        pos = np.linspace(0, m - 1, num=n_test_blocks + 2)[1:-1]
        pos = np.unique(np.round(pos).astype(int))
        test_blocks.update(int(x) for x in grp.loc[pos, "block_id"].tolist())

    if not test_blocks or len(test_blocks) >= len(block_df):
        fallback = block_df.iloc[1::3]["block_id"].astype(int).tolist()
        if not fallback:
            fallback = [int(block_df.iloc[len(block_df) // 2]["block_id"])]
        test_blocks = set(fallback)

    test_mask = np.isin(row_block, sorted(test_blocks))
    train = data.loc[~test_mask].copy()
    test = data.loc[test_mask].copy()

    if train.empty or test.empty:
        cut = max(1, int(round((1 - test_frac) * n)))
        train = data.iloc[:cut].copy()
        test = data.iloc[cut:].copy()

    return train, test, {
        "block_size": float(block_size),
        "n_blocks": float(len(block_df)),
        "n_bins": float(n_bins_eff),
        "test_frac_real": len(test) / max(1, n),
    }


def run_calibration(
    aligned: pd.DataFrame,
    feature_col: str,
    include_temperature: bool = USE_TEMPERATURE_DEFAULT,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """
    Lance la calibration avec deux evaluations:
    - split chronologique 70/30 (diagnostic de derive temporelle),
    - split par blocs repartis sur la gamme d'humidite
      (plus adapte a un protocole monotone sec -> humide).

    Le mode par defaut est SANS temperature (HA ~ feature).
    """
    data = (
        aligned.sort_values("scan_id")[[feature_col, "T", "HA_ref", "scan_id"]]
        .dropna()
        .reset_index(drop=True)
    )
    n = len(data)
    cut = int(0.7 * n)
    train_chrono = data.iloc[:cut].copy()
    test_chrono = data.iloc[cut:].copy()
    train_blocked, test_blocked, blocked_meta = make_blocked_balanced_split(
        data,
        y_col="HA_ref",
        test_frac=0.30,
    )

    models: list[tuple[str, list[str]]] = [("HA ~ feature", [feature_col])]
    if include_temperature:
        models.append(("HA ~ feature + T", [feature_col, "T"]))

    metrics_rows = []
    pred_test_selected = pd.DataFrame()
    selected_model_name = "HA ~ feature + T" if include_temperature else "HA ~ feature"
    selected_holdout_split = "test_30_blocked_balanced"

    for model_name, cols in models:
        coef_all, pred_all = fit_linear_model(data, cols, y_col="HA_ref")
        m_all = metrics(data["HA_ref"].to_numpy(dtype=float), pred_all)

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
                "split_strategy": "fit_all",
                "block_size": np.nan,
                "n_blocks": np.nan,
                "n_bins": np.nan,
            }
        )

        split_specs = [
            ("chrono", "train_70_chrono", "test_30_chrono", train_chrono, test_chrono, {}),
            (
                "blocked_balanced",
                "train_70_blocked_balanced",
                "test_30_blocked_balanced",
                train_blocked,
                test_blocked,
                blocked_meta,
            ),
        ]

        for strategy_name, train_name, test_name, train, test, meta in split_specs:
            coef_train, pred_train = fit_linear_model(train, cols, y_col="HA_ref")
            X_test = np.column_stack(
                [np.ones(len(test))] + [test[c].to_numpy(dtype=float) for c in cols]
            )
            pred_test = X_test @ coef_train

            m_train = metrics(train["HA_ref"].to_numpy(dtype=float), pred_train)
            m_test = metrics(test["HA_ref"].to_numpy(dtype=float), pred_test)

            metrics_rows.append(
                {
                    "model": model_name,
                    "split": train_name,
                    "n": len(train),
                    **m_train,
                    "coef_intercept": float(coef_train[0]),
                    "coef_feature": float(coef_train[1]) if len(coef_train) > 1 else np.nan,
                    "coef_T": float(coef_train[2]) if len(coef_train) > 2 else np.nan,
                    "feature_col": feature_col,
                    "split_strategy": strategy_name,
                    "block_size": meta.get("block_size", np.nan),
                    "n_blocks": meta.get("n_blocks", np.nan),
                    "n_bins": meta.get("n_bins", np.nan),
                }
            )
            metrics_rows.append(
                {
                    "model": model_name,
                    "split": test_name,
                    "n": len(test),
                    **m_test,
                    "coef_intercept": float(coef_train[0]),
                    "coef_feature": float(coef_train[1]) if len(coef_train) > 1 else np.nan,
                    "coef_T": float(coef_train[2]) if len(coef_train) > 2 else np.nan,
                    "feature_col": feature_col,
                    "split_strategy": strategy_name,
                    "block_size": meta.get("block_size", np.nan),
                    "n_blocks": meta.get("n_blocks", np.nan),
                    "n_bins": meta.get("n_bins", np.nan),
                }
            )

            if model_name == selected_model_name and test_name == selected_holdout_split:
                pred_test_selected = pd.DataFrame(
                    {
                        "scan_id": test["scan_id"].to_numpy(dtype=int),
                        "HA_ref": test["HA_ref"].to_numpy(dtype=float),
                        "HA_pred": pred_test.astype(float),
                        "residual": (
                            test["HA_ref"].to_numpy(dtype=float) - pred_test
                        ).astype(float),
                        "model": model_name,
                        "split": test_name,
                        "split_strategy": strategy_name,
                    }
                )

    return (
        pd.DataFrame(metrics_rows),
        pred_test_selected.sort_values("scan_id").reset_index(drop=True),
        selected_model_name,
        selected_holdout_split,
    )


def make_plots(
    matching_scores: pd.DataFrame,
    aligned: pd.DataFrame,
    feature_col: str,
    calib_pred: pd.DataFrame,
    best_match_value: int,
    calibration_model_name: str,
    holdout_split_name: str,
    match_axis_col: str,
    match_axis_label: str,
    match_title: str,
) -> None:
    """Genere les figures de controle du matching et de la calibration."""
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Matching score curve
    plt.figure(figsize=(10, 4))
    plt.plot(matching_scores[match_axis_col], matching_scores["score"], marker="o", ms=3)
    plt.axvline(
        best_match_value,
        color="tab:red",
        linestyle="--",
        label=f"best={best_match_value}",
    )
    plt.xlabel(match_axis_label)
    plt.ylabel("Matching score")
    plt.title(match_title)
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
    plt.plot(p["scan_id"], p["HA_ref"], label="HA_ref", linewidth=1.5, marker="o", ms=3)
    plt.plot(p["scan_id"], p["HA_pred"], label="HA_pred", linewidth=1.5, marker="o", ms=3)
    plt.xlabel("scan_id")
    plt.ylabel("HA (g/m3)")
    plt.title(f"Calibration holdout ({holdout_split_name}) - model: {calibration_model_name}")
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
    plt.title(f"Residuals on holdout ({holdout_split_name})")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_FIG_DIR / "calibration_holdout_residuals.png", dpi=200)
    plt.close()


def resolve_signal_pattern(data_dir: Path, signal_pattern: str | None) -> str:
    """Choisit un pattern de scans raisonnable si non fourni."""
    if signal_pattern:
        return signal_pattern
    if list(data_dir.glob("*_calibration_*.txt")):
        return "*_calibration_*.txt"
    if list(data_dir.glob("Mesures*.txt")):
        return "Mesures*.txt"
    return "*.txt"


def resolve_button_path(data_dir: Path, button_path: str | None) -> Path:
    """Trouve le log bouton si le chemin n'est pas fourni explicitement."""
    if button_path:
        return Path(button_path)
    candidates = sorted(list(data_dir.glob("*.xls")) + list(data_dir.glob("*.xlsx")))
    if not candidates:
        raise FileNotFoundError(f"No button log (.xls/.xlsx) found under {data_dir}")
    preferred = [p for p in candidates if "button" in p.name.lower() or "hygro" in p.name.lower()]
    return preferred[0] if preferred else candidates[0]


def resolve_summary_path(data_dir: Path, summary_path: str | None) -> Path | None:
    """Trouve le fichier summary si present."""
    if summary_path:
        p = Path(summary_path)
        return p if p.exists() else None
    candidates = sorted(data_dir.glob("*summary*.txt"))
    return candidates[0] if candidates else None


def parse_args() -> argparse.Namespace:
    """Arguments CLI simples pour activer/desactiver l'usage de T."""
    parser = argparse.ArgumentParser(
        description="Calibration laser->HA avec matching robuste scan/bouton."
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Dossier contenant les scans laser et le log bouton.",
    )
    parser.add_argument(
        "--button-path",
        default=None,
        help="Chemin explicite vers le fichier bouton (.xls/.xlsx).",
    )
    parser.add_argument(
        "--summary-path",
        default=None,
        help="Chemin explicite vers le fichier summary si disponible.",
    )
    parser.add_argument(
        "--signal-pattern",
        default=None,
        help="Pattern glob des fichiers scans (.txt). Par defaut: auto-detection.",
    )
    parser.add_argument(
        "--with-temperature",
        action="store_true",
        help="Ajoute T dans la calibration (HA ~ feature + T). Par defaut: desactive.",
    )
    return parser.parse_args()


def main(
    include_temperature: bool = USE_TEMPERATURE_DEFAULT,
    data_dir: Path = DEFAULT_DATA_DIR,
    button_path: Path = DEFAULT_BUTTON_PATH,
    summary_path: Path | None = DEFAULT_SUMMARY_PATH,
    signal_pattern: str = DEFAULT_SIGNAL_PATTERN,
) -> None:
    OUT_REP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    df_laser = build_laser_features(data_dir, signal_pattern)
    df_btn = read_button_log(button_path)
    df_summary = read_summary(summary_path)

    feature_cols = [
        c
        for c in df_laser.columns
        if c not in {"scan_id", "scan_name", "scan_stem", "scan_dt", "scan_local_idx"}
    ]

    summary_shift, summary_corr, summary_n = validate_shift_with_summary(
        df_summary, df_btn, shift_min=-20, shift_max=20
    )
    button_period_s = float("nan")
    half_window_s = float("nan")
    has_summary_validation = bool(
        not df_summary.empty and "Abs_ref" in df_btn.columns and df_btn["Abs_ref"].dropna().any()
    )
    has_scan_dt = "scan_dt" in df_laser.columns and not df_laser["scan_dt"].dropna().empty

    if has_summary_validation:
        # Ancien workflow: validation via summary + comparaison de mappings.
        matching_scores, best_shift, aligned_shift, corr_shift = evaluate_shift_candidates(
            df_laser, df_btn, feature_cols, shift_min=-40, shift_max=40
        )
        scan_for_time = df_laser.drop(columns=["scan_dt"], errors="ignore").merge(
            df_summary[["scan_id", "scan_dt"]], on="scan_id", how="inner"
        )
        aligned_time = align_by_time(
            scan_for_time,
            df_btn,
            scan_dt_col="scan_dt",
            tol_s=12,
        )
        corr_time = compute_feature_correlations(aligned_time, feature_cols)
        score_time = mapping_score(corr_time)

        aligned_dtw = align_by_dtw(df_laser, df_btn, feature_col="F_p95", window=35)
        corr_dtw = compute_feature_correlations(aligned_dtw, feature_cols)
        score_dtw = mapping_score(corr_dtw)

        if abs(summary_corr) >= 0.98:
            best_match_value = -summary_shift
            aligned_final = align_by_shift(df_laser, df_btn, best_match_value)
            corr_final = compute_feature_correlations(aligned_final, feature_cols)
            final_method = f"index_shift_from_summary({best_match_value})"
        else:
            candidates = [
                ("index_shift", mapping_score(corr_shift), aligned_shift, corr_shift, best_shift),
                ("time_nearest", score_time, aligned_time, corr_time, best_shift),
                ("dtw", score_dtw, aligned_dtw, corr_dtw, best_shift),
            ]
            final_method, _, aligned_final, corr_final, best_match_value = max(
                candidates, key=lambda x: x[1]
            )
        match_axis_col = "shift"
        match_axis_label = "Index shift (btn_idx = scan_id + shift)"
        match_title = "Shift search for scan-button matching"
    else:
        # Nouveau workflow: recherche d'offset temporel entre scans horodates et log bouton.
        if not has_scan_dt:
            raise ValueError(
                "The current dataset has no summary validation and no scan timestamps in filenames."
            )
        button_period_s = estimate_button_period_seconds(df_btn)
        half_window_s = max(0.5, button_period_s / 2.0)
        offset_min_s, offset_max_s = estimate_offset_search_window(df_laser, df_btn, pad_s=240)
        matching_scores, best_match_value, aligned_final, corr_final = evaluate_time_offset_candidates(
            df_laser,
            df_btn,
            feature_cols,
            offset_min_s=offset_min_s,
            offset_max_s=offset_max_s,
            half_window_s=half_window_s,
        )
        final_method = "time_offset_search"
        match_axis_col = "offset_s"
        match_axis_label = "Offset applied to scan timestamps (s)"
        match_title = "Time-offset search for scan-button matching"

    best_feature_row = corr_final.iloc[
        corr_final["corr_HA"].abs().fillna(-np.inf).idxmax()
    ]
    best_feature = str(best_feature_row["feature"])

    calib_metrics, calib_pred, selected_model_name, selected_holdout_split = run_calibration(
        aligned_final,
        feature_col=best_feature,
        include_temperature=include_temperature,
    )
    make_plots(
        matching_scores,
        aligned_final,
        best_feature,
        calib_pred,
        best_match_value=best_match_value,
        calibration_model_name=selected_model_name,
        holdout_split_name=selected_holdout_split,
        match_axis_col=match_axis_col,
        match_axis_label=match_axis_label,
        match_title=match_title,
    )

    # Save tables.
    df_laser.to_csv(OUT_REP_DIR / "laser_features_all_scans.csv", index=False)
    matching_scores.to_csv(OUT_REP_DIR / "matching_shift_scores.csv", index=False)
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
                "data_dir": str(data_dir),
                "button_path": str(button_path),
                "summary_path": str(summary_path) if summary_path else "",
                "n_scans": len(df_laser),
                "n_button_rows": len(df_btn),
                "n_summary_rows": len(df_summary),
                "button_period_s": button_period_s,
                "aggregation_half_window_s": half_window_s,
                "best_match_value": best_match_value,
                "summary_validated_shift": summary_shift,
                "summary_corr_absorbance": summary_corr,
                "summary_pairs": summary_n,
                "final_method": final_method,
                "final_pairs": len(aligned_final),
                "best_feature": best_feature,
                "best_corr_HA": float(best_feature_row["corr_HA"]),
                "best_corr_Abs": float(best_feature_row["corr_Abs"]),
                "calibration_model": selected_model_name,
                "holdout_split": selected_holdout_split,
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
    if has_summary_validation:
        print(
            f"- Summary Abs_ref validation: shift={summary_shift}, corr={summary_corr:.4f}, n={summary_n}"
        )
    else:
        print(f"- Button median period: {button_period_s:.3f} s")
        print(f"- Aggregation half-window: {half_window_s:.3f} s")
        print(f"- Best time offset: {best_match_value} s")
    print(f"- Final matching method: {final_method}")
    print(f"- Final pairs: {len(aligned_final)}")
    print(
        f"- Best feature for HA: {best_feature} (corr={float(best_feature_row['corr_HA']):.4f})"
    )
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
    data_dir = Path(args.data_dir)
    button_path = resolve_button_path(data_dir, args.button_path)
    summary_path = resolve_summary_path(data_dir, args.summary_path)
    signal_pattern = resolve_signal_pattern(data_dir, args.signal_pattern)
    main(
        include_temperature=bool(args.with_temperature),
        data_dir=data_dir,
        button_path=button_path,
        summary_path=summary_path,
        signal_pattern=signal_pattern,
    )
