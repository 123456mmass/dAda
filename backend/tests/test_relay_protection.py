import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from config import (
    ModbusConfig,
    RelayConfig,
    TransformerConfig,
    app_config,
    normalize_vector_group,
)
from services.modbus_service import MeterReading, modbus_service
from services.relay_service import (
    DetectionResult,
    RelayStatus,
    SystemPhase,
    build_current_phasors,
    get_compensation_matrix,
    relay_service,
)


SUPPORTED_VECTOR_GROUPS = [
    "Dd0",
    "Dd6",
    "Yy0",
    "Yy6",
    "YNyn0",
    "Dy1",
    "Dy5",
    "Dy7",
    "Dy11",
    "Yd1",
    "Yd5",
    "Yd7",
    "Yd11",
    "Dyn1",
    "Dyn11",
    "YNd1",
    "YNd11",
    "YNy0",
]

ALIAS_EXPECTATIONS = [
    ("Dyn1", "Dy1", False, True),
    ("Dyn11", "Dy11", False, True),
    ("YNd1", "Yd1", True, False),
    ("YNd11", "Yd11", True, False),
    ("YNy0", "Yy0", True, False),
    ("YNyn0", "Yy0", True, True),
]


def reset_singletons() -> None:
    app_config.transformer = TransformerConfig()
    app_config.modbus = ModbusConfig()
    app_config.relay = RelayConfig(
        trip_delay_ms=0,
        reset_delay_ms=0,
        inrush_block_ms=0,
    )
    app_config.update_zero_seq_filters()

    relay_service.relay_status = RelayStatus()
    relay_service._trip_start_time = None
    relay_service._clear_start_time = None
    relay_service._detection_result = DetectionResult()
    relay_service._detection_attempts = 0
    relay_service._energized_since = None
    relay_service._voltage_present_last = False

    modbus_service._simulation = True
    modbus_service._connected = False
    modbus_service._running = False
    modbus_service._poll_task = None
    modbus_service._hv_client = None
    modbus_service._lv_client = None
    modbus_service._hv_port = None
    modbus_service._lv_port = None
    modbus_service._consecutive_errors = {1: 0, 2: 0}
    modbus_service._fault_inject = {"active": False}
    modbus_service._reset_readings()


@pytest.fixture(autouse=True)
def clean_state():
    reset_singletons()
    yield
    reset_singletons()


def configure_vector_group(vector_group: str) -> None:
    app_config.transformer.vector_group = vector_group
    app_config.transformer.detection_mode = "manual_confirmed"
    app_config.transformer.tap_position = 1
    app_config.transformer.ct_ratio_hv = 1.0
    app_config.transformer.ct_ratio_lv = 1.0
    app_config.update_zero_seq_filters()


def build_meter(currents: np.ndarray, voltage_ll: float) -> MeterReading:
    current_a, current_b, current_c = [float(v) for v in currents]
    voltage_ln = voltage_ll / math.sqrt(3)
    reading = MeterReading(
        connected=True,
        timestamp=1.0,
        current_a=current_a,
        current_b=current_b,
        current_c=current_c,
        current_n=0.0,
        current_avg=float(np.mean(np.abs(currents))),
        voltage_ab=voltage_ll,
        voltage_bc=voltage_ll,
        voltage_ca=voltage_ll,
        voltage_ll_avg=voltage_ll,
        voltage_an=voltage_ln,
        voltage_bn=voltage_ln,
        voltage_cn=voltage_ln,
        voltage_ln_avg=voltage_ln,
        frequency=50.0,
    )
    return reading


