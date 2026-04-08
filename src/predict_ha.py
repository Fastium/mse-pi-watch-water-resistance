from __future__ import annotations

"""
Inference script: predict absolute humidity (HA) from laser scan files.

Pipeline per file:
1) read I(t) from .txt
2) build baseline I0(t)
3) compute absorbance series A(t) = -ln(I/I0)
4) extract feature (default: best feature from calibration run summary)
5) predict HA with linear formula: HA = intercept + slope * feature
(feature = F_p95 for us)

Usage examples:
    python src/predict_ha.py --input data/raw/Mesures27062024/Mesures27062024_578.txt
    python src/predict_ha.py --input data/raw/Mesures27062024 --output outputs/reports/ha_predictions_new.csv

How to use (quick):
    # 1) Predict HA for one file (1 ligne de sortie)
    python src/predict_ha.py \
      --input data/raw/Mesures27062024/Mesures27062024_578.txt \
      --output outputs/reports/ha_prediction_578.csv

    # 2) Predict HA for all scans in a folder (1 ligne par fichier .txt)
    python src/predict_ha.py \
      --input data/raw/Mesures27062024 \
      --pattern "Mesures27062024_*.txt" \
      --output outputs/reports/ha_predictions_all.csv

    # 3) Optional: override calibration manually
    python src/predict_ha.py \
      --input data/raw/Mesures27062024/Mesures27062024_578.txt \
      --feature F_p95 \
      --intercept -1.9583817352 \
      --slope 1669.54392698
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from laser_matching_calibration import compute_A_full, compute_I0, extract_features, read_signal


DEFAULT_PATTERN = "Mesures*.txt"
DEFAULT_RUN_SUMMARY = Path("outputs/reports/laser_matching_run_summary.csv")
DEFAULT_CALIB_METRICS = Path("outputs/reports/calibration_metrics.csv")
DEFAULT_OUTPUT = Path("outputs/reports/ha_predictions.csv")
DEFAULT_ENRICHED_DIR = Path("data/processed/enriched_with_A_pred")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict absolute humidity (HA) from one scan file or a directory of scan files."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to one .txt scan file OR a directory containing scan files.",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help=f"Glob pattern used when --input is a directory (default: {DEFAULT_PATTERN}).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output CSV path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--run-summary",
        default=str(DEFAULT_RUN_SUMMARY),
        help="CSV path for run summary (used to auto-select feature).",
    )
    parser.add_argument(
        "--calibration-metrics",
        default=str(DEFAULT_CALIB_METRICS),
        help="CSV path for calibration metrics (used to auto-load coefficients).",
    )
    parser.add_argument(
        "--feature",
        default=None,
        help="Feature name override (default: auto from run summary).",
    )
    parser.add_argument(
        "--intercept",
        type=float,
        default=None,
        help="Intercept override for HA = intercept + slope*feature.",
    )
    parser.add_argument(
        "--slope",
        type=float,
        default=None,
        help="Slope override for HA = intercept + slope*feature.",
    )
    parser.add_argument(
        "--save-enriched",
        action="store_true",
        help="If set, save per-scan enriched CSV with t, I, I0, A.",
    )
    parser.add_argument(
        "--enriched-dir",
        default=str(DEFAULT_ENRICHED_DIR),
        help=f"Directory for enriched CSV files (default: {DEFAULT_ENRICHED_DIR}).",
    )
    return parser.parse_args()


def parse_scan_id(path: Path) -> int | None:
    """Extract numeric scan_id from a filename suffix like *_578.txt."""
    try:
        return int(path.stem.split("_")[-1])
    except Exception:
        return None


def collect_input_files(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        files = sorted(
            input_path.glob(pattern),
            key=lambda p: (
                parse_scan_id(p) is None,
                parse_scan_id(p) if parse_scan_id(p) is not None else p.name,
                p.name,
            ),
        )
        if not files:
            raise FileNotFoundError(f"No files matched pattern '{pattern}' in {input_path}")
        return files
    raise FileNotFoundError(f"Input path not found: {input_path}")


def load_feature_name(run_summary_path: Path, feature_override: str | None) -> str:
    if feature_override:
        return feature_override

    if not run_summary_path.exists():
        raise FileNotFoundError(
            f"Run summary not found at {run_summary_path}. Use --feature to set one manually."
        )

    df = pd.read_csv(run_summary_path)
    if "best_feature" not in df.columns or df.empty:
        raise ValueError(
            f"Invalid run summary ({run_summary_path}): missing best_feature column or empty file."
        )
    return str(df.loc[0, "best_feature"])


def load_coefficients(
    calibration_metrics_path: Path,
    feature_name: str,
    intercept_override: float | None,
    slope_override: float | None,
) -> tuple[float, float]:
    if intercept_override is not None and slope_override is not None:
        return float(intercept_override), float(slope_override)
    if (intercept_override is None) != (slope_override is None):
        raise ValueError("Provide both --intercept and --slope together, or none.")

    if not calibration_metrics_path.exists():
        raise FileNotFoundError(
            f"Calibration metrics not found at {calibration_metrics_path}. "
            "Use --intercept and --slope to provide coefficients manually."
        )

    m = pd.read_csv(calibration_metrics_path)
    req_cols = {"model", "split", "feature_col", "coef_intercept", "coef_feature"}
    if not req_cols.issubset(set(m.columns)):
        raise ValueError(
            f"Invalid calibration metrics ({calibration_metrics_path}): missing required columns."
        )

    # Prefer the non-temperature model, split=all.
    row = m[
        (m["model"] == "HA ~ feature")
        & (m["split"] == "all")
        & (m["feature_col"] == feature_name)
    ]
    if row.empty:
        # Fallback on first matching row for feature.
        row = m[m["feature_col"] == feature_name]
    if row.empty:
        raise ValueError(
            f"No coefficients found for feature '{feature_name}' in {calibration_metrics_path}."
        )

    row = row.iloc[0]
    intercept = float(row["coef_intercept"])
    slope = float(row["coef_feature"])
    return intercept, slope


def predict_one_file(
    path: Path,
    feature_name: str,
    intercept: float,
    slope: float,
    save_enriched: bool,
    enriched_dir: Path,
) -> dict[str, float | str | int]:
    I = read_signal(path)
    I0 = compute_I0(I, smooth_window=41, k=0.20)
    A = compute_A_full(I, I0)
    feat = extract_features(A, edge=20)

    if feature_name not in feat:
        raise KeyError(
            f"Feature '{feature_name}' not available. Available: {sorted(feat.keys())}"
        )

    fval = float(feat[feature_name])
    ha_pred = float(intercept + slope * fval)

    if save_enriched:
        enriched_dir.mkdir(parents=True, exist_ok=True)
        t = np.arange(I.size, dtype=int)
        out = pd.DataFrame(
            {
                "t": t,
                "I": I.astype(float),
                "I0": I0.astype(float),
                "A": A.astype(float),
            }
        )
        out.to_csv(enriched_dir / f"{path.stem}_enriched.csv", index=False)

    scan_id = parse_scan_id(path)

    return {
        "file": path.name,
        "file_path": str(path),
        "scan_id": scan_id if scan_id is not None else "",
        "feature_name": feature_name,
        "feature_value": fval,
        "coef_intercept": intercept,
        "coef_slope": slope,
        "HA_pred": ha_pred,
    }


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    run_summary_path = Path(args.run_summary)
    calibration_metrics_path = Path(args.calibration_metrics)
    enriched_dir = Path(args.enriched_dir)

    files = collect_input_files(input_path, args.pattern)
    feature_name = load_feature_name(run_summary_path, args.feature)
    intercept, slope = load_coefficients(
        calibration_metrics_path=calibration_metrics_path,
        feature_name=feature_name,
        intercept_override=args.intercept,
        slope_override=args.slope,
    )

    rows = []
    for p in files:
        rows.append(
            predict_one_file(
                path=p,
                feature_name=feature_name,
                intercept=intercept,
                slope=slope,
                save_enriched=bool(args.save_enriched),
                enriched_dir=enriched_dir,
            )
        )

    df_out = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False)

    print("OK")
    print(f"- Files processed: {len(df_out)}")
    print(f"- Feature used: {feature_name}")
    print(f"- Formula: HA = {intercept:.8f} + {slope:.8f} * {feature_name}")
    print(f"- Output CSV: {output_path}")
    if args.save_enriched:
        print(f"- Enriched per-scan CSV dir: {enriched_dir}")


if __name__ == "__main__":
    main()
