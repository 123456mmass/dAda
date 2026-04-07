"""
Modbus RTU Service for PM2200 Meters
=====================================
Handles communication with 2 × Schneider PM2200 via RS485.
Features:
  - Auto COM port detection (scans for meters at addr 1,2)
  - Cyclic polling with error recovery
  - Float32 Big-Endian register decoding
  - Phase angle derivation from PF
"""

import asyncio
import struct
import time
import logging
import math
from typing import Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Lazy imports for pymodbus — allows fallback to simulation
try:
    from pymodbus.client import AsyncModbusSerialClient, ModbusSerialClient
    from pymodbus.exceptions import ModbusException
    HAS_PYMODBUS = True
except ImportError:
    HAS_PYMODBUS = False
    ModbusSerialClient = None
    logger.warning("pymodbus not installed — running in simulation mode")

from config import app_config, EM96Registers


@dataclass
class MeterReading:
    """All instantaneous readings from one PM2200 meter."""
    timestamp: float = 0.0
    connected: bool = False

    # Currents (A) — values as seen by meter
    current_a: float = 0.0
    current_b: float = 0.0
    current_c: float = 0.0
    current_n: float = 0.0
    current_avg: float = 0.0

    # Line-Line Voltages (V)
    voltage_ab: float = 0.0
    voltage_bc: float = 0.0
    voltage_ca: float = 0.0
    voltage_ll_avg: float = 0.0

    # Line-Neutral Voltages (V)
    voltage_an: float = 0.0
    voltage_bn: float = 0.0
    voltage_cn: float = 0.0
    voltage_ln_avg: float = 0.0

    # Power Factor
    pf_a: float = 1.0
    pf_b: float = 1.0
    pf_c: float = 1.0
    pf_total: float = 1.0

    # Power
    p_total: float = 0.0
    q_total: float = 0.0
    s_total: float = 0.0

    # Frequency
    frequency: float = 50.0

    # Phase angles (degrees) — for waveform synthesis
    angle_v1: float = 0.0
    angle_v2: float = -120.0
    angle_v3: float = 120.0
    angle_i1: float = 0.0
    angle_i2: float = -120.0
    angle_i3: float = 120.0

    def to_dict(self) -> dict:
        return {
            "connected": self.connected,
            "timestamp": self.timestamp,
            "current": {
                "a": round(self.current_a, 4),
                "b": round(self.current_b, 4),
                "c": round(self.current_c, 4),
                "n": round(self.current_n, 4),
                "avg": round(self.current_avg, 4),
            },
            "voltage_ll": {
                "ab": round(self.voltage_ab, 2),
                "bc": round(self.voltage_bc, 2),
                "ca": round(self.voltage_ca, 2),
                "avg": round(self.voltage_ll_avg, 2),
            },
            "voltage_ln": {
                "an": round(self.voltage_an, 2),
                "bn": round(self.voltage_bn, 2),
                "cn": round(self.voltage_cn, 2),
                "avg": round(self.voltage_ln_avg, 2),
            },
            "power_factor": {
                "a": round(self.pf_a, 4),
                "b": round(self.pf_b, 4),
                "c": round(self.pf_c, 4),
                "total": round(self.pf_total, 4),
            },
            "power": {
                "p_total": round(self.p_total, 2),
                "q_total": round(self.q_total, 2),
                "s_total": round(self.s_total, 2),
            },
            "frequency": round(self.frequency, 3),
            "phase_angles": {
                "v1": round(self.angle_v1, 2),
                "v2": round(self.angle_v2, 2),
                "v3": round(self.angle_v3, 2),
                "i1": round(self.angle_i1, 2),
                "i2": round(self.angle_i2, 2),
                "i3": round(self.angle_i3, 2),
            },
        }


def _decode_float32(registers: list, index: int = 0) -> float:
    """Decode two 16-bit registers → 32-bit float (Big-Endian)."""
    try:
        high = registers[index]
        low = registers[index + 1]
        raw = struct.pack('>HH', high, low)
        value = struct.unpack('>f', raw)[0]
        if value != value or abs(value) > 1e10:  # NaN or overflow guard
            return 0.0
        return value
    except (IndexError, struct.error):
        return 0.0


async def scan_com_ports() -> List[str]:
    """Scan available COM ports on Windows."""
    import serial.tools.list_ports
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]


