import csv
import os
from datetime import datetime


class HeartRateOutputManager:
    def __init__(self, enable_txt_output: bool, enable_csv_output: bool):
        self.enable_txt_output = enable_txt_output
        self.enable_csv_output = enable_csv_output

        self.txt_file = None
        self.csv_file = None
        self.csv_writer = None

    def open_files(self):
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

    def write_heart_rate(self, hr: int):
        if self.enable_txt_output and self.txt_file:
            self.txt_file.seek(0)
            self.txt_file.write(f"{hr} bpm")
            self.txt_file.truncate()
            self.txt_file.flush()

        if self.enable_csv_output and self.csv_file and self.csv_writer:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.csv_writer.writerow([timestamp, hr])
            self.csv_file.flush()

    def close_files(self):
        if self.txt_file:
            self.txt_file.close()
            self.txt_file = None
            print("Text file closed.")

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            print("CSV file closed.")
