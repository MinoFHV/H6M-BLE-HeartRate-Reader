import asyncio
import argparse
import csv
import os
from datetime import datetime

from bleak import BleakClient, BleakScanner

# All BLE characteristic UUIDs are of the form: 0000xxxx-0000-1000-8000-00805f9b34fb
# 2a37 is the standard UUID for Heart Rate Measurement characteristic
# See https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Assigned_Numbers/out/en/Assigned_Numbers.pdf
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_NAME_SUBSTRING = "H6M"


class H6MHeartRateMonitor:
    def __init__(self, enable_tcp: bool, enable_txt_output: bool,
                 enable_csv_output: bool, ble_timeout: int):
        self.enable_tcp = enable_tcp
        self.enable_txt_output = enable_txt_output
        self.enable_csv_output = enable_csv_output
        self.ble_timeout = ble_timeout

        self.latest_hr: int = 0
        self.tcp_clients: set[asyncio.StreamWriter] = set()

        self.txt_file = None
        self.csv_file = None
        self.csv_writer = None

        self.tcp_server = None
        self.tcp_broadcast_task = None

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

            if self.enable_txt_output and self.txt_file:
                self.txt_file.seek(0)
                self.txt_file.write(f"{hr} bpm")
                self.txt_file.truncate()
                self.txt_file.flush()

            if self.enable_csv_output and self.csv_file and self.csv_writer:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.csv_writer.writerow([timestamp, hr])
                self.csv_file.flush()
        else:
            print(f"Failed to parse heart rate data: {data.hex()}")

    @staticmethod
    def parse_heart_rate(data: bytearray):
        if not data:
            return None

        flags = data[0]
        hr_format = flags & 0x01

        if hr_format == 0:
            # Heart Rate is in uint8 format
            if len(data) >= 2:
                return data[1]
        else:
            # Heart Rate is in uint16 format
            if len(data) >= 3:
                return int.from_bytes(data[1:3], byteorder="little")

        return None

    async def handle_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("New TCP client connected.")
        self.tcp_clients.add(writer)

        try:
            while True:
                await asyncio.sleep(0.1)
        except Exception:
            pass
        finally:
            if writer in self.tcp_clients:
                self.tcp_clients.remove(writer)
            writer.close()
            await writer.wait_closed()
            print("TCP client disconnected.")

    async def tcp_broadcast_loop(self):
        while True:
            if self.tcp_clients:
                message = f"{self.latest_hr}\n".encode()
                for writer in list(self.tcp_clients):
                    try:
                        writer.write(message)
                        await writer.drain()
                    except Exception:
                        if writer in self.tcp_clients:
                            self.tcp_clients.remove(writer)
                        writer.close()
                        await writer.wait_closed()
            await asyncio.sleep(1)

    def setup_outputs(self):
        if self.enable_txt_output:
            self.txt_file = open("heart_rate.txt", "w")
            print("Text output enabled. Writing to heart_rate.txt")

        if self.enable_csv_output:
            os.makedirs("logs", exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            csv_filename = f"logs/heart_rate_{timestamp}.csv"
            self.csv_file = open(csv_filename, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["timestamp", "bpm"])
            print(f"CSV output enabled. Writing to {csv_filename}")

    async def start_tcp_server(self):
        if not self.enable_tcp:
            return

        self.tcp_server = await asyncio.start_server(
            lambda r, w: asyncio.create_task(self.handle_tcp_client(r, w)),
            "127.0.0.1",
            8888,
        )
        print("TCP server started on 127.0.0.1:8888")
        self.tcp_broadcast_task = asyncio.create_task(self.tcp_broadcast_loop())

    async def stop_tcp_server(self):
        if self.tcp_broadcast_task:
            self.tcp_broadcast_task.cancel()
            try:
                await self.tcp_broadcast_task
            except asyncio.CancelledError:
                pass

        if self.tcp_server:
            self.tcp_server.close()
            await self.tcp_server.wait_closed()
            print("TCP server stopped.")

    def cleanup_outputs(self):
        if self.txt_file:
            self.txt_file.close()
            self.txt_file = None
            print("Text file closed.")
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            print("CSV file closed.")

    async def run(self):
        device = await self.scan_ble_devices()
        if device is None:
            return

        self.setup_outputs()
        await self.start_tcp_server()

        try:
            print(f"Connecting to {device.name} ({device.address})...")
            async with BleakClient(device) as client:
                if client.is_connected:
                    print(f"Connected to {device.name} ({device.address})")
                else:
                    print(f"Failed to connect to {device.name} ({device.address})")

                print("Subscribing to Heart Rate Measurement notifications...")
                await client.start_notify(HR_MEASUREMENT_UUID, self.hr_measurement_handler)

                print("Listening for heart rate data... Press Ctrl+C to stop.")
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("Stopping notifications...")
                    await client.stop_notify(HR_MEASUREMENT_UUID)
        finally:
            await self.stop_tcp_server()
            self.cleanup_outputs()


async def main():
    parser = argparse.ArgumentParser(description="H6M BLE Heart Rate Monitor")
    parser.add_argument("--tcp", action="store_true", help="Activate TCP server on 127.0.0.1:8888")
    parser.add_argument("--txt", action="store_true", help="Activate .txt file output")
    parser.add_argument("--logcsv", action="store_true", help="Activate .csv file logging")
    parser.add_argument(
        "--ble_timeout",
        type=int,
        default=10,
        help="BLE scanning timeout in seconds (default: 10)",
    )
    args = parser.parse_args()

    monitor = H6MHeartRateMonitor(
        enable_tcp=args.tcp,
        enable_txt_output=args.txt,
        enable_csv_output=args.logcsv,
        ble_timeout=args.ble_timeout,
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
