import asyncio
from bleak import BleakClient, BleakScanner

from .outputs import HeartRateOutputManager
from .tcp_server import HeartRateTCPServer

# All BLE characteristic UUIDs are of the form: 0000xxxx-0000-1000-8000-00805f9b34fb
# 2a37 is the standard UUID for Heart Rate Measurement characteristic
# See https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Assigned_Numbers/out/en/Assigned_Numbers.pdf
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_NAME_SUBSTRING = "H6M"


class H6MHeartRateMonitor:
    def __init__(self, enable_tcp: bool, enable_txt_output: bool,
                 enable_csv_output: bool, ble_timeout: int):
        self.enable_tcp = enable_tcp
        self.ble_timeout = ble_timeout

        self.latest_hr: int = 0

        # Composition: delegate responsibilities
        self.outputs = HeartRateOutputManager(
            enable_txt_output=enable_txt_output,
            enable_csv_output=enable_csv_output,
        )

        self.tcp_server: HeartRateTCPServer | None = None
        if enable_tcp:
            self.tcp_server = HeartRateTCPServer(
                host="127.0.0.1",
                port=8888,
                get_latest_hr=self.get_latest_hr,
            )

    def get_latest_hr(self) -> int:
        return self.latest_hr

    async def scan_ble_devices(self):
        while True:
            print(f"Scanning for BLE devices (timeout: {self.ble_timeout}s)...")
            devices = await BleakScanner.discover(timeout=self.ble_timeout)

            if devices:
                for device in devices:
                    if device.name and TARGET_NAME_SUBSTRING.lower() in device.name.lower():
                        print(f"Found target device: {device.name} ({device.address})")
                        return device

            print("No target BLE devices found, retrying in 5 seconds... (Ctrl+C to quit)")
            await asyncio.sleep(5)

    def hr_measurement_handler(self, sender: int, data: bytearray):
        hr = self.parse_heart_rate(data)
        if hr is not None:
            self.latest_hr = hr
            print(f"Heart Rate: {hr} bpm")
            self.outputs.write_heart_rate(hr)
        else:
            print(f"Failed to parse heart rate data: {data.hex()}")

    @staticmethod
    def parse_heart_rate(data: bytearray):
        if not data:
            return None

        flags = data[0]
        hr_format = flags & 0x01

        if hr_format == 0:
            if len(data) >= 2:
                return data[1]
        else:
            if len(data) >= 3:
                return int.from_bytes(data[1:3], byteorder="little")

        return None

    async def run(self):
        device = await self.scan_ble_devices()
        if device is None:
            return

        self.outputs.open_files()

        if self.tcp_server is not None:
            await self.tcp_server.start()

        try:
            while True:
                try:
                    print(f"Connecting to {device.name} ({device.address})...")
                    async with BleakClient(device) as client:
                        if not client.is_connected:
                            print(f"Failed to connect to {device.name} ({device.address}), retrying in 5 seconds...")
                            await asyncio.sleep(5)
                            continue

                        print(f"Connected to {device.name} ({device.address})")

                        print("Subscribing to Heart Rate Measurement notifications...")
                        await client.start_notify(HR_MEASUREMENT_UUID, self.hr_measurement_handler)

                        print("Listening for heart rate data... Press Ctrl+C to stop.")
                        while True:
                            if not client.is_connected:
                                raise ConnectionError("BLE connection lost")

                            await asyncio.sleep(1)

                except KeyboardInterrupt:
                    print("Stopping monitor (Ctrl+C pressed)")
                    break

                except Exception as e:
                    print(f"Connection error: {e}")
                    print("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

        finally:
            if self.tcp_server is not None:
                await self.tcp_server.stop()
            self.outputs.close_files()
