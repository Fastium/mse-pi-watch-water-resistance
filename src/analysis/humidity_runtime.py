from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from analysis.laser_matching_calibration import (
        compute_A_full,
        compute_I0,
        extract_features,
        read_signal,
    )
except ImportError:
    from laser_matching_calibration import (
        compute_A_full,
        compute_I0,
        extract_features,
        read_signal,
    )

DEFAULT_RUN_SUMMARY = Path("outputs/reports/laser_matching_run_summary.csv")
DEFAULT_CALIB_METRICS = Path("outputs/reports/calibration_metrics.csv")
DEFAULT_REF_PATH_LENGTH = 4.6
DEFAULT_PATH_LENGTH_UNIT = "mm"
DEFAULT_SMOOTH_WINDOW = 41
DEFAULT_K = 0.20
DEFAULT_EDGE = 20


@dataclass(frozen=True)
class HumidityCalibrationModel:
    feature_name: str
    intercept: float
    slope: float
    ref_path_length: float = DEFAULT_REF_PATH_LENGTH
    path_length_unit: str = DEFAULT_PATH_LENGTH_UNIT
    run_summary_path: str = str(DEFAULT_RUN_SUMMARY)
    calibration_metrics_path: str = str(DEFAULT_CALIB_METRICS)


def load_feature_name(
    run_summary_path: Path,
    feature_override: str | None = None,
) -> str:
    if feature_override:
        return feature_override

    if not run_summary_path.exists():
        raise FileNotFoundError(
            f"Run summary not found at {run_summary_path}. Use a feature override."
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
    intercept_override: float | None = None,
    slope_override: float | None = None,
) -> tuple[float, float]:
    if intercept_override is not None and slope_override is not None:
        return float(intercept_override), float(slope_override)
    if (intercept_override is None) != (slope_override is None):
        raise ValueError("Provide both intercept and slope together, or none.")

    if not calibration_metrics_path.exists():
        raise FileNotFoundError(
            f"Calibration metrics not found at {calibration_metrics_path}. "
            "Use manual overrides if needed."
        )

    m = pd.read_csv(calibration_metrics_path)
    req_cols = {"model", "split", "feature_col", "coef_intercept", "coef_feature"}
    if not req_cols.issubset(set(m.columns)):
        raise ValueError(
            f"Invalid calibration metrics ({calibration_metrics_path}): missing required columns."
        )

    row = m[
        (m["model"] == "HA ~ feature")
        & (m["split"] == "all")
        & (m["feature_col"] == feature_name)
    ]
    if row.empty:
        row = m[m["feature_col"] == feature_name]
    if row.empty:
        raise ValueError(
            f"No coefficients found for feature '{feature_name}' in {calibration_metrics_path}."
        )

    row = row.iloc[0]
    return float(row["coef_intercept"]), float(row["coef_feature"])


def load_calibration_model(
    run_summary_path: Path = DEFAULT_RUN_SUMMARY,
    calibration_metrics_path: Path = DEFAULT_CALIB_METRICS,
    feature_override: str | None = None,
    intercept_override: float | None = None,
    slope_override: float | None = None,
    ref_path_length: float = DEFAULT_REF_PATH_LENGTH,
    path_length_unit: str = DEFAULT_PATH_LENGTH_UNIT,
) -> HumidityCalibrationModel:
    feature_name = load_feature_name(run_summary_path, feature_override)
    intercept, slope = load_coefficients(
        calibration_metrics_path=calibration_metrics_path,
        feature_name=feature_name,
        intercept_override=intercept_override,
        slope_override=slope_override,
    )
    return HumidityCalibrationModel(
        feature_name=feature_name,
        intercept=intercept,
        slope=slope,
        ref_path_length=float(ref_path_length),
        path_length_unit=path_length_unit,
        run_summary_path=str(run_summary_path),
        calibration_metrics_path=str(calibration_metrics_path),
    )


def resolve_path_length_correction(
    path_length: float | None,
    ref_path_length: float,
) -> tuple[float, float, float]:
    current_path_length = (
        float(ref_path_length) if path_length is None else float(path_length)
    )
    ref_path_length = float(ref_path_length)
    if current_path_length <= 0 or ref_path_length <= 0:
        raise ValueError("Path lengths must be > 0.")

    return (
        float(ref_path_length / current_path_length),
        current_path_length,
        ref_path_length,
    )


def compute_absorbance_from_signal(
    signal: np.ndarray,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    k: float = DEFAULT_K,
) -> dict[str, np.ndarray]:
    I = np.asarray(signal, dtype=float).reshape(-1)
    I0 = compute_I0(I, smooth_window=smooth_window, k=k)
    A = compute_A_full(I, I0)
    return {
        "I": I,
        "I0": I0,
        "A": A,
    }


def analyze_signal(
    signal: np.ndarray,
    edge: int = DEFAULT_EDGE,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    k: float = DEFAULT_K,
) -> dict[str, Any]:
    out = compute_absorbance_from_signal(
        signal,
        smooth_window=smooth_window,
        k=k,
    )
    features = extract_features(out["A"], edge=edge)
    out["features"] = features
    return out


def predict_ha_from_signal(
    signal: np.ndarray,
    model: HumidityCalibrationModel,
    path_length: float | None = None,
    edge: int = DEFAULT_EDGE,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    k: float = DEFAULT_K,
) -> dict[str, Any]:
    analysis = analyze_signal(
        signal,
        edge=edge,
        smooth_window=smooth_window,
        k=k,
    )
    features = analysis["features"]
    if model.feature_name not in features:
        raise KeyError(
            f"Feature '{model.feature_name}' not available. "
            f"Available: {sorted(features.keys())}"
        )

    correction_factor, current_path_length, ref_path_length = (
        resolve_path_length_correction(
            path_length=path_length,
            ref_path_length=model.ref_path_length,
        )
    )
    feature_raw = float(features[model.feature_name])
    feature_value = float(feature_raw * correction_factor)
    ha_pred = float(model.intercept + model.slope * feature_value)

    return {
        **analysis,
        "feature_name": model.feature_name,
        "feature_raw": feature_raw,
        "feature_correction_factor": correction_factor,
        "feature_value": feature_value,
        "path_length": current_path_length,
        "ref_path_length": ref_path_length,
        "path_length_unit": model.path_length_unit,
        "coef_intercept": float(model.intercept),
        "coef_slope": float(model.slope),
        "HA_pred": ha_pred,
    }


def predict_ha_from_file(
    path: Path,
    model: HumidityCalibrationModel,
    path_length: float | None = None,
    edge: int = DEFAULT_EDGE,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    k: float = DEFAULT_K,
) -> dict[str, Any]:
    signal = read_signal(path)
    result = predict_ha_from_signal(
        signal=signal,
        model=model,
        path_length=path_length,
        edge=edge,
        smooth_window=smooth_window,
        k=k,
    )
    result.update(
        {
            "file": path.name,
            "file_path": str(path),
        }
    )
    return result
