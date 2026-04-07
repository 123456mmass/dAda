import time
from pymodbus.client import ModbusSerialClient
from pymodbus.framer.rtu_framer import ModbusRtuFramer

# Configuration reflecting the expected user parameters.
PORT = "COM5"
BAUDRATE = 38400
PARITY = "N"
STOPBITS = 1
BYTESIZE = 8
TIMEOUT = 1.0

# PM2200 Basic V_L-N reading (Address 0, Length 12)
REGISTER_ADDR = 0   

from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

def test_meter(client, slave_id):
    print(f"\n--- Testing Meter Address {slave_id} ---")
    try:
        # Test Input Registers 0-1 (V1N)
        print("  -> Testing Input Registers (FC=04) at Address 0 (V1N), Count=2")
        result = client.read_input_registers(address=0, count=2, slave=slave_id)
        if result.isError():
            print(f"     Failed: Modbus Error Response -> {result}")
        else:
            decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG, wordorder=Endian.BIG)
            v1n = decoder.decode_32bit_float()
            print(f"     Success: Raw registers -> {result.registers}")
            print(f"     Decoded Voltage V1N  -> {v1n:.2f} V")

    except Exception as e:
        print(f"     Exception occurred: {e}")

import serial.tools.list_ports

def scan_and_test():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    print(f"Discovered ports: {ports}")
    
    for port in ports:
        print(f"\n======================================")
        print(f"Initializing Modbus Serial on {port} ({BAUDRATE}, {PARITY}, {BYTESIZE}, {STOPBITS})")
        client = ModbusSerialClient(
            port=port,
            framer=ModbusRtuFramer,
            baudrate=BAUDRATE,
            parity=PARITY,
            stopbits=STOPBITS,
            bytesize=BYTESIZE,
            timeout=TIMEOUT
        )
        try:
            if client.connect():
                print(f"Successfully opened serial port {port}.")
                test_meter(client, 1)
                test_meter(client, 2)
                client.close()
                print(f"Closed serial connection for {port}.")
            else:
                print(f"Failed to open serial port {port}. May be in use or disconnected.")
        except Exception as e:
            print(f"Failed to open/test {port} with exception: {repr(e)}")

if __name__ == "__main__":
    scan_and_test()
