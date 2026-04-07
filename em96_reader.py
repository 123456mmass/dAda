"""
RTR EM96 Energy Meter Reader
เชื่อมต่อกับมิเตอร์พลังงาน RTR EM96 ผ่าน Modbus RTU (RS485)
"""

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import time
import serial
import serial.tools.list_ports

class EM96Meter:
    """คลาสสำหรับอ่านค่าจากมิเตอร์ RTR EM96"""

    def __init__(self, port='COM3', baudrate=9600, slave_id=1):
        """
        เริ่มต้นการเชื่อมต่อกับมิเตอร์

        Args:
            port: พอร์ต COM (เช่น 'COM3' หรือ '/dev/ttyUSB0')
            baudrate: อัตราเร็ว baud (ปกติ 9600 หรือ 19200)
            slave_id: Slave ID ของมิเตอร์ (ปกติ 1)
        """
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.client = None

    def connect(self):
        """เปิดการเชื่อมต่อกับมิเตอร์"""
        self.client = ModbusSerialClient(
            method='rtu',
            port=self.port,
            baudrate=self.baudrate,
            stopbits=1,
            bytesize=8,
            parity='N',
            timeout=1
        )
        if self.client.connect():
            print(f"[OK] เชื่อมต่อกับมิเตอร์ที่ {self.port} สำเร็จ")
            return True
        else:
            print(f"[ERROR] ไม่สามารถเชื่อมต่อกับมิเตอร์ที่ {self.port}")
            return False

    def disconnect(self):
        """ปิดการเชื่อมต่อ"""
        if self.client:
            self.client.close()
            print("[OK] ปิดการเชื่อมต่อแล้ว")

    def read_registers(self, address, count=1):
        """
        อ่านค่าจาก Input Registers (FC 04)

        Args:
            address: เริ่มต้น register address
            count: จำนวน register ที่จะอ่าน

        Returns:
            list ของค่าที่อ่านได้ หรือ None ถ้ามีข้อผิดพลาด
        """
        if not self.client or not self.client.connected:
            print("[ERROR] ไม่มีการเชื่อมต่อ")
            return None

        try:
            result = self.client.read_input_registers(
                address=address,
                count=count,
                slave=self.slave_id
            )

            if result.isError():
                print(f"[ERROR] เกิดข้อผิดพลาดในการอ่าน: {result}")
                return None

            return result.registers

        except ModbusException as e:
            print(f"[ERROR] Modbus Exception: {e}")
            return None

    def read_input_registers(self, address, count=1):
        """
        อ่านค่าจาก Input Registers

        Args:
            address: เริ่มต้น register address
            count: จำนวน register ที่จะอ่าน

        Returns:
            list ของค่าที่อ่านได้ หรือ None ถ้ามีข้อผิดพลาด
        """
        if not self.client or not self.client.connected:
            print("[ERROR] ไม่มีการเชื่อมต่อ")
            return None

        try:
            result = self.client.read_input_registers(
                address=address,
                count=count,
                slave=self.slave_id
            )

            if result.isError():
                print(f"[ERROR] เกิดข้อผิดพลาดในการอ่าน: {result}")
                return None

            return result.registers

        except ModbusException as e:
            print(f"[ERROR] Modbus Exception: {e}")
            return None

    def get_voltage_ln(self):
        """อ่านค่าแรงดันไฟฟ้าเฟส-นิวทรัล (V)"""
        regs = self.read_registers(address=0, count=6)
        if regs:
            van = self._regs_to_float32(regs[0:2])
            vbn = self._regs_to_float32(regs[2:4])
            vcn = self._regs_to_float32(regs[4:6])
            return van, vbn, vcn
        return None, None, None

    def get_voltage_ll(self):
        """อ่านค่าแรงดันไฟฟ้าเฟส-เฟส (V)"""
        regs = self.read_registers(address=200, count=8)
        if regs:
            vab = self._regs_to_float32(regs[0:2])
            vbc = self._regs_to_float32(regs[2:4])
            vca = self._regs_to_float32(regs[4:6])
            return vab, vbc, vca
        return None, None, None

    def get_current(self):
        """อ่านค่ากระแสไฟฟ้า (A)"""
        regs = self.read_registers(address=6, count=6)
        if regs:
            ia = self._regs_to_float32(regs[0:2])
            ib = self._regs_to_float32(regs[2:4])
            ic = self._regs_to_float32(regs[4:6])
            return ia, ib, ic
        return None, None, None

    def get_power_factor(self):
        """อ่านค่า Power Factor"""
        regs = self.read_registers(address=30, count=6)
        if regs:
            pf_a = self._regs_to_float32(regs[0:2])
            pf_b = self._regs_to_float32(regs[2:4])
            pf_c = self._regs_to_float32(regs[4:6])
            return pf_a, pf_b, pf_c
        return None, None, None

    def get_power(self):
        """อ่านค่ากำลังไฟฟ้า (W)"""
        regs = self.read_registers(address=52, count=2)
        if regs:
            p_total = self._regs_to_float32(regs[0:2])
            return p_total
        return None

    def get_energy(self):
        """อ่านค่าพลังงานสะสม (kWh) - address 102"""
        regs = self.read_registers(address=102, count=2)
        if regs:
            energy = self._regs_to_float32(regs[0:2])
            return energy
        return None

    def get_frequency(self):
        """อ่านค่าความถี่ (Hz) - address 70"""
        regs = self.read_registers(address=70, count=2)
        if regs:
            freq = self._regs_to_float32(regs[0:2])
            return freq
        return None

    def _regs_to_float32(self, regs):
        """แปลง 2 registers เป็น Float32"""
        import struct
        # รวม 2 registers (16-bit each) เป็น 32-bit
        combined = (regs[0] << 16) | regs[1]
        # แปลงเป็น float
        return struct.unpack('>f', struct.pack('>I', combined))[0]