async def scan_candidate_com_ports() -> List[str]:
    """List only ports that look like real serial adapters, excluding Bluetooth virtual ports."""
    import serial.tools.list_ports

    candidates: List[str] = []
    for port in serial.tools.list_ports.comports():
        descriptor = " ".join(
            str(value or "")
            for value in [port.device, port.description, getattr(port, "manufacturer", "")]
        ).lower()
        if "bluetooth" in descriptor:
            continue
        candidates.append(port.device)
    return candidates


async def auto_detect_port(exclude_ports: Optional[List[str]] = None) -> Optional[str]:
    """Try each COM port and find one with PM2200 responding at addr 1 or 2."""
    if not HAS_PYMODBUS:
        return None

    ports = await scan_candidate_com_ports()
    excluded = {port.upper() for port in (exclude_ports or []) if port}
    ports = [port for port in ports if port.upper() not in excluded]
    cfg = app_config.modbus
    logger.info(f"Auto-detecting meter on ports: {ports}")

    for port in ports:
        try:
            client = AsyncModbusSerialClient(
                port=port,
                baudrate=cfg.baudrate,
                parity=cfg.parity,
                stopbits=cfg.stopbits,
                bytesize=cfg.bytesize,
                timeout=0.5,
            )
            connected = await client.connect()
            if not connected:
                continue

            # Try reading a known input register block from meter addr 1.
            # Some setups return special values for frequency, so a non-error
            # response here is a more reliable probe than validating the numeric value.
            result = await client.read_input_registers(
                address=EM96Registers.V1N,
                count=2,
                slave=cfg.hv_meter_address
            )
            client.close()

            if not result.isError():
                logger.info("Found PM2200 on %s", port)
                return port
        except Exception as e:
            logger.debug(f"Port {port} scan failed: {e}")
            continue

    logger.warning("No PM2200 found on any COM port")
    return None


def _wrap_angle_deg(angle: float) -> float:
    """Normalize an angle to the [-180, 180) range."""
    wrapped = ((angle + 180.0) % 360.0) - 180.0
    if wrapped == -180.0:
        return 180.0
    return wrapped


