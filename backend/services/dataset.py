"""Utilities for building relay-oriented summaries from Hioki waveform CSV files."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


VOLTAGE_CHANNELS = ("U1", "U2", "U3", "U4")
CURRENT_CHANNELS = ("I1", "I2", "I3", "I4")
ALL_CHANNELS = VOLTAGE_CHANNELS + CURRENT_CHANNELS


def wrap_angle_deg(angle_deg: float) -> float:
    """Wrap an angle into [-180, 180)."""
    return ((angle_deg + 180.0) % 360.0) - 180.0


def parse_case_metadata(file_name: str) -> dict:
    """Split names like 2.3.1_1200W.csv into structured case metadata."""
    stem = Path(file_name).stem
    case_id, _, label = stem.partition("_")
    parts = case_id.split(".")
    section = ".".join(parts[:2]) if len(parts) >= 2 else case_id
    step = parts[2] if len(parts) >= 3 else ""
    return {
        "case_id": case_id,
        "section": section,
        "step": step,
        "label": label or stem,
    }


def load_waveform_csv(csv_path: Path) -> dict[str, np.ndarray]:
    """Load a Hioki waveform export into numeric numpy arrays."""
    columns = {name: [] for name in ALL_CHANNELS}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for name in ALL_CHANNELS:
                columns[name].append(float(row[name]))
    return {name: np.asarray(values, dtype=float) for name, values in columns.items()}


def summarize_channel(samples: np.ndarray) -> dict:
    """Compute scalar stats for one waveform channel."""
    if samples.size == 0:
        return {
            "mean": 0.0,
            "rms": 0.0,
            "min": 0.0,
            "max": 0.0,
            "peak": 0.0,
        }
    return {
        "mean": round(float(np.mean(samples)), 6),
        "rms": round(float(math.sqrt(np.mean(samples**2))), 6),
        "min": round(float(np.min(samples)), 6),
        "max": round(float(np.max(samples)), 6),
        "peak": round(float(np.max(np.abs(samples))), 6),
    }


def estimate_fundamental_phasors(channel_map: dict[str, np.ndarray]) -> tuple[int, dict[str, complex]]:
    """Estimate per-channel phasors from the dominant non-DC spectral bin."""
    spectral_targets = []
    for name in CURRENT_CHANNELS[:3]:
        demeaned = channel_map[name] - np.mean(channel_map[name])
        spectral_targets.append(np.fft.rfft(demeaned))

    energy = np.zeros_like(np.abs(spectral_targets[0]))
    for spectrum in spectral_targets:
        energy += np.abs(spectrum)

    if energy.size <= 1 or np.allclose(energy[1:], 0.0):
        return 0, {name: 0j for name in CURRENT_CHANNELS}

    dominant_bin = int(np.argmax(energy[1:]) + 1)
    sample_count = len(channel_map[CURRENT_CHANNELS[0]])
    phasors = {}
    for name in CURRENT_CHANNELS:
        demeaned = channel_map[name] - np.mean(channel_map[name])
        coefficient = np.fft.rfft(demeaned)[dominant_bin]
        phasors[name] = 2.0 * coefficient / sample_count / math.sqrt(2.0)
    return dominant_bin, phasors


def summarize_currents(channel_map: dict[str, np.ndarray]) -> dict:
    """Build relay-oriented metrics from I1-I4 waveform data."""
    stats = {name: summarize_channel(channel_map[name]) for name in CURRENT_CHANNELS}
    dominant_bin, phasors = estimate_fundamental_phasors(channel_map)

    phase_channels = CURRENT_CHANNELS[:3]
    phase_rms = [stats[name]["rms"] for name in phase_channels]
    mean_phase_rms = float(np.mean(phase_rms)) if phase_rms else 0.0
    max_dev = max(abs(value - mean_phase_rms) for value in phase_rms) if phase_rms else 0.0
    balance_pct = 0.0 if mean_phase_rms == 0 else 100.0 * max_dev / mean_phase_rms

    zero_seq = np.mean([channel_map["I1"], channel_map["I2"], channel_map["I3"]], axis=0)
    zero_seq_rms = float(math.sqrt(np.mean(zero_seq**2))) if zero_seq.size else 0.0

    phasor_info = {}
    for name, phasor in phasors.items():
        phasor_info[name] = {
            "fundamental_rms": round(float(abs(phasor)), 6),
            "fundamental_phase_deg": round(float(wrap_angle_deg(math.degrees(np.angle(phasor)))), 6),
        }

    if dominant_bin == 0:
        phase_diffs = {"I1_to_I2": 0.0, "I2_to_I3": 0.0, "I1_to_I3": 0.0}
    else:
        phase_diffs = {
            "I1_to_I2": round(
                wrap_angle_deg(
                    phasor_info["I2"]["fundamental_phase_deg"]
                    - phasor_info["I1"]["fundamental_phase_deg"]
                ),
                6,
            ),
            "I2_to_I3": round(
                wrap_angle_deg(
                    phasor_info["I3"]["fundamental_phase_deg"]
                    - phasor_info["I2"]["fundamental_phase_deg"]
                ),
                6,
            ),
            "I1_to_I3": round(
                wrap_angle_deg(
                    phasor_info["I3"]["fundamental_phase_deg"]
                    - phasor_info["I1"]["fundamental_phase_deg"]
                ),
                6,
            ),
        }

    return {
        "channels": {name: {**stats[name], **phasor_info[name]} for name in CURRENT_CHANNELS},
        "dominant_bin": dominant_bin,
        "samples_per_cycle_estimate": (
            round(len(channel_map["I1"]) / dominant_bin, 3) if dominant_bin else None
        ),
        "phase_balance_pct": round(balance_pct, 6),
        "phase_mean_rms": round(mean_phase_rms, 6),
        "neutral_rms": stats["I4"]["rms"],
        "zero_seq_rms": round(zero_seq_rms, 6),
        "phase_differences_deg": phase_diffs,
    }


def summarize_voltages(channel_map: dict[str, np.ndarray]) -> dict:
    """Summarize voltage channels with scalar stats only."""
    return {name: summarize_channel(channel_map[name]) for name in VOLTAGE_CHANNELS}


def summarize_waveform_file(csv_path: Path, dataset_root: Path) -> dict:
    """Create a normalized summary for one waveform CSV."""
    waveform = load_waveform_csv(csv_path)
    relative_path = csv_path.relative_to(dataset_root)
    metadata = parse_case_metadata(csv_path.name)
    return {
        "group_name": relative_path.parts[0] if relative_path.parts else "",
        "relative_path": relative_path.as_posix(),
        "recording_folder": csv_path.parent.name,
        "rows": int(len(waveform["I1"])),
        **metadata,
        "currents": summarize_currents(waveform),
        "voltages": summarize_voltages(waveform),
    }


def summarize_dataset(dataset_root: Path | str) -> dict:
    """Summarize every Hioki CSV inside a dataset root."""
    root = Path(dataset_root)
    csv_files = sorted(root.rglob("*.csv"))
    cases = [summarize_waveform_file(path, root) for path in csv_files]
    groups = Counter(case["group_name"] for case in cases)
    sections = Counter(case["section"] for case in cases)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root_name": root.name,
        "file_count": len(cases),
        "group_count": len(groups),
        "groups": dict(sorted(groups.items())),
        "sections": dict(sorted(sections.items())),
        "cases": cases,
    }


def save_dataset_summary(summary: dict, output_path: Path | str) -> Path:
    """Write a dataset summary JSON to disk."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def load_dataset_summary(summary_path: Path | str) -> dict:
    """Load a previously generated dataset summary JSON."""
    return json.loads(Path(summary_path).read_text(encoding="utf-8"))


def iter_case_paths(dataset_root: Path | str) -> Iterable[Path]:
    """Yield CSV files inside a dataset root."""
    return sorted(Path(dataset_root).rglob("*.csv"))