def build_balanced_meter_pair(
    vector_group: str,
    current_scale: float = 1.0,
) -> tuple[MeterReading, MeterReading]:
    configure_vector_group(vector_group)
    matrix = get_compensation_matrix(vector_group)
    lag_angle = math.degrees(math.acos(0.95))
    hv_pu_arr = current_scale * np.array([
        np.exp(1j * math.radians(-lag_angle)),
        np.exp(1j * math.radians(-120.0 - lag_angle)),
        np.exp(1j * math.radians(120.0 - lag_angle)),
    ], dtype=complex)
    lv_pu_arr = np.linalg.pinv(matrix) @ hv_pu_arr

    tx = app_config.transformer
    hv_currents = np.abs(hv_pu_arr) * tx.i_rated_hv_secondary
    lv_currents = np.abs(lv_pu_arr) * tx.i_rated_lv_secondary

    hv = build_meter(hv_currents, tx.v_hv)
    lv = build_meter(lv_currents, tx.v_lv)
    hv.angle_i1 = math.degrees(np.angle(hv_pu_arr[0]))
    hv.angle_i2 = math.degrees(np.angle(hv_pu_arr[1]))
    hv.angle_i3 = math.degrees(np.angle(hv_pu_arr[2]))
    lv.angle_i1 = math.degrees(np.angle(lv_pu_arr[0]))
    lv.angle_i2 = math.degrees(np.angle(lv_pu_arr[1]))
    lv.angle_i3 = math.degrees(np.angle(lv_pu_arr[2]))
    return hv, lv


def trigger_trip(hv: MeterReading, lv: MeterReading) -> None:
    relay_service.relay_status.system_phase = SystemPhase.PROTECTING
    relay_service.process(hv, lv)


@pytest.mark.parametrize("vector_group", SUPPORTED_VECTOR_GROUPS)
def test_balanced_load_stays_normal_for_supported_vector_groups(vector_group: str):
    hv, lv = build_balanced_meter_pair(vector_group)

    trigger_trip(hv, lv)

    assert relay_service.relay_status.status == "NORMAL"
    assert relay_service.relay_status.last_trip_phases == []
    assert relay_service.relay_status.to_dict()["trip_phases"] == [False, False, False]
    assert max(phase.i_diff for phase in relay_service.relay_status.phases) < 1e-9


@pytest.mark.parametrize("vector_group", SUPPORTED_VECTOR_GROUPS)
def test_three_phase_internal_fault_trips_all_phases(vector_group: str):
    hv, lv = build_balanced_meter_pair(vector_group)

    lv_fault = copy.deepcopy(lv)
    lv_fault.current_a *= 3.0
    lv_fault.current_b *= 3.0
    lv_fault.current_c *= 3.0
    lv_fault.current_avg = (abs(lv_fault.current_a) + abs(lv_fault.current_b) + abs(lv_fault.current_c)) / 3.0

    trigger_trip(hv, lv_fault)

    assert relay_service.relay_status.status == "TRIP"
    assert relay_service.relay_status.last_trip_phases == ["A", "B", "C"]
    assert relay_service.relay_status.to_dict()["trip_phases"] == [True, True, True]


@pytest.mark.parametrize(
    ("raw_group", "normalized_group", "hv_filter", "lv_filter"),
    ALIAS_EXPECTATIONS,
)
def test_neutral_aliases_normalize_and_set_filters(
    raw_group: str,
    normalized_group: str,
    hv_filter: bool,
    lv_filter: bool,
):
    configure_vector_group(raw_group)

    assert normalize_vector_group(raw_group) == normalized_group
    assert app_config.relay.filter_zero_seq_hv is hv_filter
    assert app_config.relay.filter_zero_seq_lv is lv_filter
    np.testing.assert_allclose(
        get_compensation_matrix(raw_group),
        get_compensation_matrix(normalized_group),
    )


@pytest.mark.parametrize("vector_group", ["Dd0", "Dyn11", "YNd1", "YNyn0"])
def test_balanced_phasors_cancel_after_compensation(vector_group: str):
    hv, lv = build_balanced_meter_pair(vector_group)

    tx = app_config.transformer
    hv_phasors = build_current_phasors(hv, tx.i_rated_hv_secondary)
    lv_phasors = build_current_phasors(lv, tx.i_rated_lv_secondary)
    compensated = get_compensation_matrix(vector_group) @ lv_phasors

    np.testing.assert_allclose(hv_phasors, compensated, atol=1e-9)


