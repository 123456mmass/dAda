import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.hioki_dataset_service import (
    load_dataset_summary,
    parse_case_metadata,
    summarize_dataset,
    summarize_waveform_file,
)


def build_three_phase_csv(csv_path: Path, sample_count: int = 600) -> None:
    angle = np.linspace(0.0, 8.0 * math.pi, sample_count, endpoint=False)
    i1 = 10.0 * np.sin(angle)
    i2 = 10.0 * np.sin(angle - 2.0 * math.pi / 3.0)
    i3 = 10.0 * np.sin(angle + 2.0 * math.pi / 3.0)
    i4 = np.zeros_like(i1)
    u1 = np.sin(angle)
    u2 = np.sin(angle - 2.0 * math.pi / 3.0)
    u3 = np.sin(angle + 2.0 * math.pi / 3.0)
    u4 = np.zeros_like(u1)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["EventNo", "Date", "Time", "U1", "U2", "U3", "U4", "I1", "I2", "I3", "I4"])
        for index in range(sample_count):
            writer.writerow(
                [
                    2,
                    "05/02/2026",
                    f"17:53:12.{index:03d}",
                    f"{u1[index]:+.6E}",
                    f"{u2[index]:+.6E}",
                    f"{u3[index]:+.6E}",
                    f"{u4[index]:+.6E}",
                    f"{i1[index]:+.6E}",
                    f"{i2[index]:+.6E}",
                    f"{i3[index]:+.6E}",
                    f"{i4[index]:+.6E}",
                ]
            )


def test_parse_case_metadata_splits_section_and_label():
    metadata = parse_case_metadata("2.3.1_1200W.csv")

    assert metadata == {
        "case_id": "2.3.1",
        "section": "2.3",
        "step": "1",
        "label": "1200W",
    }


def test_summarize_waveform_file_extracts_relay_metrics(tmp_path: Path):
    dataset_root = tmp_path / "ABCD"
    csv_path = dataset_root / "Group A" / "Group A" / "2.3.1_1200W.csv"
    build_three_phase_csv(csv_path)

    summary = summarize_waveform_file(csv_path, dataset_root)

    assert summary["group_name"] == "Group A"
    assert summary["section"] == "2.3"
    assert summary["rows"] == 600
    assert summary["currents"]["dominant_bin"] > 0
    assert summary["currents"]["phase_balance_pct"] < 1e-6
    assert abs(summary["currents"]["channels"]["I1"]["rms"] - (10.0 / math.sqrt(2.0))) < 0.01
    assert abs(abs(summary["currents"]["phase_differences_deg"]["I1_to_I2"]) - 120.0) < 1.0
    assert abs(abs(summary["currents"]["phase_differences_deg"]["I2_to_I3"]) - 120.0) < 1.0


def test_summarize_dataset_rolls_up_sections_and_groups(tmp_path: Path):
    dataset_root = tmp_path / "ABCD"
    build_three_phase_csv(dataset_root / "Group A" / "Group A" / "2.2.1_15V.csv")
    build_three_phase_csv(dataset_root / "Group A" / "Group A" / "2.3.1_1200W.csv")
    build_three_phase_csv(dataset_root / "Group B" / "Group B" / "2.5.2_B.csv")

    summary = summarize_dataset(dataset_root)

    assert summary["source_root_name"] == "ABCD"
    assert summary["file_count"] == 3
    assert summary["group_count"] == 2
    assert summary["groups"] == {"Group A": 2, "Group B": 1}
    assert summary["sections"] == {"2.2": 1, "2.3": 1, "2.5": 1}


def test_committed_lab_baseline_has_expected_shape():
    summary_path = Path(__file__).resolve().parents[1] / "data" / "hioki_lab_baseline.json"
    summary = load_dataset_summary(summary_path)

    assert summary["source_root_name"] == "ABCD"
    assert summary["file_count"] >= 100
    assert summary["group_count"] >= 10
    assert set(summary["sections"]).issuperset({"2.2", "2.3", "2.4", "2.5"})
    assert len(summary["cases"]) == summary["file_count"]
    assert all(case["rows"] > 0 for case in summary["cases"])
