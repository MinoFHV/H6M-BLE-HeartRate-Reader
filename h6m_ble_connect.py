import asyncio
import argparse
import socket

from bleak import BleakClient, BleakScanner


# All BLE characteristic UUIDs are of the form:# 0000xxxx-0000-1000-8000-00805f9b34fb
# 2a37 is the standard UUID for Heart Rate Measurement characteristic
# See https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Assigned_Numbers/out/en/Assigned_Numbers.pdf
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_NAME_SUBSTRING = "H6M"

latest_hr = 0
tcp_clients = set()
txt_file = None
enable_txt_output = False


async def scan_ble_devices(scan_timeout_time: int = 10):
    print(f"Scanning for BLE devices (timeout: {scan_timeout_time}s)...")
    devices = await BleakScanner.discover(timeout = scan_timeout_time)
    
    if not devices:
        print("No BLE devices found. Make sure your strap is on and in range.")
        return
    
    for device in devices:
        if device.name and TARGET_NAME_SUBSTRING.lower() in device.name.lower():
            print(f"Found target device: {device.name} ({device.address})")
            return device
        
    print("No target BLE devices found, please ensure your strap is on and in range.")
    return None

def hr_measurement_handler(sender: int, data: bytearray):
    global latest_hr, txt_file, enable_txt_output
    hr = parse_heart_rate(data)
    if hr is not None:
        latest_hr = hr
        print(f"Heart Rate: {hr} bpm")
        if enable_txt_output and txt_file:
            txt_file.seek(0)
            txt_file.write(str(hr) + " bpm")
            txt_file.truncate()
            txt_file.flush()
    else:
        print(f"Failed to parse heart rate data: {data.hex()}")
        
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
            return int.from_bytes(data[1:3], byteorder='little')
        
    return None

async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    print("New TCP client connected.")
    tcp_clients.add(writer)
    
    try:
        while True:
            # Keep TCP connection alive
            await asyncio.sleep(0.1)
    except Exception:
        pass
    finally:
        tcp_clients.remove(writer)
        writer.close()
        await writer.wait_closed()
        print("TCP client disconnected.")

async def tcp_broadcast_loop():
    while True:
        if tcp_clients:
            message = f"{latest_hr}\n".encode()
            for writer in list(tcp_clients):
                try:
                    writer.write(message)
                    await writer.drain()
                except Exception:
                    tcp_clients.remove(writer)
                    writer.close()
                    await writer.wait_closed()
        await asyncio.sleep(1)

async def main():
    parser = argparse.ArgumentParser(description="H6M BLE Heart Rate Monitor")
    parser.add_argument("--tcp", action="store_true", help="Activate TCP server on 127.0.0.1:8888")
    parser.add_argument("--txt", action="store_true", help="Activate .txt file output")
    parser.add_argument("--ble_timeout", type=int, default=10, help="BLE scanning timeout in seconds (default: 10)")
    args = parser.parse_args()
    
    global txt_file, enable_txt_output
    enable_txt_output = args.txt
    
    if enable_txt_output:
        txt_file = open("heart_rate.txt", "w")
        print("Text output enabled. Writing to heart_rate.txt")
    
    device = await scan_ble_devices(args.ble_timeout)
    if device is None:
        if txt_file:
            txt_file.close()
        return
    
    tcp_server = None
    if args.tcp:
        tcp_server = await asyncio.start_server(handle_tcp_client, "127.0.0.1", 8888)
        print("TCP server started on 127.0.0.1:8888")
        asyncio.create_task(tcp_broadcast_loop())
    
    try:
        print(f"Connecting to {device.name} ({device.address})...")
        async with BleakClient(device) as client:
            if client.is_connected:
                print(f"Connected to {device.name} ({device.address})")
            else:
                print(f"Failed to connect to {device.name} ({device.address})")
                
            print("Subscribing to Heart Rate Measurement notifications...")
            await client.start_notify(HR_MEASUREMENT_UUID, hr_measurement_handler)
            
            print("Listening for heart rate data... Press Ctrl+C to stop.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("Stopping notifications...")
                await client.stop_notify(HR_MEASUREMENT_UUID)
    finally:
        if tcp_server:
            tcp_server.close()
            await tcp_server.wait_closed()
        if txt_file:
            txt_file.close()
            print("Text file closed.")

asyncio.run(main())