def test_pipeline_transitions_from_idle_to_protecting():
    hv, lv = build_balanced_meter_pair("Dd0")
    app_config.transformer.detection_mode = "shared_vref"

    relay_service.process(hv, lv)
    assert relay_service.relay_status.system_phase == SystemPhase.DETECTING

    relay_service.process(hv, lv)
    assert relay_service.relay_status.system_phase == SystemPhase.DETECTED
    assert relay_service.relay_status.vector_group == "Dd0"
    assert relay_service.relay_status.tap_position == 1

    relay_service.process(hv, lv)
    assert relay_service.relay_status.system_phase == SystemPhase.PROTECTING
    assert relay_service.relay_status.status == "NORMAL"
    assert relay_service.relay_status.detection["method"] == "shared_vref_current_angle"
    assert relay_service.relay_status.signature_validation is not None
    assert "hv" in relay_service.relay_status.signature_validation
    assert "lv" in relay_service.relay_status.signature_validation


def test_manual_confirmed_pipeline_uses_selected_vector_group():
    hv, lv = build_balanced_meter_pair("Dd0")
    app_config.transformer.equipment_mode = "autotransformer"
    app_config.transformer.vector_group = "Dyn11"
    app_config.transformer.tap_position = 3
    app_config.transformer.detection_mode = "manual_confirmed"

    relay_service.process(hv, lv)
    assert relay_service.relay_status.system_phase == SystemPhase.DETECTING

    relay_service.process(hv, lv)
    assert relay_service.relay_status.system_phase == SystemPhase.DETECTED
    assert relay_service.relay_status.vector_group == "Dyn11"
    assert relay_service.relay_status.tap_position == 3
    assert relay_service.relay_status.detection["method"] == "manual_confirmed"


def test_hidden_signature_validation_is_set_when_meters_disconnect():
    relay_service.process(MeterReading(connected=False), MeterReading(connected=True))

    assert relay_service.relay_status.system_phase == SystemPhase.IDLE
    assert relay_service.relay_status.signature_validation == {
        "available": False,
        "overall_consistent": False,
        "reason": "meters_disconnected",
        "hv": {"available": False, "consistent": False, "score": 0.0},
        "lv": {"available": False, "consistent": False, "score": 0.0},
    }


def test_reset_endpoint_clears_trip_latch_after_fault():
    hv, lv = build_balanced_meter_pair("Dd0")
    lv_fault = copy.deepcopy(lv)
    lv_fault.current_a *= 3.0
    lv_fault.current_b *= 3.0
    lv_fault.current_c *= 3.0
    lv_fault.current_avg = (abs(lv_fault.current_a) + abs(lv_fault.current_b) + abs(lv_fault.current_c)) / 3.0

    trigger_trip(hv, lv_fault)
    assert relay_service.relay_status.status == "TRIP"

    client = TestClient(main.app)
    response = client.post("/api/relay/reset")

    assert response.status_code == 200
    assert response.json() == {"success": True, "status": "NORMAL"}
    assert relay_service.relay_status.status == "NORMAL"
    assert relay_service.relay_status.to_dict()["trip_phases"] == [False, False, False]


