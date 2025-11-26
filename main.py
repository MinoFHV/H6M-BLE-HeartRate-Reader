import argparse
import asyncio

from h6m_monitor import H6MHeartRateMonitor


async def main():
    parser = argparse.ArgumentParser(description="H6M BLE Heart Rate Monitor")
    parser.add_argument("--tcp", action="store_true", help="Activate TCP server on 127.0.0.1:8888")
    parser.add_argument("--txt", action="store_true", help="Activate .txt file output")
    parser.add_argument("--logcsv", action="store_true", help="Activate .csv file logging")
    parser.add_argument(
        "--ble_timeout",
        type=int,
        default=5,
        help="BLE scanning timeout in seconds (default: 5)",
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
