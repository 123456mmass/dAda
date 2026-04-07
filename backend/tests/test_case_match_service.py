import math
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from services.case_match_service import (
    build_baseline_signature,
    build_hidden_validation,
    build_meter_signature,
    get_baseline_overview,
    match_meter_to_baseline,
    match_signature_to_baseline,
)
from services.modbus_service import MeterReading, modbus_service


def make_reading(
    current_a: float,
    current_b: float,
    current_c: float,
    current_n: float = 0.0,
    angle_i1: float = 0.0,
    angle_i2: float = -120.0,
    angle_i3: float = 120.0,
) -> MeterReading:
    return MeterReading(
        connected=True,
        current_a=current_a,
        current_b=current_b,
        current_c=current_c,
        current_n=current_n,
        current_avg=(abs(current_a) + abs(current_b) + abs(current_c)) / 3.0,
        angle_i1=angle_i1,
        angle_i2=angle_i2,
        angle_i3=angle_i3,
    )


def test_match_signature_prefers_closest_synthetic_case(monkeypatch):
    baseline = {
        "source_root_name": "ABCD",
        "file_count": 2,
        "group_count": 1,
        "sections": {"2.3": 2},
        "groups": {"Group A": 2},
        "cases": [
            {
                "case_id": "2.3.1",
                "section": "2.3",
                "step": "1",
                "label": "balanced",
                "group_name": "Group A",
                "relative_path": "Group A/2.3.1_balanced.csv",
                "currents": {
                    "phase_mean_rms": 10.0,
                    "phase_balance_pct": 0.0,
                    "zero_seq_rms": 0.0,
                    "neutral_rms": 0.0,
                    "phase_differences_deg": {
                        "I1_to_I2": -120.0,
                        "I2_to_I3": -120.0,
                        "I1_to_I3": 120.0,
                    },
                    "channels": {
                        "I1": {"fundamental_rms": 10.0},
                        "I2": {"fundamental_rms": 10.0},
                        "I3": {"fundamental_rms": 10.0},
                        "I4": {"fundamental_rms": 0.0},
                    },
                },
            },
            {
                "case_id": "2.3.2",
                "section": "2.3",
                "step": "2",
                "label": "unbalanced",
                "group_name": "Group A",
                "relative_path": "Group A/2.3.2_unbalanced.csv",
                "currents": {
                    "phase_mean_rms": 12.0,
                    "phase_balance_pct": 50.0,
                    "zero_seq_rms": 3.0,
                    "neutral_rms": 4.0,
                    "phase_differences_deg": {
                        "I1_to_I2": -80.0,
                        "I2_to_I3": -150.0,
                        "I1_to_I3": 130.0,
                    },
                    "channels": {
                        "I1": {"fundamental_rms": 16.0},
                        "I2": {"fundamental_rms": 10.0},
                        "I3": {"fundamental_rms": 10.0},
                        "I4": {"fundamental_rms": 4.0},
                    },
                },
            },
        ],
    }

    monkeypatch.setattr(
        "services.case_match_service.get_baseline_summary",
        lambda: baseline,
    )

    live = build_meter_signature(make_reading(10.1, 9.9, 10.0))
    matches = match_signature_to_baseline(live, top_n=2)

    assert matches[0]["case_id"] == "2.3.1"
    assert matches[0]["score"] > matches[1]["score"]


def test_committed_baseline_match_returns_ranked_cases():
    result = match_meter_to_baseline(make_reading(10.0, 10.0, 10.0), top_n=3)

    assert result["baseline"]["file_count"] >= 100
    assert len(result["matches"]) == 3
    assert result["matches"][0]["score"] >= result["matches"][1]["score"]
    assert "phase_balance_pct" in result["signature"]


def test_hidden_validation_hides_case_names_and_returns_consistency():
    validation = build_hidden_validation(make_reading(10.0, 10.0, 10.0))

    assert validation["available"] is True
    assert "score" in validation
    assert "consistent" in validation
    assert "case_id" not in validation
    assert "label" not in validation


def test_lab_baseline_endpoint_returns_overview_and_matches():
    modbus_service.hv_reading = make_reading(
        12.0,
        11.5,
        12.5,
        current_n=0.5,
        angle_i1=0.0,
        angle_i2=-120.0,
        angle_i3=120.0,
    )

    client = TestClient(main.app)
    overview = client.get("/api/relay/lab-baseline")
    match_response = client.get("/api/relay/lab-baseline/match", params={"source": "hv", "top_n": 2})

    assert overview.status_code == 200
    assert overview.json()["file_count"] >= 100

    assert match_response.status_code == 200
    payload = match_response.json()
    assert payload["success"] is True
    assert payload["source"] == "hv"
    assert len(payload["matches"]) == 2
