import psutil
import time
import csv
import sys

PID = int(sys.argv[1])

OUTPUT = sys.argv[2]

process = psutil.Process(PID)

with open(OUTPUT, "w") as f:

    writer = csv.writer(f)

    writer.writerow([
        "timestamp",
        "cpu_percent",
        "memory_percent"
    ])

    while True:

        try:

            cpu = process.cpu_percent(interval=1)

            mem = process.memory_percent()

            writer.writerow([
                time.time(),
                cpu,
                mem
            ])

            f.flush()

        except:

            break