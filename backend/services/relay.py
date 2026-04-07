"""
Differential Relay Service
===========================
System operates as a pipeline:
  Phase 1: DETECTION — Auto-detect vector group from voltage ratios
  Phase 2: PROTECTION — Differential relay with detected vector group

Both phases work together:
  - Detection runs first when meters connect (or on demand)
  - Once detected, protection starts automatically
  - Detection can be re-triggered at any time
  - Protection always uses latest detected/configured vector group

Designed for Tirathai 15kVA transformer with Dd0 or YNyn0 connection.
"""

import math
import time
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from config import app_config, normalize_vector_group, parse_vector_group, vector_group_family
from services.case_match import build_hidden_validation
from services.modbus import MeterReading

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Vector Group Compensation Matrices
# ─────────────────────────────────────────────
_INV_SQRT3 = 1.0 / math.sqrt(3)

COMPENSATION_MATRICES = {
    "Yy0":   np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
    "Dd0":   np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
    "YNyn0": np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
    "Dy1":  _INV_SQRT3 * np.array([[1, -1, 0], [0, 1, -1], [-1, 0, 1]], dtype=float),
    "Yd1":  _INV_SQRT3 * np.array([[1, -1, 0], [0, 1, -1], [-1, 0, 1]], dtype=float),
    "Dy11": _INV_SQRT3 * np.array([[1, 0, -1], [-1, 1, 0], [0, -1, 1]], dtype=float),
    "Yd11": _INV_SQRT3 * np.array([[1, 0, -1], [-1, 1, 0], [0, -1, 1]], dtype=float),
    "Yy6":  np.array([[-1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=float),
    "Dd6":  np.array([[-1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=float),
    "Dy5":  _INV_SQRT3 * np.array([[-1, 1, 0], [0, -1, 1], [1, 0, -1]], dtype=float),
    "Yd5":  _INV_SQRT3 * np.array([[-1, 1, 0], [0, -1, 1], [1, 0, -1]], dtype=float),
    "Dy7":  _INV_SQRT3 * np.array([[-1, 0, 1], [1, -1, 0], [0, 1, -1]], dtype=float),
    "Yd7":  _INV_SQRT3 * np.array([[-1, 0, 1], [1, -1, 0], [0, 1, -1]], dtype=float),
}

FAMILY_DEFAULT_GROUP = {
    "DD": "Dd0",
    "DY": "Dy11",
    "YD": "Yd11",
    "YY": "Yy0",
}

FAMILY_SCORING_CANDIDATES = {
    "DD": ["Dd0"],
    "DY": ["Dy1", "Dy11"],
    "YD": ["Yd1", "Yd11"],
    "YY": ["Yy0", "YNyn0"],
}


def get_compensation_matrix(vector_group: str) -> np.ndarray:
    """Get the compensation matrix. Falls back to identity."""
    vg = vector_group.strip()
    candidates = [vg]
    try:
        candidates.append(normalize_vector_group(vg))
    except ValueError:
        pass

    for candidate in candidates:
        matrix = COMPENSATION_MATRICES.get(candidate)
        if matrix is not None:
            return matrix.copy()

    for candidate in candidates:
        for key, mat in COMPENSATION_MATRICES.items():
            if key.lower() == candidate.lower():
                return mat.copy()

    logger.warning(f"Unknown vector group '{vg}', using identity matrix")
    return np.eye(3)


def build_current_phasors(reading: MeterReading, rated_current: float) -> np.ndarray:
    """Convert RMS current magnitudes and angles into per-unit phasors."""
    if rated_current < 1e-9:
        return np.zeros(3, dtype=complex)

    magnitudes = np.array([
        reading.current_a / rated_current,
        reading.current_b / rated_current,
        reading.current_c / rated_current,
    ], dtype=float)
    angles_deg = np.array([
        reading.angle_i1,
        reading.angle_i2,
        reading.angle_i3,
    ], dtype=float)
    return magnitudes * np.exp(1j * np.radians(angles_deg))


def infer_winding_from_voltage(reading: MeterReading) -> dict:
    """Infer D or Y from live voltage behavior.

    PM2200 reports line-neutral values only when the side is effectively wired/measured as wye.
    """
    ll = max(
        float(reading.voltage_ll_avg),
        float(reading.voltage_ab),
        float(reading.voltage_bc),
        float(reading.voltage_ca),
        0.0,
    )
    ln_values = [
        max(float(reading.voltage_an), 0.0),
        max(float(reading.voltage_bn), 0.0),
        max(float(reading.voltage_cn), 0.0),
    ]
    ln_avg = max(float(reading.voltage_ln_avg), sum(ln_values) / 3.0)
    ln_threshold = max(5.0, ll * 0.2)
    ln_present_count = sum(1 for value in ln_values if value >= ln_threshold)
    ln_present = ln_present_count >= 2 or ln_avg >= ln_threshold
    winding = "Y" if ln_present else "D"
    confidence = 95.0 if ln_present else 90.0
    return {
        "detected": ll >= 5.0,
        "winding": winding,
        "line_line_avg": ll,
        "line_neutral_avg": ln_avg,
        "ln_present": ln_present,
        "ln_present_count": ln_present_count,
        "confidence_pct": confidence,
    }


# ─────────────────────────────────────────────
# System Operating Phases
# ─────────────────────────────────────────────
class SystemPhase(str, Enum):
    IDLE = "IDLE"                         # Meters not connected
    DETECTING = "DETECTING"               # Running vector group detection
    DETECTED = "DETECTED"                 # Detection complete, ready for protection
    PROTECTING = "PROTECTING"             # Active differential protection


# ─────────────────────────────────────────────
# Detection Result
# ─────────────────────────────────────────────
@dataclass
class DetectionResult:
    detected: bool = False
    method: str = ""
    vector_group: str = ""
    tap_position: int = 1
    confidence_pct: float = 0.0
    details: dict = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "method": self.method,
            "vector_group": self.vector_group,
            "tap_position": self.tap_position,
            "confidence_pct": round(self.confidence_pct, 1),
            "details": self.details,
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────
# Phase Status & Relay Status
# ─────────────────────────────────────────────
@dataclass
class PhaseStatus:
    i_diff: float = 0.0
    i_bias: float = 0.0
    tripped: bool = False
    threshold: float = 0.0


@dataclass
class RelayStatus:
    # System phase (pipeline stage)
    system_phase: str = "IDLE"

    # Relay status
    status: str = "NORMAL"  # "NORMAL" or "TRIP"
    phases: List[PhaseStatus] = field(default_factory=lambda: [
        PhaseStatus(), PhaseStatus(), PhaseStatus()
    ])

    # Current config (from detection or manual)
    vector_group: str = ""
    vector_family: str = "UNKNOWN"
    compensation_group: str = "UNKNOWN"
    tap_position: int = 1

    # Trip tracking
    trip_time: Optional[float] = None
    reset_time: Optional[float] = None
    trip_count: int = 0
    last_trip_phases: List[str] = field(default_factory=list)

    # Per-unit currents (used internally for protection)
    i_hv_pu: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_lv_pu: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_lv_comp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Ampere values (for display)
    i_hv_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_lv_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_hv_ref_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_lv_ref_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_diff_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    i_bias_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    threshold_amp: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    inrush_block_active: bool = False
    inrush_block_remaining_ms: int = 0

    # Detection result
    detection: Optional[dict] = None
    signature_validation: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "system_phase": self.system_phase,
            "status": self.status,
            "i_diff": [round(p.i_diff, 4) for p in self.phases],
            "i_bias": [round(p.i_bias, 4) for p in self.phases],
            "trip_phases": [p.tripped for p in self.phases],
            "thresholds": [round(p.threshold, 4) for p in self.phases],
            "vector_group": self.vector_group,
            "vector_family": self.vector_family,
            "compensation_group": self.compensation_group,
            "tap_position": self.tap_position,
            "trip_time": self.trip_time,
            "reset_time": self.reset_time,
            "trip_count": self.trip_count,
            "last_trip_phases": self.last_trip_phases,
            "i_hv_pu": [round(v, 4) for v in self.i_hv_pu],
            "i_lv_pu": [round(v, 4) for v in self.i_lv_pu],
            "i_lv_comp": [round(v, 4) for v in self.i_lv_comp],
            # Ampere values for display
            "i_hv_amp": [round(v, 2) for v in self.i_hv_amp],
            "i_lv_amp": [round(v, 2) for v in self.i_lv_amp],
            "i_hv_ref_amp": [round(v, 2) for v in self.i_hv_ref_amp],
            "i_lv_ref_amp": [round(v, 2) for v in self.i_lv_ref_amp],
            "i_diff_amp": [round(v, 2) for v in self.i_diff_amp],
            "i_bias_amp": [round(v, 2) for v in self.i_bias_amp],
            "threshold_amp": [round(v, 2) for v in self.threshold_amp],
            "inrush_block_active": self.inrush_block_active,
            "inrush_block_remaining_ms": self.inrush_block_remaining_ms,
            "detection": self.detection,
            "signature_validation": self.signature_validation,
        }


class RelayService:
    """
    Transformer differential relay protection — Pipeline:
      1. IDLE → waiting for meters
      2. DETECTING → auto-detect vector group from voltages
      3. DETECTED → apply detected settings
      4. PROTECTING → continuous differential protection
    """

    def __init__(self):
        self.relay_status = RelayStatus()
        self._trip_start_time: Optional[float] = None
        self._clear_start_time: Optional[float] = None
        self._detection_result = DetectionResult()
        self._detection_attempts = 0
        self._max_detection_attempts = 10  # Try detection N times before using default
        self._energized_since: Optional[float] = None
        self._voltage_present_last: bool = False

    def _refresh_display_thresholds(self):
        """Expose the configured trip threshold even when the relay is idle."""
        threshold_amp = float(app_config.relay.i_pickup)
        for idx, phase in enumerate(self.relay_status.phases):
            phase.threshold = threshold_amp
            self.relay_status.threshold_amp[idx] = threshold_amp

    def _known_family(self) -> str:
        family = (self.relay_status.vector_family or "").upper()
        return family if family in {"DD", "DY", "YD", "YY"} else "UNKNOWN"

    def _voltage_present(self, hv: MeterReading, lv: MeterReading) -> bool:
        hv_ll = max(float(hv.voltage_ll_avg), float(hv.voltage_ab), float(hv.voltage_bc), float(hv.voltage_ca), 0.0)
        lv_ll = max(float(lv.voltage_ll_avg), float(lv.voltage_ab), float(lv.voltage_bc), float(lv.voltage_ca), 0.0)
        return hv_ll >= 20.0 and lv_ll >= 20.0

    def _line_voltage_avg(self, reading: MeterReading) -> float:
        return max(
            float(reading.voltage_ll_avg),
            float(reading.voltage_ab),
            float(reading.voltage_bc),
            float(reading.voltage_ca),
            0.0,
        )

    def _active_turns_ratio(self, hv: MeterReading, lv: MeterReading) -> float:
        tx = app_config.transformer
        if tx.equipment_mode == "autotransformer":
            return max(float(tx.autotransformer_turns_ratio), 0.001)

        hv_ll = self._line_voltage_avg(hv)
        lv_ll = self._line_voltage_avg(lv)
        if hv_ll >= 1.0 and lv_ll >= 1.0:
            return max(hv_ll / lv_ll, 0.001)

        return max(float(tx.turns_ratio), 0.001)

    def _detect_connection_family(self, hv: MeterReading, lv: MeterReading) -> dict:
        hv_side = infer_winding_from_voltage(hv)
        lv_side = infer_winding_from_voltage(lv)
        if not hv_side["detected"] or not lv_side["detected"]:
            return {
                "detected": False,
                "method": "auto_family_voltage",
                "reason": "Insufficient voltage to classify family",
                "hv": hv_side,
                "lv": lv_side,
            }

        family = f"{hv_side['winding']}{lv_side['winding']}"
        confidence = min(hv_side["confidence_pct"], lv_side["confidence_pct"])
        return {
            "detected": True,
            "method": "auto_family_voltage",
            "family": family,
            "vector_family": family,
            "hv": hv_side,
            "lv": lv_side,
            "confidence_pct": confidence,
        }

    def _score_vector_group_candidate(
        self, hv: MeterReading, lv: MeterReading, candidate: str
    ) -> float:
        tx = app_config.transformer
        i_hv = build_current_phasors(hv, tx.i_rated_hv_secondary)
        i_lv = build_current_phasors(lv, tx.i_rated_lv_secondary)
        i_lv_comp = get_compensation_matrix(candidate) @ i_lv
        return float(np.sum(np.abs(i_hv - i_lv_comp)))

    def _select_compensation_group(
        self, hv: MeterReading, lv: MeterReading, family: str
    ) -> dict:
        tx = app_config.transformer
        current_group = tx.vector_group
        current_family = vector_group_family(current_group)

        if family in ("DD", "YY"):
            if current_family == family:
                selected = current_group
            else:
                selected = FAMILY_DEFAULT_GROUP[family]
            return {
                "vector_group": selected,
                "family": family,
                "scores": {selected: 0.0},
                "reason": "family_default",
            }

        i_hv = build_current_phasors(hv, tx.i_rated_hv_secondary)
        i_lv = build_current_phasors(lv, tx.i_rated_lv_secondary)
        load_strength = max(float(np.mean(np.abs(i_hv))), float(np.mean(np.abs(i_lv))))

        candidates = FAMILY_SCORING_CANDIDATES[family]
        if load_strength < 0.05:
            if current_family == family and current_group in candidates:
                selected = current_group
            else:
                selected = FAMILY_DEFAULT_GROUP[family]
            return {
                "vector_group": selected,
                "family": family,
                "scores": {candidate: 0.0 for candidate in candidates},
                "reason": "low_current_default",
            }

        scores = {
            candidate: self._score_vector_group_candidate(hv, lv, candidate)
            for candidate in candidates
        }
        selected = min(scores, key=scores.get)
        return {
            "vector_group": selected,
            "family": family,
            "scores": scores,
            "reason": "minimum_idiff_score",
        }

    def _resolve_active_group(self, hv: MeterReading, lv: MeterReading) -> dict:
        detection_mode = (app_config.transformer.detection_mode or "auto_family").lower()
        tx = app_config.transformer

        if detection_mode == "manual_confirmed":
            family = vector_group_family(tx.vector_group)
            return {
                "detected": True,
                "method": "manual_confirmed",
                "family": family,
                "vector_family": family,
                "vector_group": tx.vector_group,
                "tap_position": tx.tap_position,
                "confidence_pct": 100.0,
                "details": {
                    "reason": "manual vector group selected",
                    "vector_group": tx.vector_group,
                    "family": family,
                },
            }

        if detection_mode == "auto_family":
            family_result = self._detect_connection_family(hv, lv)
            if not family_result["detected"]:
                fallback_family = self._known_family()
                return {
                    "detected": False,
                    "method": "auto_family_voltage",
                    "family": fallback_family,
                    "vector_family": fallback_family,
                    "vector_group": FAMILY_DEFAULT_GROUP.get(fallback_family, ""),
                    "compensation_group": fallback_family,
                    "tap_position": tx.tap_position,
                    "confidence_pct": 0.0,
                    "details": family_result,
                }

            return {
                "detected": True,
                "method": "auto_family_voltage",
                "family": family_result["family"],
                "vector_family": family_result["family"],
                "vector_group": FAMILY_DEFAULT_GROUP.get(
                    family_result["family"],
                    tx.vector_group,
                ),
                "compensation_group": family_result["family"],
                "tap_position": tx.tap_position,
                "confidence_pct": family_result["confidence_pct"],
                "details": family_result,
            }

        from services.detector import (
            detect_vector_group,
            detect_vector_group_shared_vref,
        )

        if detection_mode == "shared_vref":
            result = detect_vector_group_shared_vref(hv, lv)
        else:
            result = detect_vector_group(hv, lv)

        if not result.get("detected"):
            fallback_family = self._known_family()
            return {
                "detected": False,
                "method": result.get("method", detection_mode),
                "family": fallback_family,
                "vector_family": fallback_family,
                "vector_group": tx.vector_group if fallback_family != "UNKNOWN" else "",
                "tap_position": tx.tap_position,
                "confidence_pct": 0.0,
                "details": result,
            }

        selected_group = result["vector_group"]
        family = vector_group_family(selected_group)
        confidence = 100.0
        if result.get("method") == "shared_vref_current_angle":
            confidence = max(0.0, 100.0 - result.get("max_deviation_deg", 30.0) * 4.0)
        else:
            confidence = max(0.0, 100.0 - result.get("voltage_error_pct", 100.0) * 10.0)

        return {
            "detected": True,
            "method": result.get("method", detection_mode),
            "family": family,
            "vector_family": family,
            "vector_group": selected_group,
            "tap_position": result.get("tap_position", tx.tap_position),
            "confidence_pct": confidence,
            "details": result,
        }

    def process(self, hv: MeterReading, lv: MeterReading):
        """
        Main processing cycle — called every poll.
        Runs the appropriate phase of the pipeline.
        """
        self._refresh_display_thresholds()

        # ── Phase 1: Check meter connectivity ──
        if not hv.connected or not lv.connected:
            if self.relay_status.system_phase != SystemPhase.IDLE:
                logger.info("Meter(s) disconnected → returning to IDLE")
            self.relay_status.system_phase = SystemPhase.IDLE
            self.relay_status.status = "NORMAL"
            self.relay_status.signature_validation = {
                "available": False,
                "overall_consistent": False,
                "reason": "meters_disconnected",
                "hv": {"available": False, "consistent": False, "score": 0.0},
                "lv": {"available": False, "consistent": False, "score": 0.0},
            }
            # Reset trip state when meters disconnect
            self._energized_since = None
            self._voltage_present_last = False
            self.relay_status.inrush_block_active = False
            self.relay_status.inrush_block_remaining_ms = 0
            for p in self.relay_status.phases:
                p.tripped = False
            return

        phase = self.relay_status.system_phase

        if phase == SystemPhase.IDLE:
            # Both meters just connected → start detection
            if hv.connected and lv.connected:
                self.relay_status.system_phase = SystemPhase.DETECTING
                self._detection_attempts = 0
                logger.info("Meters connected → starting vector group detection")
            return

        if phase == SystemPhase.DETECTING:
            self._run_detection(hv, lv)
            return

        if phase in (SystemPhase.DETECTED, SystemPhase.PROTECTING):
            self.relay_status.system_phase = SystemPhase.PROTECTING
            self._run_protection(hv, lv)
            return

    def _run_detection(self, hv: MeterReading, lv: MeterReading):
        """Phase 2: resolve the coarse family and hidden compensation profile."""
        self._detection_attempts += 1
        result = self._resolve_active_group(hv, lv)
        if result.get("detected"):
            selected_group = result["vector_group"]
            family = result["family"]
            tap = result["tap_position"]
            self._detection_result = DetectionResult(
                detected=True,
                method=result["method"],
                vector_group=selected_group,
                tap_position=tap,
                confidence_pct=result["confidence_pct"],
                details=result["details"],
                timestamp=time.time(),
            )
            app_config.transformer.vector_group = selected_group
            app_config.transformer.tap_position = tap
            app_config.update_zero_seq_filters()
            self.relay_status.detection = self._detection_result.to_dict()
            self.relay_status.vector_group = selected_group
            self.relay_status.vector_family = family
            self.relay_status.compensation_group = result.get("compensation_group", selected_group)
            self.relay_status.tap_position = tap
            self.relay_status.system_phase = SystemPhase.DETECTED
            logger.info(
                "Detection complete: family=%s compensation=%s tap=%s (confidence: %.0f%%)",
                family,
                selected_group,
                tap,
                result["confidence_pct"],
            )
            return
        if self._detection_attempts >= self._max_detection_attempts:
            logger.warning("Detection failed, using current config")
            family = self._known_family()
            self.relay_status.detection = {
                "detected": False,
                "reason": result["details"].get("reason", "Unknown"),
                "using_default": family != "UNKNOWN",
                "vector_family": family,
            }
            self.relay_status.vector_family = family
            self.relay_status.compensation_group = family
            self.relay_status.system_phase = SystemPhase.DETECTED

    def re_detect(self):
        """Trigger re-detection (e.g., after tap change or rewiring)."""
        self.relay_status.system_phase = SystemPhase.DETECTING
        self._detection_attempts = 0
        logger.info("Re-detection triggered")

    def manual_reset(self):
        """Clear the trip latch without discarding trip counters."""
        self.relay_status.status = "NORMAL"
        self.relay_status.reset_time = time.time()
        self.relay_status.last_trip_phases = []
        self._trip_start_time = None
        self._clear_start_time = None
        for phase in self.relay_status.phases:
            phase.tripped = False
        logger.info("Manual reset applied")

    def _run_ratio_based_trip_logic(
        self,
        hv: MeterReading,
        lv: MeterReading,
        relay_cfg,
        now: float,
        inrush_block_active: bool,
    ) -> None:
        hv_raw = np.array([hv.current_a, hv.current_b, hv.current_c], dtype=float)
        lv_raw = np.array([lv.current_a, lv.current_b, lv.current_c], dtype=float)
        turns_ratio = self._active_turns_ratio(hv, lv)
        hv_ref = hv_raw.copy()
        lv_ref = lv_raw / turns_ratio

        self.relay_status.i_hv_pu = [float(v) for v in hv_raw]
        self.relay_status.i_lv_pu = [float(v) for v in lv_raw]
        self.relay_status.i_lv_comp = [float(v) for v in lv_ref]
        self.relay_status.i_hv_amp = [float(v) for v in hv_raw]
        self.relay_status.i_lv_amp = [float(v) for v in lv_raw]
        self.relay_status.i_hv_ref_amp = [float(v) for v in hv_ref]
        self.relay_status.i_lv_ref_amp = [float(v) for v in lv_ref]

        if relay_cfg.filter_zero_seq_hv:
            hv_ref = hv_ref - np.mean(hv_ref)

        if relay_cfg.filter_zero_seq_lv:
            lv_ref = lv_ref - np.mean(lv_ref)

        phase_names = ["A", "B", "C"]
        any_trip = False
        tripped_phases = []

        for idx in range(3):
            i_diff = float(abs(hv_ref[idx] - lv_ref[idx]))
            i_bias = float((abs(hv_ref[idx]) + abs(lv_ref[idx])) / 2.0)
            
            if i_bias <= relay_cfg.bias_breakpoint:
                threshold = float(relay_cfg.i_pickup + (relay_cfg.slope1 * i_bias))
            else:
                threshold = float(relay_cfg.i_pickup + (relay_cfg.slope1 * relay_cfg.bias_breakpoint) + (relay_cfg.slope2 * (i_bias - relay_cfg.bias_breakpoint)))

            phase = self.relay_status.phases[idx]
            phase.i_diff = i_diff
            phase.i_bias = i_bias
            phase.threshold = threshold

            self.relay_status.i_diff_amp[idx] = i_diff
            self.relay_status.i_bias_amp[idx] = i_bias
            self.relay_status.threshold_amp[idx] = threshold

            if relay_cfg.trip_enabled and not inrush_block_active and i_diff > threshold:
                phase.tripped = True
                any_trip = True
                tripped_phases.append(phase_names[idx])
            elif relay_cfg.auto_reset or not relay_cfg.trip_enabled:
                phase.tripped = False

        if not relay_cfg.trip_enabled:
            self._trip_start_time = None
            self._clear_start_time = None
            self.relay_status.status = "NORMAL"
            self.relay_status.last_trip_phases = []
            return

        if inrush_block_active:
            self._trip_start_time = None
            self._clear_start_time = None
            self.relay_status.status = "NORMAL"
            self.relay_status.last_trip_phases = []
            for phase in self.relay_status.phases:
                phase.tripped = False
            return

        if any_trip:
            self._clear_start_time = None

            if self.relay_status.status != "TRIP":
                if self._trip_start_time is None:
                    self._trip_start_time = now

                elapsed_ms = (now - self._trip_start_time) * 1000.0
                if elapsed_ms >= relay_cfg.trip_delay_ms:
                    self.relay_status.status = "TRIP"
                    self.relay_status.trip_time = now
                    self.relay_status.trip_count += 1
                    self.relay_status.last_trip_phases = tripped_phases
                    logger.warning(f"TRIP! Phases: {tripped_phases}")
        else:
            self._trip_start_time = None

            if self.relay_status.status == "TRIP":
                if relay_cfg.auto_reset:
                    if self._clear_start_time is None:
                        self._clear_start_time = now

                    elapsed_ms = (now - self._clear_start_time) * 1000.0
                    if elapsed_ms >= relay_cfg.reset_delay_ms:
                        self.relay_status.status = "NORMAL"
                        self.relay_status.reset_time = now
                        self._clear_start_time = None
                        logger.info("Auto-reset: NORMAL")
            else:
                self.relay_status.status = "NORMAL"

    def _run_protection(self, hv: MeterReading, lv: MeterReading):
        """
        Phase 3+4: Continuous differential protection.
        Uses the vector group determined during detection.
        """
        cfg = app_config
        tx = cfg.transformer
        relay_cfg = cfg.relay
        active_group = self._resolve_active_group(hv, lv)
        if active_group.get("detected"):
            tx.vector_group = active_group["vector_group"]
            tx.tap_position = active_group["tap_position"]
            app_config.update_zero_seq_filters()
            self.relay_status.detection = {
                "detected": True,
                "method": active_group["method"],
                "vector_family": active_group["family"],
                "compensation_group": active_group.get("compensation_group", active_group["vector_group"]),
                "details": active_group["details"],
            }

        if active_group.get("detected"):
            self.relay_status.vector_group = tx.vector_group
            self.relay_status.vector_family = active_group.get("family", self._known_family())
            self.relay_status.compensation_group = active_group.get(
                "compensation_group",
                tx.vector_group,
            )
        self.relay_status.tap_position = tx.tap_position

        now = time.time()
        voltage_present = self._voltage_present(hv, lv)
        if voltage_present and not self._voltage_present_last:
            self._energized_since = now
        elif not voltage_present:
            self._energized_since = None
        self._voltage_present_last = voltage_present

        inrush_block_active = False
        inrush_remaining_ms = 0
        if relay_cfg.inrush_block_ms > 0 and self._energized_since is not None:
            elapsed_ms = (now - self._energized_since) * 1000.0
            if elapsed_ms < relay_cfg.inrush_block_ms:
                inrush_block_active = True
                inrush_remaining_ms = max(0, int(relay_cfg.inrush_block_ms - elapsed_ms))

        self.relay_status.inrush_block_active = inrush_block_active
        self.relay_status.inrush_block_remaining_ms = inrush_remaining_ms

        hv_validation = build_hidden_validation(hv)
        lv_validation = build_hidden_validation(lv)
        self.relay_status.signature_validation = {
            "available": hv_validation["available"] or lv_validation["available"],
            "overall_consistent": hv_validation["consistent"] and lv_validation["consistent"],
            "reason": "matched",
            "hv": hv_validation,
            "lv": lv_validation,
        }

        use_ratio_trip_logic = (
            tx.equipment_mode == "autotransformer"
            or (tx.equipment_mode == "transformer" and (tx.detection_mode or "auto_family").lower() == "auto_family")
        )
        if use_ratio_trip_logic:
            self._run_ratio_based_trip_logic(
                hv=hv,
                lv=lv,
                relay_cfg=relay_cfg,
                now=now,
                inrush_block_active=inrush_block_active,
            )
            return

        # ═══════════ Step 1: Per-unit conversion ═══════════
        i_rated_hv = tx.i_rated_hv_secondary
        i_rated_lv = tx.i_rated_lv_secondary

        if i_rated_hv < 0.001 or i_rated_lv < 0.001:
            logger.warning("Rated currents near zero — check config")
            return

        auto_family_only = (tx.detection_mode or "auto_family").lower() == "auto_family"
        if auto_family_only:
            i_hv = np.array([
                hv.current_a / i_rated_hv,
                hv.current_b / i_rated_hv,
                hv.current_c / i_rated_hv,
            ], dtype=float)
            i_lv = np.array([
                lv.current_a / i_rated_lv,
                lv.current_b / i_rated_lv,
                lv.current_c / i_rated_lv,
            ], dtype=float)
        else:
            i_hv = build_current_phasors(hv, i_rated_hv)
            i_lv = build_current_phasors(lv, i_rated_lv)

        self.relay_status.i_hv_pu = [float(abs(v)) for v in i_hv]
        self.relay_status.i_lv_pu = [float(abs(v)) for v in i_lv]

        # Store actual Ampere values for display
        self.relay_status.i_hv_amp = [hv.current_a, hv.current_b, hv.current_c]
        self.relay_status.i_lv_amp = [lv.current_a, lv.current_b, lv.current_c]

        # ═══════════ Step 2: Vector group compensation ═══════════
        if auto_family_only:
            i_lv_comp = i_lv.copy()
        else:
            M = get_compensation_matrix(tx.vector_group)
            i_lv_comp = M @ i_lv

        self.relay_status.i_lv_comp = [float(abs(v)) for v in i_lv_comp]

        # ═══════════ Step 3: Zero-sequence filtering ═══════════
        if relay_cfg.filter_zero_seq_hv:
            i0_hv = np.mean(i_hv)
            i_hv = i_hv - i0_hv

        if relay_cfg.filter_zero_seq_lv:
            i0_lv = np.mean(i_lv_comp)
            i_lv_comp = i_lv_comp - i0_lv

        # ═══════════ Step 4: Differential only ═══════════
        self.relay_status.i_hv_ref_amp = [float(abs(v)) * i_rated_hv for v in i_hv]
        self.relay_status.i_lv_ref_amp = [float(abs(v)) * i_rated_hv for v in i_lv_comp]

        phase_names = ["A", "B", "C"]
        any_trip = False
        tripped_phases = []

        for idx in range(3):
            # The two meters report line current in the same physical flow
            # direction, so the compensated LV current must oppose the HV side
            # under normal load.
            i_diff = abs(i_hv[idx] - i_lv_comp[idx])
            i_bias = (abs(i_hv[idx]) + abs(i_lv_comp[idx])) / 2.0
            
            if i_bias <= relay_cfg.bias_breakpoint:
                threshold = relay_cfg.i_pickup + (relay_cfg.slope1 * i_bias)
            else:
                threshold = relay_cfg.i_pickup + (relay_cfg.slope1 * relay_cfg.bias_breakpoint) + (relay_cfg.slope2 * (i_bias - relay_cfg.bias_breakpoint))

            phase = self.relay_status.phases[idx]
            phase.i_diff = float(i_diff)
            phase.i_bias = float(i_bias)
            phase.threshold = float(threshold)

            # Store HV-referred Ampere values for display.
            self.relay_status.i_diff_amp[idx] = float(i_diff) * i_rated_hv
            self.relay_status.i_bias_amp[idx] = float(i_bias) * i_rated_hv
            self.relay_status.threshold_amp[idx] = float(threshold) * i_rated_hv

            if relay_cfg.trip_enabled and not inrush_block_active and i_diff > threshold:
                phase.tripped = True
                any_trip = True
                tripped_phases.append(phase_names[idx])
            elif relay_cfg.auto_reset or not relay_cfg.trip_enabled:
                phase.tripped = False

        # ═══════════ Step 5: Trip / Auto-Reset ═══════════

        if not relay_cfg.trip_enabled:
            self._trip_start_time = None
            self._clear_start_time = None
            self.relay_status.status = "NORMAL"
            self.relay_status.last_trip_phases = []
            return

        if inrush_block_active:
            self._trip_start_time = None
            self._clear_start_time = None
            self.relay_status.status = "NORMAL"
            self.relay_status.last_trip_phases = []
            for phase in self.relay_status.phases:
                phase.tripped = False
            return

        if any_trip:
            self._clear_start_time = None

            if self.relay_status.status != "TRIP":
                if self._trip_start_time is None:
                    self._trip_start_time = now

                elapsed_ms = (now - self._trip_start_time) * 1000.0
                if elapsed_ms >= relay_cfg.trip_delay_ms:
                    self.relay_status.status = "TRIP"
                    self.relay_status.trip_time = now
                    self.relay_status.trip_count += 1
                    self.relay_status.last_trip_phases = tripped_phases
                    logger.warning(f"TRIP! Phases: {tripped_phases}")
        else:
            self._trip_start_time = None

            if self.relay_status.status == "TRIP":
                if relay_cfg.auto_reset:
                    if self._clear_start_time is None:
                        self._clear_start_time = now

                    elapsed_ms = (now - self._clear_start_time) * 1000.0
                    if elapsed_ms >= relay_cfg.reset_delay_ms:
                        self.relay_status.status = "NORMAL"
                        self.relay_status.reset_time = now
                        self._clear_start_time = None
                        logger.info("Auto-reset: NORMAL")
            else:
                self.relay_status.status = "NORMAL"

    def get_bias_characteristic(self) -> dict:
        """Return the displayed Idiff pickup curve for plotting."""
        cfg = app_config.relay
        tx = app_config.transformer
        i_rated_hv = tx.i_rated_hv_secondary
        
        # Characteristic curve points (Bias vs Diff)
        # We sample Bias from 0 to a reasonable max (e.g. 10 * i_rated_hv)
        max_bias = max(10.0, cfg.i_pickup * 10, cfg.bias_breakpoint * 4)
        points_amp = []
        
        for i_bias in np.linspace(0, max_bias, 100):
            if i_bias <= cfg.bias_breakpoint:
                threshold = cfg.i_pickup + (cfg.slope1 * i_bias)
            else:
                threshold = cfg.i_pickup + (cfg.slope1 * cfg.bias_breakpoint) + (cfg.slope2 * (i_bias - cfg.bias_breakpoint))
            
            points_amp.append({
                "bias": round(i_bias * i_rated_hv, 3),
                "threshold": round(threshold * i_rated_hv, 3)
            })
            
        return {
            "curve": points_amp,
            "params": {
                "i_pickup": round(cfg.i_pickup * i_rated_hv, 3),
                "slope1": cfg.slope1,
                "slope2": cfg.slope2,
                "bias_breakpoint": round(cfg.bias_breakpoint * i_rated_hv, 3),
            },
            "i_rated_hv": i_rated_hv
        }


# Singleton
relay_service = RelayService()

