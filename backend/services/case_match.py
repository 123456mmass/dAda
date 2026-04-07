"""Match live meter signatures against the committed Hioki lab baseline."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from services.dataset import load_dataset_summary, wrap_angle_deg
from services.modbus import MeterReading


BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "hioki_lab_baseline.json"


def _safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if abs(denominator) < 1e-9 else numerator / denominator


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def build_meter_signature(reading: MeterReading) -> dict:
    """Convert a live meter reading into the same relay-oriented feature space."""
    phase_rms = [abs(reading.current_a), abs(reading.current_b), abs(reading.current_c)]
    phase_mean_rms = sum(phase_rms) / 3.0 if phase_rms else 0.0
    max_dev = max(abs(value - phase_mean_rms) for value in phase_rms) if phase_rms else 0.0
    phase_balance_pct = 0.0 if phase_mean_rms == 0 else 100.0 * max_dev / phase_mean_rms

    phasors = [
        phase_rms[0] * complex(math.cos(math.radians(reading.angle_i1)), math.sin(math.radians(reading.angle_i1))),
        phase_rms[1] * complex(math.cos(math.radians(reading.angle_i2)), math.sin(math.radians(reading.angle_i2))),
        phase_rms[2] * complex(math.cos(math.radians(reading.angle_i3)), math.sin(math.radians(reading.angle_i3))),
    ]
    zero_seq_rms = abs(sum(phasors) / 3.0)

    total_phase_rms = sum(phase_rms)
    phase_shares = [
        _safe_div(phase_rms[0], total_phase_rms),
        _safe_div(phase_rms[1], total_phase_rms),
        _safe_div(phase_rms[2], total_phase_rms),
    ]

    return {
        "phase_rms": phase_rms,
        "phase_mean_rms": phase_mean_rms,
        "phase_balance_pct": phase_balance_pct,
        "zero_seq_rms": zero_seq_rms,
        "neutral_rms": abs(reading.current_n),
        "phase_shares": phase_shares,
        "phase_differences_deg": {
            "I1_to_I2": wrap_angle_deg(reading.angle_i2 - reading.angle_i1),
            "I2_to_I3": wrap_angle_deg(reading.angle_i3 - reading.angle_i2),
            "I1_to_I3": wrap_angle_deg(reading.angle_i3 - reading.angle_i1),
        },
    }


def build_baseline_signature(case_summary: dict) -> dict:
    """Extract matching features from one case in hioki_lab_baseline.json."""
    channels = case_summary["currents"]["channels"]
    phase_rms = [channels["I1"]["fundamental_rms"], channels["I2"]["fundamental_rms"], channels["I3"]["fundamental_rms"]]
    total_phase_rms = sum(phase_rms)
    return {
        "phase_rms": phase_rms,
        "phase_mean_rms": case_summary["currents"]["phase_mean_rms"],
        "phase_balance_pct": case_summary["currents"]["phase_balance_pct"],
        "zero_seq_rms": case_summary["currents"]["zero_seq_rms"],
        "neutral_rms": case_summary["currents"]["neutral_rms"],
        "phase_shares": [
            _safe_div(phase_rms[0], total_phase_rms),
            _safe_div(phase_rms[1], total_phase_rms),
            _safe_div(phase_rms[2], total_phase_rms),
        ],
        "phase_differences_deg": case_summary["currents"]["phase_differences_deg"],
    }


def score_case_match(live_signature: dict, baseline_signature: dict) -> tuple[float, dict]:
    """Return a similarity score and the normalized error components."""
    live_mean = live_signature["phase_mean_rms"]
    base_mean = baseline_signature["phase_mean_rms"]
    if live_mean > 0.0 and base_mean > 0.0:
        scale_error = _clip01(abs(math.log(live_mean / base_mean)) / math.log(10.0))
    else:
        scale_error = 1.0

    share_error = sum(
        abs(a - b)
        for a, b in zip(live_signature["phase_shares"], baseline_signature["phase_shares"])
    ) / 3.0

    angle_error = sum(
        abs(
            wrap_angle_deg(
                live_signature["phase_differences_deg"][key]
                - baseline_signature["phase_differences_deg"][key]
            )
        ) / 180.0
        for key in ("I1_to_I2", "I2_to_I3", "I1_to_I3")
    ) / 3.0

    balance_error = _clip01(
        abs(live_signature["phase_balance_pct"] - baseline_signature["phase_balance_pct"]) / 100.0
    )
    zero_seq_error = _clip01(
        abs(
            _safe_div(live_signature["zero_seq_rms"], max(live_mean, 1e-9))
            - _safe_div(baseline_signature["zero_seq_rms"], max(base_mean, 1e-9))
        )
    )
    neutral_error = _clip01(
        abs(
            _safe_div(live_signature["neutral_rms"], max(live_mean, 1e-9))
            - _safe_div(baseline_signature["neutral_rms"], max(base_mean, 1e-9))
        )
    )

    weighted_distance = (
        0.35 * share_error
        + 0.20 * scale_error
        + 0.25 * angle_error
        + 0.10 * balance_error
        + 0.05 * zero_seq_error
        + 0.05 * neutral_error
    )
    score = round(max(0.0, 100.0 * (1.0 - weighted_distance)), 3)
    return score, {
        "share_error": round(share_error, 6),
        "scale_error": round(scale_error, 6),
        "angle_error": round(angle_error, 6),
        "balance_error": round(balance_error, 6),
        "zero_seq_error": round(zero_seq_error, 6),
        "neutral_error": round(neutral_error, 6),
        "weighted_distance": round(weighted_distance, 6),
    }


@lru_cache(maxsize=1)
def get_baseline_summary() -> dict:
    """Load the committed Hioki baseline once per process."""
    return load_dataset_summary(BASELINE_PATH)


def get_baseline_overview() -> dict:
    """Return compact baseline metadata for UI/API use."""
    summary = get_baseline_summary()
    return {
        "source_root_name": summary["source_root_name"],
        "file_count": summary["file_count"],
        "group_count": summary["group_count"],
        "sections": summary["sections"],
        "groups": summary["groups"],
    }


def match_signature_to_baseline(live_signature: dict, top_n: int = 5) -> list[dict]:
    """Rank the closest lab cases for a live signature."""
    summary = get_baseline_summary()
    matches = []
    for case in summary["cases"]:
        baseline_signature = build_baseline_signature(case)
        score, components = score_case_match(live_signature, baseline_signature)
        matches.append(
            {
                "score": score,
                "case_id": case["case_id"],
                "section": case["section"],
                "step": case["step"],
                "label": case["label"],
                "group_name": case["group_name"],
                "relative_path": case["relative_path"],
                "feature_distance": components["weighted_distance"],
                "feature_errors": components,
                "baseline_signature": baseline_signature,
            }
        )

    matches.sort(key=lambda item: (-item["score"], item["feature_distance"], item["relative_path"]))
    return matches[: max(1, top_n)]


def match_meter_to_baseline(reading: MeterReading, top_n: int = 5) -> dict:
    """Convenience wrapper for live meter readings."""
    live_signature = build_meter_signature(reading)
    return {
        "signature": live_signature,
        "matches": match_signature_to_baseline(live_signature, top_n=top_n),
        "baseline": get_baseline_overview(),
    }


def build_hidden_validation(reading: MeterReading, top_n: int = 3, threshold: float = 70.0) -> dict:
    """Summarize matcher output without exposing case labels to the frontend."""
    signature = build_meter_signature(reading)
    if signature["phase_mean_rms"] < 0.05:
        return {
            "available": False,
            "consistent": False,
            "score": 0.0,
            "threshold": threshold,
            "reason": "insufficient_current",
        }

    ranked = match_signature_to_baseline(signature, top_n=top_n)
    best_score = ranked[0]["score"] if ranked else 0.0
    return {
        "available": True,
        "consistent": best_score >= threshold,
        "score": round(best_score, 3),
        "threshold": threshold,
        "reason": "matched" if ranked else "no_baseline_match",
    }
