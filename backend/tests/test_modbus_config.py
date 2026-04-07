import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from config import ModbusConfig, app_config
from services.modbus_service import modbus_service


def reset_modbus_state() -> None:
    app_config.modbus = ModbusConfig()
    modbus_service._simulation = False
    modbus_service._connected = False
    modbus_service._running = False
    modbus_service._poll_task = None
    modbus_service._hv_client = None
    modbus_service._lv_client = None
    modbus_service._hv_port = None
    modbus_service._lv_port = None
    modbus_service._consecutive_errors = {"hv": 0, "lv": 0}
    modbus_service._last_reconnect_attempt = {"hv": 0.0, "lv": 0.0}


class DummyClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_current_port_summarizes_dual_port_mode():
    reset_modbus_state()
    modbus_service._hv_port = "COM4"
    modbus_service._lv_port = "COM10"

    assert modbus_service.current_port == "HV: COM4 | LV: COM10"
    assert modbus_service.current_ports == {"hv": "COM4", "lv": "COM10"}


def test_current_port_collapses_same_port_mode():
    reset_modbus_state()
    modbus_service._hv_port = "COM4"
    modbus_service._lv_port = "COM4"

    assert modbus_service.current_port == "COM4"
    assert modbus_service.current_ports == {"hv": "COM4", "lv": "COM4"}


def test_modbus_config_endpoint_exposes_dual_port_fields():
    reset_modbus_state()
    client = TestClient(main.app)

    response = client.put(
        "/api/modbus/config",
        json={
            "hv_port": "COM4",
            "lv_port": "COM10",
            "hv_meter_address": 1,
            "lv_meter_address": 1,
            "parity": "E",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["modbus"]["hv_port"] == "COM4"
    assert payload["modbus"]["lv_port"] == "COM10"
    assert payload["modbus"]["hv_meter_address"] == 1
    assert payload["modbus"]["lv_meter_address"] == 2
    assert payload["modbus"]["parity"] == "E"


def test_mark_meter_disconnected_only_drops_failed_side_in_dual_port_mode():
    reset_modbus_state()
    hv_client = DummyClient()
    lv_client = DummyClient()
    modbus_service._hv_client = hv_client
    modbus_service._lv_client = lv_client
    modbus_service._hv_port = "COM4"
    modbus_service._lv_port = "COM10"
    modbus_service._connected = True
    modbus_service.hv_reading.connected = True
    modbus_service.lv_reading.connected = True
    modbus_service.lv_reading.timestamp = 123.0
    modbus_service.lv_reading.voltage_ab = 50.0

    modbus_service._mark_meter_disconnected("lv")

    assert modbus_service._hv_client is hv_client
    assert modbus_service._lv_client is None
    assert modbus_service._hv_port == "COM4"
    assert modbus_service._lv_port == "COM10"
    assert modbus_service.hv_reading.connected is True
    assert modbus_service.lv_reading.connected is False
    assert modbus_service.lv_reading.timestamp == 0.0
    assert modbus_service.lv_reading.voltage_ab == 0.0
    assert hv_client.closed is False
    assert lv_client.closed is True


def test_mark_meter_disconnected_drops_both_sides_for_shared_client():
    reset_modbus_state()
    shared_client = DummyClient()
    modbus_service._hv_client = shared_client
    modbus_service._lv_client = shared_client
    modbus_service._hv_port = "COM4"
    modbus_service._lv_port = "COM4"
    modbus_service._connected = True
    modbus_service.hv_reading.connected = True
    modbus_service.lv_reading.connected = True

    modbus_service._mark_meter_disconnected("lv")

    assert modbus_service._hv_client is None
    assert modbus_service._lv_client is None
    assert modbus_service.hv_reading.connected is False
    assert modbus_service.lv_reading.connected is False
    assert shared_client.closed is True
