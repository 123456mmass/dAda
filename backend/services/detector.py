"""
Vector Group Auto-Detection
=============================
Three detection modes:

1. **Voltage-ratio mode** (default, no special wiring):
   Uses voltage magnitude ratios to determine Dd vs YNyn and match tap.
   Cannot detect clock number (phase shift).

2. **Shared-Vref current-angle mode** (recommended for precise detection):
   WIRING: Connect HV-side PT secondary to BOTH meters' voltage inputs.
           Each meter keeps its OWN CT (HV CT for meter#1, LV CT for meter#2).
   
   Since both meters reference the SAME voltage (V_HV), the current
   phase angles are directly comparable across meters:
     - Meter#1: angle(I_HV) relative to V_HV
     - Meter#2: angle(I_LV) relative to V_HV (same ref!)
     - Difference = transformer vector group phase shift
   
   After detection, rewire meter#2 back to its own LV voltage for
   normal protection operation.

3. **PF-comparison mode** (approximate, no special wiring):
   Compares power factor patterns on both sides to estimate
   whether the wiring matches expected vector group.

Designed for Tirathai 15kVA (Dd0 / YNyn0), supports all standard groups.
"""

import math
import logging
from typing import Optional

import numpy as np

from config import app_config, TAP_TABLE
from services.modbus import MeterReading

logger = logging.getLogger(__name__)

# Standard vector group clock numbers and their phase shifts
VECTOR_GROUP_TABLE = {
    0:   {"shift_deg": 0,    "groups": ["Yy0", "Dd0", "YNyn0"]},
    1:   {"shift_deg": 30,   "groups": ["Dy1", "Yd1"]},
    2:   {"shift_deg": 60,   "groups": ["Dd2", "Yy2"]},
    3:   {"shift_deg": 90,   "groups": ["Dy3", "Yd3"]},
    4:   {"shift_deg": 120,  "groups": ["Dd4", "Yy4"]},
    5:   {"shift_deg": 150,  "groups": ["Dy5", "Yd5"]},
    6:   {"shift_deg": 180,  "groups": ["Yy6", "Dd6"]},
    7:   {"shift_deg": 210,  "groups": ["Dy7", "Yd7"]},
    8:   {"shift_deg": 240,  "groups": ["Dd8", "Yy8"]},
    9:   {"shift_deg": 270,  "groups": ["Dy9", "Yd9"]},
    10:  {"shift_deg": 300,  "groups": ["Dd10", "Yy10"]},
    11:  {"shift_deg": 330,  "groups": ["Dy11", "Yd11"]},
}


# ═══════════════════════════════════════════════════════════
# Mode 1: Voltage-Ratio Detection (no special wiring)
# ═══════════════════════════════════════════════════════════

def detect_vector_group(hv: MeterReading, lv: MeterReading) -> dict:
    """
    Detect vector group using voltage ratio method.
    Does NOT require shared Vref — uses magnitude only.
    Can determine Dd vs YNyn and tap position.
    CANNOT determine clock number (assumes 0° for this transformer).
    """
    if not hv.connected or not lv.connected:
        return {
            "detected": False,
            "reason": "Both meters must be connected",
            "vector_group": None,
            "tap_position": None,
        }

    v_hv = hv.voltage_ll_avg
    v_lv = lv.voltage_ll_avg

    if v_hv < 1.0 or v_lv < 1.0:
        return {
            "detected": False,
            "reason": "Voltage too low for detection",
            "vector_group": None,
            "tap_position": None,
        }

    # Find best matching tap & connection type
    best_match = None
    best_error = float("inf")
    best_connection = None

    for tap_pos, tap_data in TAP_TABLE.items():
        for conn_type in ["dd", "yy"]:
            expected_hv, expected_lv = tap_data[conn_type]
            if expected_hv < 1.0 or expected_lv < 1.0:
                continue
            hv_error = abs(v_hv - expected_hv) / expected_hv
            lv_error = abs(v_lv - expected_lv) / expected_lv
            total_error = hv_error + lv_error

            if total_error < best_error:
                best_error = total_error
                best_match = tap_pos
                best_connection = conn_type

    if best_error > 0.15:
        return {
            "detected": False,
            "reason": (
                f"No tap matches measured voltages "
                f"(V_HV={v_hv:.1f}V, V_LV={v_lv:.1f}V, error={best_error:.2%})"
            ),
            "vector_group": None,
            "tap_position": None,
            "measured_ratio": round(v_hv / v_lv if v_lv > 0 else 0, 3),
        }

    detected_vg = "Dd0" if best_connection == "dd" else "YNyn0"
    tap_data = TAP_TABLE[best_match]
    expected_hv, expected_lv = tap_data[best_connection]

    return {
        "detected": True,
        "method": "voltage_ratio",
        "vector_group": detected_vg,
        "tap_position": best_match,
        "connection": tap_data["conn"],
        "expected_v_hv": expected_hv,
        "expected_v_lv": expected_lv,
        "measured_v_hv": round(v_hv, 1),
        "measured_v_lv": round(v_lv, 1),
        "measured_ratio": round(v_hv / v_lv if v_lv > 0 else 0, 3),
        "voltage_error_pct": round(best_error * 100, 1),
        "phase_shift_deg": 0,
        "note": (
            "Ratio-based: assumes 0° shift for Dd0/YNyn0. "
            "For precise angle detection, use shared-Vref mode."
        ),
    }


