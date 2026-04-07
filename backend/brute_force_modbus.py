import time
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient

# Common configurations to test
BAUDRATES = [9600, 19200, 38400, 115200]
PARITIES = ['N', 'E', 'O']
SLAVES = [1, 2, 3, 4, 10, 11] # Expanded slave ID search
ADDRESSES = [0, 1, 2, 10, 100, 3000, 4000] # Common default starting registers

def brute_force():
    ports = ["COM5"]

    for target_port in ports:
        print(f"\nBrute forcing Modbus RTU on {target_port} ...")
        
        # Quick test if port is even openable
        test_client = ModbusSerialClient(port=target_port, baudrate=9600, timeout=0.1)
        if not test_client.connect():
            print(f"Skipping {target_port}: Port cannot be opened.")
            continue
        test_client.close()
        
        for b in BAUDRATES:
            for p in PARITIES:
                client = ModbusSerialClient(
                    port=target_port,
                    baudrate=b,
                    parity=p,
                    stopbits=1,
                    bytesize=8,
                    timeout=0.3  # Short timeout for brute forcing
                )
                if not client.connect():
                    continue
                    
                for slave in SLAVES:
                    for addr in ADDRESSES:
                        # Test Input Register
                        res = client.read_input_registers(address=addr, count=1, slave=slave)
                        if not res.isError():
                            print(f"\n[!!! SUCCESS !!!] Found Meter at => Port: {target_port}, Baud: {b}, Parity: '{p}', Slave: {slave}")
                            print(f"Register (Input) Address {addr} responded with: {res.registers}")
                            client.close()
                            return
                        
                        # Test Holding Register
                        res2 = client.read_holding_registers(address=addr, count=1, slave=slave)
                        if not res2.isError():
                            print(f"\n[!!! SUCCESS !!!] Found Meter at => Port: {target_port}, Baud: {b}, Parity: '{p}', Slave: {slave}")
                            print(f"Register (Holding) Address {addr} responded with: {res2.registers}")
                            client.close()
                            return
                
                client.close()
        
        print(f"[FAILED] Explored all combinations on {target_port}. No meter responded.")

if __name__ == "__main__":
    brute_force()
