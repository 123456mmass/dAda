"""
ทดสอบอ่านค่าจากมิเตอร์ EM96 แบบง่าย
"""

from pymodbus.client import ModbusSerialClient
import struct

def decode_float32(regs, index=0):
    high = regs[index]
    low = regs[index + 1]
    raw = struct.pack('>HH', high, low)
    return struct.unpack('>f', raw)[0]

client = ModbusSerialClient(
    port='COM4',
    baudrate=38400,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)

print("Connecting to COM4...")
if not client.connect():
    print("FAILED to connect!")
    exit(1)

print("Connected!")

# ทดสอบอ่าน register 0-5 (Voltage L-N)
print("\n--- Reading Input Registers (FC 04) ---")
for addr in [0, 6, 30, 200]:
    result = client.read_input_registers(address=addr, count=2, slave=1)
    if result.isError():
        print(f"Addr {addr}: ERROR - {result}")
    else:
        val = decode_float32(result.registers, 0)
        print(f"Addr {addr}: {result.registers} -> {val:.2f}")

# ทดสอบ Slave 2
print("\n--- Slave 2 ---")
for addr in [0, 6]:
    result = client.read_input_registers(address=addr, count=2, slave=2)
    if result.isError():
        print(f"Addr {addr}: ERROR - {result}")
    else:
        val = decode_float32(result.registers, 0)
        print(f"Addr {addr}: {result.registers} -> {val:.2f}")

client.close()
print("\nDone!")