class ModbusService:
    """Manages Modbus RTU connection and polling for 2 PM2200 meters."""

    def __init__(self):
        self._client = None
        self._connected: bool = False
        self._running: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        self._port: Optional[str] = None
        self._last_connect_error: str = ""

        # Latest readings
        self.hv_reading = MeterReading()
        self.lv_reading = MeterReading()

        # Error tracking per meter address
        self._consecutive_errors: Dict[str, int] = {"hv": 0, "lv": 0}
        self._max_errors = 5
        self._last_reconnect_attempt: float = 0.0
        self._reconnect_interval_s = 2.0

        # Simulation mode flag
        self._simulation = not HAS_PYMODBUS
        self._fault_inject: dict = {"active": False}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def current_port(self) -> Optional[str]:
        return self._port

    @property
    def current_ports(self) -> dict:
        return {"hv": self._port, "lv": self._port}

    @property
    def last_connect_error(self) -> str:
        return self._last_connect_error

    async def _resolve_port(self, requested_port: Optional[str], exclude_ports: Optional[List[str]] = None) -> Optional[str]:
        """Resolve 'auto' to a real COM port while optionally excluding busy ports."""
        use_port = requested_port or "auto"
        if use_port != "auto":
            return use_port
        return await auto_detect_port(exclude_ports=exclude_ports)

    async def _connect_client(self, port: str):
        """Create and connect one serial client."""
        cfg = app_config.modbus
        try:
            client = AsyncModbusSerialClient(
                port=port,
                baudrate=cfg.baudrate,
                parity=cfg.parity,
                stopbits=cfg.stopbits,
                bytesize=cfg.bytesize,
                timeout=cfg.timeout,
            )
            connected = await client.connect()
            if connected:
                # Wait for serial port to stabilize
                await asyncio.sleep(0.3)
                return client
            client.close()
            self._last_connect_error = f"เปิดพอร์ต {port} ไม่สำเร็จ"
            return None
        except Exception as exc:
            self._last_connect_error = f"เปิดพอร์ต {port} ไม่ได้: {exc}"
            return None

    async def _probe_meter_with_client(self, client, address: int) -> bool:
        """Quick probe on an already-open client using a known input register block."""
        try:
            # Small delay before probing
            await asyncio.sleep(0.1)
            result = await client.read_input_registers(
                address=EM96Registers.V1N,
                count=2,
                slave=address,
            )
            return not result.isError()
        except Exception as exc:
            logger.debug("Probe failed on open client addr %s: %s", address, exc)
            return False

    async def _probe_meter_address(self, port: str, address: int) -> bool:
        """Quick probe: can this port talk to the requested fixed PM2200 address?"""
        cfg = app_config.modbus
        client = None
        try:
            # Use the sync client for auto-pair probing on Windows/CH340.
            # This matches the direct terminal checks that have been reliable.
            client = ModbusSerialClient(
                port=port,
                baudrate=cfg.baudrate,
                parity=cfg.parity,
                stopbits=cfg.stopbits,
                bytesize=cfg.bytesize,
                timeout=cfg.timeout,
            )
            if not client.connect():
                return False
            # Wait for port to stabilize
            time.sleep(0.3)
            result = client.read_input_registers(
                address=EM96Registers.V1N,
                count=2,
                slave=address,
            )
            return not result.isError()
        except Exception as exc:
            logger.debug("Probe failed on %s addr %s: %s", port, address, exc)
            return False
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
                await asyncio.sleep(0.1)

    async def _auto_pair_meter_ports(self) -> Optional[str]:
        """Auto-pair single port to both fixed meter addresses: HV=addr1, LV=addr2."""
        cfg = app_config.modbus
        ports = await scan_candidate_com_ports()
        logger.info("Auto-pairing fixed meter addresses on candidate ports: %s", ports)

        for port in ports:
            # Assume bus architecture: if it can talk to either one, it is the right bus
            if await self._probe_meter_address(port, cfg.hv_meter_address) or await self._probe_meter_address(port, cfg.lv_meter_address):
                return port

        port_list = ", ".join(ports) if ports else "ไม่มีพอร์ตที่เข้าเงื่อนไข"
        self._last_connect_error = (
            f"Auto Pair ไม่สำเร็จ: เปิดหรือ probe พอร์ตไม่ได้ ({port_list}) "
            f"ให้ลองเลือก COM เองหรือปิดโปรแกรมที่จับพอร์ตอยู่"
        )
        return None

    async def _auto_rebind_fixed_ports(self, reason: str) -> Optional[str]:
        """When saved COM ports go stale, scan live ports and bind back to addr 1 / addr 2."""
        logger.warning("Saved COM ports look stale (%s). Re-scanning candidate ports.", reason)
        port = await self._auto_pair_meter_ports()
        if port:
            app_config.modbus.port = port
            logger.info("Rebound meter port to: %s", port)
        return port

    async def connect(self, port: Optional[str] = None) -> bool:
        """Connect to Modbus RTU on a single port for both meters."""
        if self._simulation:
            self._connected = True
            self._port = "SIMULATION"
            logger.info("Running in simulation mode (no pymodbus)")
            return True

        cfg = app_config.modbus
        self._last_connect_error = ""
        requested_port = port or cfg.port

        if self._connected and self._port == requested_port and requested_port != "auto":
            logger.info("Modbus already connected on %s", self._port)
            return True

        if requested_port == "auto" and self._connected and self._port:
            logger.info("Reusing existing connected port for auto-pair: %s", self._port)
            return True

        try:
            if self._client:
                await self.disconnect()
                await asyncio.sleep(0.2)

            resolved_port = requested_port
            if requested_port == "auto":
                resolved_port = await self._auto_pair_meter_ports()
                if not resolved_port:
                    logger.error("Failed to auto-detect any meter")
                    return False

            client = await self._connect_client(resolved_port)
            if not client:
                logger.error("Failed to connect to port %s", resolved_port)
                return False

            hv_ok = await self._probe_meter_with_client(client, cfg.hv_meter_address)
            if not hv_ok:
                logger.warning("Port %s connected but HV meter (addr %s) not responding", resolved_port, cfg.hv_meter_address)
            
            lv_ok = await self._probe_meter_with_client(client, cfg.lv_meter_address)
            if not lv_ok:
                logger.warning("Port %s connected but LV meter (addr %s) not responding", resolved_port, cfg.lv_meter_address)

            if not hv_ok and not lv_ok:
                self._safe_close_client(client)
                self._last_connect_error = f"ต่อ {resolved_port} ได้ แต่มิเตอร์ไม่ตอบทั้ง 2 ตัว"
                return False

            self._client = client
            self._connected = True
            self._port = resolved_port
            self._consecutive_errors = {"hv": 0, "lv": 0}
            self._last_reconnect_attempt = 0.0
            self._reset_readings()
            logger.info("Modbus connected on %s", self._port)
            return True

        except Exception as e:
            self._last_connect_error = f"เชื่อมต่อ Modbus ไม่สำเร็จ: {e}"
            logger.error(f"Modbus connect error: {e}")
            return False

    async def disconnect(self):
        """Close connection and zero out all readings."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        self._safe_close_client(self._client)
        self._client = None
        self._connected = False
        self._port = None
        self._reset_readings()
        logger.info("Modbus disconnected")

    def _safe_close_client(self, client):
        """Best-effort close that swallows broken client-state errors."""
        if not client:
            return
        try:
            client.close()
        except Exception as exc:
            logger.debug("Ignoring client close error: %s", exc)

    def _mark_meter_disconnected(self, meter_key: str):
        self._reset_meter_reading(meter_key)

    async def _ensure_client(self):
        """Reconnect single port if client dropped."""
        if self._client or self._simulation or not self._port:
            return self._client

        now = time.time()
        if now - self._last_reconnect_attempt < self._reconnect_interval_s:
            return None

        self._last_reconnect_attempt = now
        try:
            client = await self._connect_client(self._port)
            if client:
                self._client = client
                self._consecutive_errors = {"hv": 0, "lv": 0}
                self.hv_reading.connected = False
                self.lv_reading.connected = False
                logger.info("Reconnected Modbus on %s", self._port)
                return client
        except Exception as exc:
            logger.debug("Reconnect attempt for %s failed: %s", self._port, exc)
        return None

    def _reset_readings(self):
        """Reset both meter readings to zero / not-connected."""
        self.hv_reading = MeterReading()
        self.lv_reading = MeterReading()

    def _reset_meter_reading(self, meter_key: str):
        """Reset one meter reading to zero / not-connected."""
        if meter_key == "hv":
            self.hv_reading = MeterReading()
        else:
            self.lv_reading = MeterReading()

    async def start_polling(self):
        """Start background polling loop."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Polling started")

    async def stop_polling(self):
        """Stop background polling loop."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()

    async def _poll_loop(self):
        """Main polling loop alternating HV/LV meters."""
        cfg = app_config.modbus
        interval = cfg.poll_interval_ms / 1000.0
        from services.relay import relay_service
        from services.display import esp_display_service

        while self._running:
            try:
                if not self._connected:
                    # In real mode without connection, keep readings at zero
                    if not self._simulation:
                        self.hv_reading.connected = False
                        self.lv_reading.connected = False
                    relay_service.process(self.hv_reading, self.lv_reading)
                    await esp_display_service.push_relay_status(relay_service.relay_status)
                    await asyncio.sleep(1.0)
                    continue

                if self._simulation:
                    self._generate_simulation_data()
                    relay_service.process(self.hv_reading, self.lv_reading)
                    await esp_display_service.push_relay_status(relay_service.relay_status)
                    await asyncio.sleep(interval)
                    continue

                client = await self._ensure_client()

                # Poll HV meter
                await self._read_meter(client, cfg.hv_meter_address, self.hv_reading, "hv")
                await asyncio.sleep(0.05)

                # Poll LV meter
                await self._read_meter(client, cfg.lv_meter_address, self.lv_reading, "lv")

                relay_service.process(self.hv_reading, self.lv_reading)
                await esp_display_service.push_relay_status(relay_service.relay_status)
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(1.0)

    async def _read_meter(self, client, address: int, reading: MeterReading, meter_key: str):
        """Read all registers from one PM2200."""
        if not client:
            self._reset_meter_reading(meter_key)
            return

        try:
            block_success = False

            # ── Block 1: V LN and Currents (regs 0-11 = 12 regs) ──
            result = await client.read_input_registers(
                address=EM96Registers.V1N, count=12, slave=address
            )
            if not result.isError():
                r = result.registers
                reading.voltage_an = _decode_float32(r, 0)
                reading.voltage_bn = _decode_float32(r, 2)
                reading.voltage_cn = _decode_float32(r, 4)
                reading.current_a = _decode_float32(r, 6)
                reading.current_b = _decode_float32(r, 8)
                reading.current_c = _decode_float32(r, 10)
                block_success = True
            else:
                logger.debug("Meter %s Block 1 read error: %s", address, result)

            # ── Block 2: Power, PF, Angles (regs 30-71 = 42 regs) ──
            angles_loaded = False
            result = await client.read_input_registers(
                address=EM96Registers.PF1, count=42, slave=address
            )
            if not result.isError():
                r = result.registers
                # r[0] corresponds to addr 30
                reading.pf_a = _decode_float32(r, 0)
                reading.pf_b = _decode_float32(r, 2)
                reading.pf_c = _decode_float32(r, 4)
                
                reading.angle_v1 = 0.0
                reading.angle_v2 = -120.0
                reading.angle_v3 = 120.0
                reading.angle_i1 = _wrap_angle_deg(reading.angle_v1 + _decode_float32(r, 6))
                reading.angle_i2 = _wrap_angle_deg(reading.angle_v2 + _decode_float32(r, 8))
                reading.angle_i3 = _wrap_angle_deg(reading.angle_v3 + _decode_float32(r, 10))
                angles_loaded = True
                
                reading.voltage_ln_avg = _decode_float32(r, 12)
                reading.current_avg = _decode_float32(r, 16)
                reading.p_total = _decode_float32(r, 22)
                reading.s_total = _decode_float32(r, 26)
                reading.q_total = _decode_float32(r, 30)
                reading.pf_total = _decode_float32(r, 32)
                reading.frequency = _decode_float32(r, 40)
                block_success = True
            else:
                logger.debug("Meter %s Block 2 read error: %s", address, result)

            # ── Block 3: Line-Line voltages (regs 200-207 = 8 regs) ──
            result = await client.read_input_registers(
                address=EM96Registers.V12, count=8, slave=address
            )
            if not result.isError():
                r = result.registers
                reading.voltage_ab = _decode_float32(r, 0)
                reading.voltage_bc = _decode_float32(r, 2)
                reading.voltage_ca = _decode_float32(r, 4)
                reading.voltage_ll_avg = _decode_float32(r, 6)
                block_success = True
            else:
                logger.debug("Meter %s Block 3 read error: %s", address, result)

            # ── Block 4: Neutral current (regs 224-225 = 2 regs) ──
            result = await client.read_input_registers(
                address=EM96Registers.I_N, count=2, slave=address
            )
            if not result.isError():
                reading.current_n = _decode_float32(result.registers, 0)
                block_success = True
            else:
                logger.debug("Meter %s Block 4 read error: %s", address, result)

            if not block_success:
                self._consecutive_errors[meter_key] = self._consecutive_errors.get(meter_key, 0) + 1
                reading.connected = False
                if self._consecutive_errors[meter_key] >= self._max_errors:
                    logger.warning(
                        "%s meter is reachable on serial but returned Modbus errors for all blocks",
                        meter_key.upper(),
                    )
                    self._mark_meter_disconnected(meter_key)
                return

            if not angles_loaded:
                # ── Fallback derivation from PF ──
                self._derive_angles(reading)

            reading.timestamp = time.time()
            reading.connected = True
            self._consecutive_errors[meter_key] = 0

        except Exception as e:
            self._consecutive_errors[meter_key] = self._consecutive_errors.get(meter_key, 0) + 1
            if self._consecutive_errors[meter_key] >= self._max_errors:
                reading.connected = False
                logger.warning(
                    "%s meter (addr %s) lost (%s errors): %s",
                    meter_key.upper(),
                    address,
                    self._max_errors,
                    e,
                )
                self._mark_meter_disconnected(meter_key)
            else:
                logger.debug(
                    "%s meter (addr %s) error #%s: %s",
                    meter_key.upper(),
                    address,
                    self._consecutive_errors[meter_key],
                    e,
                )

    def _derive_angles(self, reading: MeterReading):
        """Derive current phase angles from power factor values.
        Voltage angles are assumed balanced: 0°, -120°, +120°.
        Current angles = voltage angle ± acos(PF).
        """
        reading.angle_v1 = 0.0
        reading.angle_v2 = -120.0
        reading.angle_v3 = 120.0

        for phase_idx, (pf_val, v_angle) in enumerate([
            (reading.pf_a, 0.0),
            (reading.pf_b, -120.0),
            (reading.pf_c, 120.0),
        ]):
            pf_clamped = max(0.0, min(1.0, abs(pf_val)))
            if pf_clamped > 0.01:
                angle_offset = math.degrees(math.acos(pf_clamped))
                # If Q > 0 → inductive/lagging → current lags voltage
                if reading.q_total > 0:
                    current_angle = v_angle - angle_offset
                else:
                    current_angle = v_angle + angle_offset
            else:
                current_angle = v_angle

            if phase_idx == 0:
                reading.angle_i1 = current_angle
            elif phase_idx == 1:
                reading.angle_i2 = current_angle
            else:
                reading.angle_i3 = current_angle

    def _generate_simulation_data(self):
        """Generate stable simulation data — no trip under normal conditions.
        Uses exact rated values from config so I_diff ≈ 0.
        Supports fault injection via self._fault_inject."""
        now = time.time()
        tx = app_config.transformer

        v_hv = float(tx.v_hv)   # e.g., 440V for Dd0 Tap1
        v_lv = float(tx.v_lv)   # e.g., 220V
        i_hv = float(tx.i_rated_hv_secondary)  # rated A seen by meter
        i_lv = float(tx.i_rated_lv_secondary)

        # ── HV meter ──
        hv = self.hv_reading
        hv.connected = True
        hv.timestamp = now
        hv.voltage_ab = v_hv
        hv.voltage_bc = v_hv
        hv.voltage_ca = v_hv
        hv.voltage_ll_avg = v_hv
        hv.voltage_an = v_hv / math.sqrt(3)
        hv.voltage_bn = v_hv / math.sqrt(3)
        hv.voltage_cn = v_hv / math.sqrt(3)
        hv.voltage_ln_avg = v_hv / math.sqrt(3)
        hv.current_a = i_hv
        hv.current_b = i_hv
        hv.current_c = i_hv
        hv.current_n = 0.0
        hv.current_avg = i_hv
        hv.pf_a = 0.95
        hv.pf_b = 0.95
        hv.pf_c = 0.95
        hv.pf_total = 0.95
        hv.frequency = 50.0
        hv.p_total = v_hv * i_hv * math.sqrt(3) * 0.95
        hv.q_total = hv.p_total * 0.33
        hv.s_total = math.sqrt(hv.p_total**2 + hv.q_total**2)
        self._derive_angles(hv)

        # ── LV meter ──
        lv = self.lv_reading
        lv.connected = True
        lv.timestamp = now
        lv.voltage_ab = v_lv
        lv.voltage_bc = v_lv
        lv.voltage_ca = v_lv
        lv.voltage_ll_avg = v_lv
        lv.voltage_an = v_lv / math.sqrt(3)
        lv.voltage_bn = v_lv / math.sqrt(3)
        lv.voltage_cn = v_lv / math.sqrt(3)
        lv.voltage_ln_avg = v_lv / math.sqrt(3)
        # LV current = HV current × turns ratio (power conservation)
        lv.current_a = i_lv
        lv.current_b = i_lv
        lv.current_c = i_lv
        lv.current_n = 0.0
        lv.current_avg = i_lv
        lv.pf_a = 0.95
        lv.pf_b = 0.95
        lv.pf_c = 0.95
        lv.pf_total = 0.95
        lv.frequency = 50.0
        lv.p_total = v_lv * i_lv * math.sqrt(3) * 0.95
        lv.q_total = lv.p_total * 0.33
        lv.s_total = math.sqrt(lv.p_total**2 + lv.q_total**2)
        self._derive_angles(lv)

        # ── Apply fault injection (if active) ──
        fi = self._fault_inject
        if fi.get("active"):
            side = fi.get("side", "lv")
            target = lv if side == "lv" else hv
            # Multiply phase currents by fault factor
            factor = fi.get("factor", 3.0)
            phases = fi.get("phases", ["A", "B", "C"])
            if "A" in phases:
                target.current_a *= factor
            if "B" in phases:
                target.current_b *= factor
            if "C" in phases:
                target.current_c *= factor
            target.current_avg = (target.current_a + target.current_b + target.current_c) / 3

    def inject_fault(self, phases: list = None, factor: float = 3.0, side: str = "lv"):
        """Inject a simulated fault (multiply LV/HV current by factor)."""
        self._fault_inject = {
            "active": True,
            "phases": phases or ["A", "B", "C"],
            "factor": factor,
            "side": side,
        }
        logger.info(f"Fault injected: {self._fault_inject}")

    def clear_fault(self):
        """Clear injected fault."""
        self._fault_inject = {"active": False}
        logger.info("Fault cleared")


# Singleton
modbus_service = ModbusService()