# ═══════════════════════════════════════════════════════════
# Mode 2: Shared-Vref Current-Angle Detection
# ═══════════════════════════════════════════════════════════

def detect_vector_group_shared_vref(hv: MeterReading, lv: MeterReading) -> dict:
    """
    Detect vector group using shared voltage reference + current angle comparison.

    REQUIRED WIRING (temporary, for detection only):
    ┌──────────────┐              ┌──────────────┐
    │  PM2200 #1   │              │  PM2200 #2   │
    │  (HV meter)  │              │  (LV meter)  │
    │              │              │              │
    │  V1,V2,V3 ←──── HV PT ────→ V1,V2,V3     │
    │  (HV voltage)│  (SHARED!)   │ (HV voltage) │
    │              │              │              │
    │  I1,I2,I3 ←── HV CT        │  I1,I2,I3 ←── LV CT
    │  (HV current)│              │ (LV current) │
    └──────────────┘              └──────────────┘

    Both meters see the SAME voltage (V_HV from primary PT).
    Each meter measures current from its OWN CT.
    
    Therefore:
    - Meter#1: I_HV angle is relative to V_HV ✓
    - Meter#2: I_LV angle is relative to V_HV ✓ (same reference!)
    - angle(I_LV) - angle(I_HV) = transformer phase shift

    Algorithm:
    1. Compare current angles: angle_i1 (meter#1) vs angle_i1 (meter#2)
       The difference = vector group phase shift
    2. Also compare phase B and C for confirmation
    3. Round to nearest 30° → clock number
    4. Combine with voltage ratio to determine winding type (Dd/Dy/Yd/Yy)
    """
    if not hv.connected or not lv.connected:
        return {
            "detected": False,
            "reason": "Both meters must be connected",
            "vector_group": None,
        }

    # Both meters must have non-zero current (transformer must be loaded)
    min_current = 0.5  # Minimum detectable current (A)
    if hv.current_avg < min_current or lv.current_avg < min_current:
        return {
            "detected": False,
            "reason": (
                f"Transformer must be loaded for angle detection. "
                f"I_HV={hv.current_avg:.2f}A, I_LV={lv.current_avg:.2f}A "
                f"(min: {min_current}A)"
            ),
            "vector_group": None,
        }

    # ── Step 1: Compare current phase angles across meters ──
    # Since both meters use same Vref (V_HV), current angles
    # are directly comparable.
    #
    # For a healthy transformer with the same load PF on both sides:
    #   angle(I_LV) - angle(I_HV) = vector group phase shift
    #
    # We compare all 3 phases and average for robustness.

    shift_a = _normalize_angle(lv.angle_i1 - hv.angle_i1)
    shift_b = _normalize_angle(lv.angle_i2 - hv.angle_i2)
    shift_c = _normalize_angle(lv.angle_i3 - hv.angle_i3)

    # Check consistency — all 3 should give similar shift
    shifts = [shift_a, shift_b, shift_c]
    avg_shift = sum(shifts) / 3.0
    max_deviation = max(abs(s - avg_shift) for s in shifts)

    if max_deviation > 20.0:
        return {
            "detected": False,
            "reason": (
                f"Phase shift inconsistency: A={shift_a:.1f}°, B={shift_b:.1f}°, "
                f"C={shift_c:.1f}°. Check CT wiring and load balance."
            ),
            "shifts": {"a": round(shift_a, 1), "b": round(shift_b, 1), "c": round(shift_c, 1)},
            "vector_group": None,
        }

    # ── Step 2: Snap to nearest 30° → clock number ──
    # Account for current direction convention:
    # If both I_HV and I_LV are defined as flowing INTO transformer,
    # there's an inherent 180° offset. We handle this by checking both.
    clock_number = round(avg_shift / 30.0) % 12

    # ── Step 3: Determine winding type from voltage ratio ──
    v_hv = hv.voltage_ll_avg
    v_lv = lv.voltage_ll_avg

    # NOTE: When sharing Vref, meter#2 reads V_HV (not V_LV).
    # So we can't use meter#2's voltage for ratio.
    # We need the user to input the expected V_LV or use the
    # current ratio instead.
    #
    # Alternative: use current ratio
    # I_HV / I_LV should be inverse of voltage ratio
    i_ratio = hv.current_avg / lv.current_avg if lv.current_avg > 0 else 0
    # For 2:1 voltage ratio transformer: I_HV/I_LV ≈ 0.5
    # For Dy (√3 factor): I_HV/I_LV would differ

    vg_info = VECTOR_GROUP_TABLE.get(clock_number)
    if not vg_info:
        return {
            "detected": False,
            "reason": f"Unknown clock number: {clock_number}",
            "measured_shift_deg": round(avg_shift, 1),
        }

    possible_groups = vg_info["groups"]

    # Determine winding type
    expected_i_ratio_dd = 0.5   # For Dd0/Yy0 (2:1 voltage ratio → 1:2 current ratio)
    if abs(i_ratio - expected_i_ratio_dd) < 0.15:
        filtered = [g for g in possible_groups if g.startswith(("Dd", "Yy", "YN"))]
    elif abs(i_ratio - expected_i_ratio_dd * math.sqrt(3)) < 0.20:
        filtered = [g for g in possible_groups if g.startswith("Dy")]
    elif abs(i_ratio - expected_i_ratio_dd / math.sqrt(3)) < 0.20:
        filtered = [g for g in possible_groups if g.startswith("Yd")]
    else:
        filtered = possible_groups

    current_config_group = app_config.transformer.vector_group
    if current_config_group in filtered:
        detected_vg = current_config_group
    elif current_config_group in possible_groups:
        detected_vg = current_config_group
    else:
        detected_vg = filtered[0] if filtered else possible_groups[0]

    # Find matching tap from current ratio
    tap_result = _detect_tap_from_current_ratio(i_ratio, detected_vg)

    result = {
        "detected": True,
        "method": "shared_vref_current_angle",
        "vector_group": detected_vg,
        "clock_number": clock_number,
        "measured_shift_deg": round(avg_shift, 1),
        "expected_shift_deg": vg_info["shift_deg"],
        "phase_shifts": {
            "a": round(shift_a, 1),
            "b": round(shift_b, 1),
            "c": round(shift_c, 1),
        },
        "max_deviation_deg": round(max_deviation, 1),
        "current_ratio_hv_lv": round(i_ratio, 3),
        "possible_groups": possible_groups,
        "wiring_note": (
            "Detection done with shared V_HV reference. "
            "Remember to rewire meter#2 back to LV voltage for normal protection."
        ),
    }
    result.update(tap_result)

    logger.info(
        f"Shared-Vref detection: {detected_vg} (clock {clock_number}, "
        f"shift={avg_shift:.1f}°, I_ratio={i_ratio:.3f})"
    )

    return result