def list_com_ports():
    """แสดงรายการพอร์ต COM ที่มีในระบบ"""
    print("\nพอร์ต COM ที่มีในระบบ:")
    print("-" * 50)
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  ไม่พบพอร์ต COM ใดๆ")
    else:
        for port in ports:
            print(f"  {port.device} - {port.description}")
    print("-" * 50)
    return [p.device for p in ports]


def main():
    """ฟังก์ชันหลักสำหรับทดสอบการเชื่อมต่อ"""

    print("=" * 50)
    print("RTR EM96 Energy Meter Reader")
    print("มิเตอร์ 2 ตัว (Slave ID: 1, 2)")
    print("=" * 50)

    # แสดงพอร์ต COM ที่มี
    available_ports = list_com_ports()

    # การตั้งค่า
    PORT = 'COM4'
    BAUDRATE = 38400
    SLAVE_IDS = [1, 2]  # Slave IDs ของมิเตอร์ทั้ง 2 ตัว

    # ตรวจสอบว่าพอร์ตที่ต้องการมีในระบบหรือไม่
    if PORT not in available_ports:
        print(f"\n[WARNING] ไม่พบ {PORT} ในระบบ!")
        print(f"กรุณาเปลี่ยน PORT ในโค้ดเป็นพอร์ตที่มี เช่น {available_ports[0] if available_ports else 'COM1'}")
        return

    # สร้าง client สำหรับแต่ละมิเตอร์
    meters = []
    for slave_id in SLAVE_IDS:
        meter = EM96Meter(port=PORT, baudrate=BAUDRATE, slave_id=slave_id)
        meters.append(meter)

    # เชื่อมต่อกับมิเตอร์ตัวแรก (ใช้ connection เดียวกัน)
    if not meters[0].connect():
        print("\nกรุณาตรวจสอบ:")
        print("  1. สายเชื่อมต่อ RS485")
        print("  2. พอร์ต COM ที่ถูกต้อง")
        print("  3. การตั้งค่า Baud Rate (38400)")
        print("  4. Slave ID ของมิเตอร์")
        return

    try:
        # รอให้มิเตอร์พร้อม
        time.sleep(0.5)

        # อ่านค่าจากแต่ละมิเตอร์
        for slave_id in SLAVE_IDS:
            print(f"\n{'=' * 50}")
            print(f"มิเตอร์ Slave ID: {slave_id}")
            print("-" * 50)

            # อัพเดท slave_id สำหรับมิเตอร์นี้
            meters[0].slave_id = slave_id

            # อ่านค่าต่างๆ
            van, vbn, vcn = meters[0].get_voltage_ln()
            vab, vbc, vca = meters[0].get_voltage_ll()
            ia, ib, ic = meters[0].get_current()
            pf_a, pf_b, pf_c = meters[0].get_power_factor()
            p_total = meters[0].get_power()
            freq = meters[0].get_frequency()

            # แสดงผล
            print("Voltage L-N (V):")
            if van is not None: print(f"  Van: {van:.2f}")
            if vbn is not None: print(f"  Vbn: {vbn:.2f}")
            if vcn is not None: print(f"  Vcn: {vcn:.2f}")

            print("Voltage L-L (V):")
            if vab is not None: print(f"  Vab: {vab:.2f}")
            if vbc is not None: print(f"  Vbc: {vbc:.2f}")
            if vca is not None: print(f"  Vca: {vca:.2f}")

            print("Current (A):")
            if ia is not None: print(f"  Ia: {ia:.2f}")
            if ib is not None: print(f"  Ib: {ib:.2f}")
            if ic is not None: print(f"  Ic: {ic:.2f}")

            print("Power Factor:")
            if pf_a is not None: print(f"  PFa: {pf_a:.3f}")
            if pf_b is not None: print(f"  PFb: {pf_b:.3f}")
            if pf_c is not None: print(f"  PFc: {pf_c:.3f}")

            if p_total is not None:
                print(f"Power (W): {p_total:.2f}")
            if freq is not None:
                print(f"Frequency (Hz): {freq:.2f}")

            # ถ้าไม่ได้รับข้อมูล
            if all(v is None for v in [van, vbn, vcn, ia, ib, ic]):
                print("  ไม่ได้รับข้อมูล - ตรวจสอบ Slave ID และการเชื่อมต่อ")

            time.sleep(0.2)  # เว้นระยะระหว่างการอ่าน

    except KeyboardInterrupt:
        print("\n\nหยุดการทำงานโดยผู้ใช้")

    finally:
        meters[0].disconnect()


if __name__ == "__main__":
    main()
