"""
ทดสอบอ่าน Register ต่างๆ ของมิเตอร์ EM96
เพื่อหา Register Map ที่ถูกต้อง
"""

from pymodbus.client import ModbusSerialClient
import struct
import time

def decode_float32(regs, index=0):
    """Decode 2 registers -> float32"""
    high = regs[index]
    low = regs[index + 1]
    raw = struct.pack('>HH', high, low)
    return struct.unpack('>f', raw)[0]

def scan_registers(port='COM4', baudrate=38400, slave_id=1):
    """สแกนอ่าน register หลายๆ address เพื่อหาข้อมูล"""

    client = ModbusSerialClient(
        port=port,
        baudrate=baudrate,
        parity='N',
        stopbits=1,
        bytesize=8,
        timeout=1
    )

    if not client.connect():
        print(f"ไม่สามารถเชื่อมต่อ {port}")
        return

    print(f"เชื่อมต่อ {port} สำเร็จ (Baud: {baudrate}, Slave: {slave_id})")
    print("=" * 60)

    # address ที่น่าสนใจต่างๆ
    test_addresses = [
        (0, 20, "Block 0: Registers 0-19"),
        (20, 20, "Block 20: Registers 20-39"),
        (30, 20, "Block 30: Registers 30-49"),
        (100, 20, "Block 100: Registers 100-119"),
        (200, 20, "Block 200: Registers 200-219"),
        (224, 10, "Block 224: Registers 224-233"),
        (300, 20, "Block 300: Registers 300-319"),
        (500, 20, "Block 500: Registers 500-519"),
    ]

    for addr, count, desc in test_addresses:
        print(f"\n{desc}:")
        print("-" * 60)

        try:
            result = client.read_input_registers(
                address=addr,
                count=count,
                slave=slave_id
            )

            if result.isError():
                print(f"  ERROR: {result}")
                continue

            regs = result.registers
            print(f"  Read {len(regs)} registers")

            # แสดงผลแบบ raw
            for i, reg in enumerate(regs[:10]):  # แสดง 10 registers แรก
                print(f"  Reg {addr+i}: {reg} (0x{reg:04X})")

            # ลอง decode เป็น float
            if len(regs) >= 2:
                for i in range(0, min(len(regs)-1, 10), 2):
                    val = decode_float32(regs, i)
                    if 0.1 < abs(val) < 10000:  # ค่าที่สมเหตุสมผล
                        print(f"    -> Float[{addr+i}]: {val:.2f}")

        except Exception as e:
            print(f"  Exception: {e}")

        time.sleep(0.1)

    # ทดสอบ Holding Registers (FC 03) ด้วย
    print("\n" + "=" * 60)
    print("Holding Registers (FC 03):")
    print("=" * 60)

    for addr in [0, 100, 200]:
        try:
            result = client.read_holding_registers(
                address=addr,
                count=10,
                slave=slave_id
            )

            if not result.isError():
                print(f"\nHolding Reg {addr}-{addr+9}:")
                for i, reg in enumerate(result.registers):
                    print(f"  Reg {addr+i}: {reg} (0x{reg:04X})")
            else:
                print(f"Holding Reg {addr}: ERROR")

        except Exception as e:
            print(f"Holding Reg {addr}: Exception {e}")

    client.close()
    print("\n" + "=" * 60)
    print("เสร็จสิ้น")


if __name__ == "__main__":
    print("EM96 Register Scanner")
    print("=" * 60)

    # ทดสอบ Slave ID 1
    scan_registers(port='COM4', baudrate=38400, slave_id=1)

    print("\n\n")

    # ทดสอบ Slave ID 2
    scan_registers(port='COM4', baudrate=38400, slave_id=2)
