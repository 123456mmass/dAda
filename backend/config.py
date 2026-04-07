"""
Differential Relay Protection System configuration.

Based on the Tirathai 15 kVA transformer nameplate:
  - Connection: Dd0 / YNyn0
  - HV: 440 V (Dd) / 762 V (YNyn)
  - LV: 220 V (Dd) / 381 V (YNyn)
  - 10 taps, ratio always 2:1
"""

from typing import List
import math

from pydantic import BaseModel, Field


TAP_TABLE = {
    1: {"conn": "11-11", "dd": (440, 220), "yy": (762, 381)},
    2: {"conn": "11-10", "dd": (396, 198), "yy": (686, 343)},
    3: {"conn": "11-9", "dd": (352, 176), "yy": (610, 305)},
    4: {"conn": "11-8", "dd": (308, 154), "yy": (533, 267)},
    5: {"conn": "11-7", "dd": (264, 132), "yy": (457, 229)},
    6: {"conn": "11-6", "dd": (220, 110), "yy": (381, 191)},
    7: {"conn": "11-5", "dd": (176, 88), "yy": (305, 152)},
    8: {"conn": "11-4", "dd": (132, 66), "yy": (229, 114)},
    9: {"conn": "11-3", "dd": (88, 44), "yy": (152, 76)},
    10: {"conn": "11-2", "dd": (44, 22), "yy": (76, 38)},
}


def parse_vector_group(vector_group: str) -> dict:
    """Parse transformer vector-group notation, including neutral variants."""
    raw = "".join(vector_group.strip().split())
    if not raw:
        return {
            "hv_winding": "D",
            "hv_grounded": False,
            "lv_winding": "D",
            "lv_grounded": False,
            "clock": 0,
        }

    index = len(raw)
    while index > 0 and raw[index - 1].isdigit():
        index -= 1

    prefix = raw[:index].upper()
    digits = raw[index:] or "0"

    def consume_token(text: str, start: int) -> tuple[str, bool, int]:
        remaining = text[start:]
        if remaining.startswith("YN"):
            return "Y", True, start + 2
        if remaining.startswith("Y"):
            return "Y", False, start + 1
        if remaining.startswith("D"):
            return "D", False, start + 1
        raise ValueError(f"Unsupported vector group token in '{vector_group}'")

    hv_winding, hv_grounded, next_index = consume_token(prefix, 0)
    lv_winding, lv_grounded, next_index = consume_token(prefix, next_index)
    if next_index != len(prefix):
        raise ValueError(f"Unsupported vector group format '{vector_group}'")

    return {
        "hv_winding": hv_winding,
        "hv_grounded": hv_grounded,
        "lv_winding": lv_winding,
        "lv_grounded": lv_grounded,
        "clock": int(digits),
    }


def normalize_vector_group(vector_group: str) -> str:
    """Normalize aliases such as Dyn11 or YNd1 to matrix keys like Dy11/Yd1."""
    parsed = parse_vector_group(vector_group)
    return (
        f"{parsed['hv_winding']}"
        f"{parsed['lv_winding'].lower()}"
        f"{parsed['clock']}"
    )


def vector_group_family(vector_group: str) -> str:
    """Return coarse vector-group family such as DD, DY, YD, or YY."""
    parsed = parse_vector_group(vector_group)
    return f"{parsed['hv_winding']}{parsed['lv_winding']}"


class TransformerConfig(BaseModel):
    equipment_mode: str = Field(
        default="transformer",
        description="Equipment mode: transformer or autotransformer",
    )
    kva: float = Field(default=15.0, description="Transformer rating in kVA")
    frequency: float = Field(default=50.0, description="System frequency Hz")
    detection_mode: str = Field(
        default="auto_family",
        description="Vector-group detection mode: auto_family, shared_vref, voltage_ratio, or manual_confirmed",
    )
    vector_group: str = Field(
        default="Dd0",
        description="Transformer vector group: Dd0 or YNyn0",
    )
    tap_position: int = Field(default=1, description="Tap changer position (1-10)")
    autotransformer_turns_ratio: float = Field(
        default=2.0,
        description="Fixed line-voltage turns ratio used in autotransformer lab mode",
    )
    ct_ratio_hv: float = Field(
        default=1.0,
        description="HV CT ratio (primary/secondary)",
    )
    ct_ratio_lv: float = Field(
        default=1.0,
        description="LV CT ratio (primary/secondary)",
    )
    current_base_hv_secondary: float = Field(
        default=19.68,
        description="HV current base seen by meter (secondary amps)",
    )
    current_base_lv_secondary: float = Field(
        default=39.36,
        description="LV current base seen by meter (secondary amps)",
    )
    impedance_pct: float = Field(
        default=3.37,
        description="Impedance voltage at 75 C (%)",
    )

    @property
    def v_hv(self) -> float:
        tap = TAP_TABLE.get(self.tap_position, TAP_TABLE[1])
        parsed = parse_vector_group(self.vector_group)
        key = "dd" if parsed["hv_winding"] == "D" else "yy"
        return float(tap[key][0])

    @property
    def v_lv(self) -> float:
        tap = TAP_TABLE.get(self.tap_position, TAP_TABLE[1])
        parsed = parse_vector_group(self.vector_group)
        key = "dd" if parsed["hv_winding"] == "D" else "yy"
        return float(tap[key][1])

    @property
    def i_rated_hv(self) -> float:
        return self.current_base_hv_secondary * self.ct_ratio_hv

    @property
    def i_rated_lv(self) -> float:
        return self.current_base_lv_secondary * self.ct_ratio_lv

    @property
    def i_rated_hv_secondary(self) -> float:
        return self.current_base_hv_secondary

    @property
    def i_rated_lv_secondary(self) -> float:
        return self.current_base_lv_secondary

    @property
    def nameplate_i_hv(self) -> float:
        if self.v_hv == 0:
            return 0.0
        return self.kva * 1000 / (math.sqrt(3) * self.v_hv)

    @property
    def nameplate_i_lv(self) -> float:
        if self.v_lv == 0:
            return 0.0
        return self.kva * 1000 / (math.sqrt(3) * self.v_lv)

    @property
    def turns_ratio(self) -> float:
        if self.v_lv == 0:
            return 1.0
        return self.v_hv / self.v_lv

    @property
    def phase_shift_deg(self) -> float:
        parsed = parse_vector_group(self.vector_group)
        return parsed["clock"] * 30.0

    def get_all_taps(self) -> List[dict]:
        parsed = parse_vector_group(self.vector_group)
        key = "dd" if parsed["hv_winding"] == "D" else "yy"
        result = []
        for pos, data in TAP_TABLE.items():
            result.append(
                {
                    "position": pos,
                    "connection": data["conn"],
                    "v_hv": data[key][0],
                    "v_lv": data[key][1],
                    "active": pos == self.tap_position,
                }
            )
        return result


