import asyncio
from bleak import BleakClient, BleakScanner


# All BLE characteristic UUIDs are of the form:# 0000xxxx-0000-1000-8000-00805f9b34fb
# 2a37 is the standard UUID for Heart Rate Measurement characteristic
# See https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Assigned_Numbers/out/en/Assigned_Numbers.pdf
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_NAME_SUBSTRING = "H6M"


async def scan_ble_devices(scan_timeout_time: int = 10):
    print("Scanning for BLE devices...")
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
    hr = parse_heart_rate(data)
    if hr is not None:
        print(f"Heart Rate: {hr} bpm")
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

async def main():
    device = await scan_ble_devices()
    if device is None:
        return
    
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

asyncio.run(main())