from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from analysis.laser_matching_calibration import (
        estimate_button_period_seconds,
        metrics,
        read_button_log,
    )
except ImportError:
    from laser_matching_calibration import (
        estimate_button_period_seconds,
        metrics,
        read_button_log,
    )

DEFAULT_BUTTON_PATH = Path("data/raw/verification_measure/button-verification.xls")
DEFAULT_PRED_PATH = Path("data/raw/verification_measure/measure_20260522_074042_HA.txt")
DEFAULT_OUTPUT_DIR = Path("outputs/verification_measure")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare runtime-predicted HA to HygroButton reference measurements."
    )
    parser.add_argument(
        "--button-path",
        default=str(DEFAULT_BUTTON_PATH),
        help=f"Path to the HygroButton file (default: {DEFAULT_BUTTON_PATH}).",
    )
    parser.add_argument(
        "--prediction-path",
        default=str(DEFAULT_PRED_PATH),
        help=f"Path to the runtime/exported HA file (default: {DEFAULT_PRED_PATH}).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for aligned CSV, metrics CSV and figures (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser.parse_args()


def read_predicted_ha(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_csv(path, skipinitialspace=True)
    required = {"Timestamp", "Relative_Time_s", "Absolute_Humidity"}
    if not required.issubset(df.columns):
        raise ValueError(f"Invalid prediction file {path}: missing columns {sorted(required)}")

    start_dt = pd.to_datetime(df["Timestamp"].iloc[0], errors="raise")
    rel_s = pd.to_numeric(df["Relative_Time_s"], errors="coerce")
    ha = pd.to_numeric(df["Absolute_Humidity"], errors="coerce")

    out = pd.DataFrame(
        {
            "pred_dt": start_dt + pd.to_timedelta(rel_s, unit="s"),
            "Relative_Time_s": rel_s,
            "HA_pred_runtime": ha,
        }
    ).dropna()

    return out.sort_values("pred_dt").reset_index(drop=True)


def align_prediction_to_button(
    df_pred: pd.DataFrame,
    df_btn: pd.DataFrame,
    half_window_s: float,
) -> pd.DataFrame:
    pred = df_pred.sort_values("pred_dt").reset_index(drop=True).copy()
    btn = df_btn.sort_values("btn_dt").reset_index(drop=True).copy()

    merged = pd.merge_asof(
        pred,
        btn[["btn_dt", "btn_idx", "HA_ref", "T", "RH_ref", "dew_ref"]],
        left_on="pred_dt",
        right_on="btn_dt",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=half_window_s),
    ).dropna(subset=["btn_idx"])

    merged["btn_idx"] = merged["btn_idx"].astype(int)
    grouped = (
        merged.groupby("btn_idx", as_index=False)
        .agg(
            btn_dt=("btn_dt", "first"),
            HA_ref=("HA_ref", "first"),
            T=("T", "first"),
            RH_ref=("RH_ref", "first"),
            dew_ref=("dew_ref", "first"),
            HA_pred=("HA_pred_runtime", "mean"),
            HA_pred_std=("HA_pred_runtime", "std"),
            pred_points=("HA_pred_runtime", "size"),
            pred_dt_first=("pred_dt", "min"),
            pred_dt_last=("pred_dt", "max"),
        )
        .sort_values("btn_dt")
        .reset_index(drop=True)
    )

    grouped["HA_pred_std"] = grouped["HA_pred_std"].fillna(0.0)
    grouped["time_err_center_s"] = (
        grouped["btn_dt"] - (
            grouped["pred_dt_first"]
            + (grouped["pred_dt_last"] - grouped["pred_dt_first"]) / 2
        )
    ).dt.total_seconds()
    grouped["residual"] = grouped["HA_ref"] - grouped["HA_pred"]
    return grouped


def build_metrics(aligned: pd.DataFrame, button_period_s: float, half_window_s: float) -> pd.DataFrame:
    y_true = aligned["HA_ref"].to_numpy(dtype=float)
    y_pred = aligned["HA_pred"].to_numpy(dtype=float)
    m = metrics(y_true, y_pred)
    corr = (
        float(np.corrcoef(y_true, y_pred)[0, 1])
        if len(aligned) >= 2
        else float("nan")
    )
    row = {
        "n_pairs": len(aligned),
        "rmse": m["rmse"],
        "mae": m["mae"],
        "mape_pct": m["mape_pct"],
        "r2": m["r2"],
        "corr_pearson": corr,
        "bias_mean": float(np.mean(y_pred - y_true)),
        "residual_mean": float(np.mean(aligned["residual"])),
        "residual_std": float(np.std(aligned["residual"], ddof=1)) if len(aligned) > 1 else 0.0,
        "button_period_s": float(button_period_s),
        "half_window_s": float(half_window_s),
        "mean_pred_points_per_button": float(np.mean(aligned["pred_points"])),
    }
    return pd.DataFrame([row])


def make_plots(aligned: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    a = aligned.sort_values("btn_dt").reset_index(drop=True)

    plt.figure(figsize=(11, 4))
    plt.plot(a["btn_dt"], a["HA_ref"], label="HA_ref (button)", linewidth=2)
    plt.plot(a["btn_dt"], a["HA_pred"], label="HA_pred (runtime mean)", linewidth=2)
    plt.xlabel("Time")
    plt.ylabel("Absolute humidity (g/m3)")
    plt.title("Verification measure: runtime HA vs HygroButton HA")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "verification_timeseries.png", dpi=200)
    plt.close()

    x = a["HA_pred"].to_numpy(dtype=float)
    y = a["HA_ref"].to_numpy(dtype=float)
    lo = float(min(np.min(x), np.min(y)))
    hi = float(max(np.max(x), np.max(y)))
    plt.figure(figsize=(5.5, 5.5))
    plt.scatter(x, y, s=16, alpha=0.7)
    plt.plot([lo, hi], [lo, hi], color="tab:red", linestyle="--", linewidth=2)
    plt.xlabel("HA_pred (runtime)")
    plt.ylabel("HA_ref (button)")
    plt.title("Verification scatter: HA_pred vs HA_ref")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "verification_scatter.png", dpi=200)
    plt.close()

    plt.figure(figsize=(5.5, 5.5))
    plt.scatter(a["HA_pred"], a["residual"], s=16, alpha=0.7)
    plt.axhline(0.0, color="tab:red", linestyle="--", linewidth=2)
    plt.xlabel("HA_pred (runtime)")
    plt.ylabel("Residual = HA_ref - HA_pred")
    plt.title("Verification residuals")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "verification_residuals.png", dpi=200)
    plt.close()


def main() -> None:
    args = parse_args()
    button_path = Path(args.button_path)
    pred_path = Path(args.prediction_path)
    out_dir = Path(args.output_dir)

    df_btn = read_button_log(button_path)
    df_pred = read_predicted_ha(pred_path)

    button_period_s = estimate_button_period_seconds(df_btn)
    half_window_s = max(0.5, button_period_s / 2.0)
    aligned = align_prediction_to_button(df_pred, df_btn, half_window_s=half_window_s)
    metric_df = build_metrics(aligned, button_period_s=button_period_s, half_window_s=half_window_s)

    out_dir.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(out_dir / "verification_aligned.csv", index=False)
    metric_df.to_csv(out_dir / "verification_metrics.csv", index=False)
    make_plots(aligned, out_dir)

    print("OK")
    print(f"- Button rows: {len(df_btn)}")
    print(f"- Runtime rows: {len(df_pred)}")
    print(f"- Overlapping aligned pairs: {len(aligned)}")
    print(f"- Button median period: {button_period_s:.3f} s")
    print(f"- Half-window used: {half_window_s:.3f} s")
    print(metric_df.to_string(index=False))
    print(f"- Outputs: {out_dir}")


if __name__ == "__main__":
    main()