class ModbusConfig(BaseModel):
    port: str = Field(default="auto", description="Serial port (COM*) or 'auto'")
    baudrate: int = Field(default=38400, description="Baud rate")
    parity: str = Field(default="N", description="Parity: N/E/O")
    stopbits: int = Field(default=1, description="Stop bits")
    bytesize: int = Field(default=8, description="Data bits")
    timeout: float = Field(default=1.0, description="Response timeout (seconds)")
    poll_interval_ms: int = Field(default=100, description="Poll interval in ms")
    hv_meter_address: int = Field(default=1, description="HV meter address")
    lv_meter_address: int = Field(default=2, description="LV meter address")


class EM96Registers:
    """EM96 Modbus input register addresses (0-based offsets for Function Code 04).

    Verified by scanning RTR EM96 meters at addresses 1 and 2.
    All values are Float32 (2 registers each).
    """

    # Block 1: Phase-Neutral Voltages and Currents (regs 0-11)
    V1N = 0      # Phase A voltage L-N
    V2N = 2      # Phase B voltage L-N
    V3N = 4      # Phase C voltage L-N
    I1 = 6       # Phase A current
    I2 = 8       # Phase B current
    I3 = 10      # Phase C current

    # Block 2: Power Factor and Angles (regs 30-71)
    PF1 = 30           # Power factor Phase A (negative = leading)
    PF2 = 32           # Power factor Phase B
    PF3 = 34           # Power factor Phase C
    ANGLE_V1_I1 = 36   # Angle between V1 and I1 (degrees)
    ANGLE_V2_I2 = 38   # Angle between V2 and I2 (degrees)
    ANGLE_V3_I3 = 40   # Angle between V3 and I3 (degrees)
    V_LN_AVG = 42      # Average L-N voltage
    I_AVG = 46         # Average current
    P_TOTAL = 52       # Total active power
    S_TOTAL = 56       # Total apparent power
    Q_TOTAL = 60       # Total reactive power
    PF_TOTAL = 62      # Total power factor
    FREQ = 70          # Frequency

    # Block 3: Line-Line Voltages (regs 200-207)
    V12 = 200      # Voltage L-L Phase AB
    V23 = 202      # Voltage L-L Phase BC
    V31 = 204      # Voltage L-L Phase CA
    V_LL_AVG = 206 # Average L-L voltage

    # Block 4: Neutral Current (regs 224-225)
    I_N = 224      # Neutral current


class RelayConfig(BaseModel):
    i_pickup: float = Field(default=0.50, description="Minimum differential pickup in amperes")
    slope1: float = Field(default=0.25, description="Slope 1")
    slope2: float = Field(default=0.50, description="Slope 2")
    bias_breakpoint: float = Field(default=1.0, description="Bias breakpoint")
    inrush_block_ms: int = Field(default=700, description="Trip block window immediately after energization")
    trip_delay_ms: int = Field(default=50, description="Trip confirmation delay")
    reset_delay_ms: int = Field(default=5000, description="Auto-reset delay")
    trip_enabled: bool = Field(default=True, description="Allow relay to trip")
    auto_reset: bool = Field(default=True, description="Auto-reset when normal")
    filter_zero_seq_hv: bool = Field(default=False, description="Filter zero-seq HV")
    filter_zero_seq_lv: bool = Field(default=False, description="Filter zero-seq LV")


class AppConfig(BaseModel):
    transformer: TransformerConfig = TransformerConfig()
    modbus: ModbusConfig = ModbusConfig()
    relay: RelayConfig = RelayConfig()

    def update_zero_seq_filters(self):
        """Auto-set zero-sequence filters from grounded-wye sides."""
        parsed = parse_vector_group(self.transformer.vector_group)
        self.relay.filter_zero_seq_hv = parsed["hv_grounded"]
        self.relay.filter_zero_seq_lv = parsed["lv_grounded"]


app_config = AppConfig()