def test_transformer_config_uses_current_base_for_relay_scaling():
    client = TestClient(main.app)

    response = client.put(
        "/api/relay/config/transformer",
        json={
            "equipment_mode": "transformer",
            "kva": 7.5,
            "detection_mode": "shared_vref",
            "current_base_hv_secondary": 2.5,
            "current_base_lv_secondary": 5.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transformer"]["equipment_mode"] == "transformer"
    assert payload["transformer"]["kva"] == 7.5
    assert payload["transformer"]["detection_mode"] == "shared_vref"
    assert payload["transformer"]["current_base_hv_secondary"] == 2.5
    assert payload["transformer"]["current_base_lv_secondary"] == 5.0
    assert payload["transformer"]["i_rated_hv"] == 2.5
    assert payload["transformer"]["i_rated_lv"] == 5.0
    assert payload["transformer"]["nameplate_i_hv"] > 0.0
    assert payload["transformer"]["nameplate_i_lv"] > 0.0
    assert app_config.transformer.equipment_mode == "transformer"
    assert app_config.transformer.kva == 7.5
    assert app_config.transformer.detection_mode == "shared_vref"
    assert app_config.transformer.current_base_hv_secondary == 2.5
    assert app_config.transformer.current_base_lv_secondary == 5.0


def test_autotransformer_preset_applies_shared_vref_lab_defaults():
    client = TestClient(main.app)
    app_config.transformer.kva = 6.0

    response = client.post("/api/relay/presets/autotransformer-test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["preset"] == "autotransformer_test"
    assert payload["transformer"]["equipment_mode"] == "autotransformer"
    assert payload["transformer"]["kva"] == 6.0
    assert payload["transformer"]["detection_mode"] == "auto_family"
    assert payload["transformer"]["ct_ratio_hv"] == 1.0
    assert payload["transformer"]["ct_ratio_lv"] == 1.0
    assert payload["transformer"]["current_base_hv_secondary"] > 0.0
    assert payload["transformer"]["current_base_lv_secondary"] > 0.0
    assert payload["relay"]["trip_enabled"] is False
    assert payload["relay"]["auto_reset"] is True
    assert relay_service.relay_status.system_phase == SystemPhase.DETECTING


def test_autotransformer_detect_endpoint_returns_manual_reason():
    client = TestClient(main.app)
    app_config.transformer.equipment_mode = "autotransformer"
    app_config.transformer.detection_mode = "manual_confirmed"
    app_config.transformer.vector_group = "YNyn0"
    app_config.transformer.tap_position = 2

    response = client.post("/api/relay/detect-vector-group")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected"] is False
    assert payload["method"] == "manual_confirmed"
    assert payload["vector_group"] == "YNyn0"
    assert payload["tap_position"] == 2


def test_auto_family_detection_prefers_dy_when_hv_has_no_vln_and_lv_has_vln():
    hv = build_meter(np.array([1.0, 1.0, 1.0]), 100.0)
    hv.voltage_an = 0.0
    hv.voltage_bn = 0.0
    hv.voltage_cn = 0.0
    hv.voltage_ln_avg = 0.0

    lv = build_meter(np.array([2.0, 2.0, 2.0]), 50.0)
    app_config.transformer.detection_mode = "auto_family"
    app_config.transformer.vector_group = "Dd0"

    result = relay_service._resolve_active_group(hv, lv)

    assert result["detected"] is True
    assert result["family"] == "DY"
    assert result["vector_group"] in {"Dy1", "Dy11"}


def test_auto_family_updates_dashboard_family_during_protection():
    hv = build_meter(np.array([1.0, 1.0, 1.0]), 100.0)
    hv.voltage_an = 0.0
    hv.voltage_bn = 0.0
    hv.voltage_cn = 0.0
    hv.voltage_ln_avg = 0.0
    hv.angle_i1 = 0.0
    hv.angle_i2 = -120.0
    hv.angle_i3 = 120.0

    lv = build_meter(np.array([2.0, 2.0, 2.0]), 50.0)
    lv.angle_i1 = 0.0
    lv.angle_i2 = -120.0
    lv.angle_i3 = 120.0

    app_config.transformer.detection_mode = "auto_family"
    relay_service.relay_status.system_phase = SystemPhase.PROTECTING

    relay_service.process(hv, lv)

    assert relay_service.relay_status.vector_family == "DY"
    assert relay_service.relay_status.compensation_group == "DY"


def test_trip_disabled_keeps_monitoring_without_trip():
    hv, lv = build_balanced_meter_pair("Dd0")
    relay_service.relay_status.system_phase = SystemPhase.PROTECTING
    app_config.relay.trip_enabled = False

    lv_fault = copy.deepcopy(lv)
    lv_fault.current_a *= 3.0
    lv_fault.current_b *= 3.0
    lv_fault.current_c *= 3.0
    lv_fault.current_avg = (abs(lv_fault.current_a) + abs(lv_fault.current_b) + abs(lv_fault.current_c)) / 3.0

    relay_service.process(hv, lv_fault)

    assert relay_service.relay_status.status == "NORMAL"
    assert relay_service.relay_status.last_trip_phases == []
    assert max(relay_service.relay_status.i_diff_amp) > 0.0