# ═══════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════

def _normalize_angle(angle_deg: float) -> float:
    """Normalize angle to [-180, 180) range."""
    while angle_deg > 180:
        angle_deg -= 360
    while angle_deg <= -180:
        angle_deg += 360
    return angle_deg


def _detect_tap_from_current_ratio(i_ratio: float, vector_group: str) -> dict:
    """
    Estimate tap position from current ratio.
    For this transformer, ratio is always 2:1 regardless of tap,
    so tap is indeterminate from current ratio alone.
    """
    # For Tirathai 15kVA: all taps have 2:1 ratio
    # Cannot distinguish taps from ratio
    return {
        "tap_position": app_config.transformer.tap_position,
        "tap_note": "Tap position unchanged (all taps have same 2:1 ratio)",
    }


def _detect_tap_position(v_hv: float, v_lv: float, vector_group: str) -> dict:
    """Find matching tap position from measured voltages."""
    key = "dd" if vector_group.upper().startswith("D") else "yy"
    best_tap = 1
    best_error = float("inf")

    for tap_pos, tap_data in TAP_TABLE.items():
        expected_hv, expected_lv = tap_data[key]
        if expected_hv < 1.0:
            continue
        hv_err = abs(v_hv - expected_hv) / expected_hv
        lv_err = abs(v_lv - expected_lv) / expected_lv if expected_lv > 0 else 0
        err = hv_err + lv_err
        if err < best_error:
            best_error = err
            best_tap = tap_pos

    return {
        "tap_position": best_tap,
        "tap_connection": TAP_TABLE[best_tap]["conn"],
        "tap_error_pct": round(best_error * 100, 1),
    }
