from __future__ import annotations

"""
CLI wrapper to compute absolute humidity (HA) from one scan file or a directory
of scan files.

Per file, the script:
1) reads the raw signal I(t) from a .txt file
2) reconstructs the baseline I0(t)
3) computes the absorbance A(t) = -ln(I / I0)
4) extracts all laser features and keeps the feature selected by the latest
   calibration run by default
5) optionally applies a path-length correction:
      feature_value = feature_raw * (L_ref / L)
6) computes:
      HA_pred = intercept + slope * feature_value

By default, the script loads:
- the feature name from `outputs/reports/laser_matching_run_summary.csv`
- the coefficients from `outputs/reports/calibration_metrics.csv`

The actual signal-processing and prediction logic lives in:
- `src/analysis/humidity_runtime.py`

Quick examples:
    # 1) Predict HA for one scan file
    python src/analysis/predict_ha.py \
      --input data/raw/calibration/20260511_211415_calibration_1.txt \
      --output outputs/reports/ha_prediction_one.csv

    # 2) Predict HA for a whole folder of calibration scans
    python src/analysis/predict_ha.py \
      --input data/raw/calibration \
      --pattern "*_calibration_*.txt" \
      --output outputs/reports/ha_predictions_calibration.csv

    # 3) Save enriched per-scan CSV files with t, I, I0, A
    python src/analysis/predict_ha.py \
      --input data/raw/calibration/20260511_211415_calibration_1.txt \
      --save-enriched

    # 4) Optional: override calibration manually
    python src/analysis/predict_ha.py \
      --input data/raw/calibration/20260511_211415_calibration_1.txt \
      --feature F_area_total \
      --intercept 2.76022528799 \
      --slope 0.04483201289

    # 5) Optional: apply path-length correction using the fixed L_ref from the code
    python src/analysis/predict_ha.py \
      --input data/raw/calibration/20260511_211415_calibration_1.txt \
      --path-length 45.92
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
try:
    from analysis.humidity_runtime import (
        DEFAULT_PATH_LENGTH_UNIT,
        DEFAULT_REF_PATH_LENGTH,
        HumidityCalibrationModel,
        load_calibration_model,
        predict_ha_from_file,
    )
except ImportError:
    from humidity_runtime import (
        DEFAULT_PATH_LENGTH_UNIT,
        DEFAULT_REF_PATH_LENGTH,
        HumidityCalibrationModel,
        load_calibration_model,
        predict_ha_from_file,
    )

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
    parser.add_argument(
        "--path-length",
        type=float,
        default=None,
        help=(
            "Effective optical path length L for the current measurement. "
            f"If omitted, the script uses L = L_ref = {DEFAULT_REF_PATH_LENGTH} {DEFAULT_PATH_LENGTH_UNIT}."
        ),
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
            raise FileNotFoundError(
                f"No files matched pattern '{pattern}' in {input_path}"
            )
        return files
    raise FileNotFoundError(f"Input path not found: {input_path}")


def predict_one_file(
    path: Path,
    model: HumidityCalibrationModel,
    path_length: float | None,
    save_enriched: bool,
    enriched_dir: Path,
) -> dict[str, float | str | int]:
    result = predict_ha_from_file(
        path=path,
        model=model,
        path_length=path_length,
    )

    if save_enriched:
        enriched_dir.mkdir(parents=True, exist_ok=True)
        I = np.asarray(result["I"], dtype=float)
        I0 = np.asarray(result["I0"], dtype=float)
        A = np.asarray(result["A"], dtype=float)
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
    result["scan_id"] = scan_id if scan_id is not None else ""
    result.pop("I", None)
    result.pop("I0", None)
    result.pop("A", None)
    result.pop("features", None)
    return result


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    run_summary_path = Path(args.run_summary)
    calibration_metrics_path = Path(args.calibration_metrics)
    enriched_dir = Path(args.enriched_dir)

    files = collect_input_files(input_path, args.pattern)
    model = load_calibration_model(
        run_summary_path=run_summary_path,
        calibration_metrics_path=calibration_metrics_path,
        feature_override=args.feature,
        intercept_override=args.intercept,
        slope_override=args.slope,
    )

    rows = []
    for p in files:
        rows.append(
            predict_one_file(
                path=p,
                model=model,
                path_length=args.path_length,
                save_enriched=bool(args.save_enriched),
                enriched_dir=enriched_dir,
            )
        )

    df_out = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False)

    print("OK")
    print(f"- Files processed: {len(df_out)}")
    print(f"- Feature used: {model.feature_name}")
    print(
        "- Path-length correction: feature_value = feature_raw * (L_ref / L)"
    )
    print(
        f"- Formula: HA = {model.intercept:.8f} + {model.slope:.8f} * feature_value"
    )
    print(f"- Output CSV: {output_path}")
    if args.save_enriched:
        print(f"- Enriched per-scan CSV dir: {enriched_dir}")


if __name__ == "__main__":
    main()
