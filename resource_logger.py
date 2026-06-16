import csv
import signal
import sys
import time

import psutil


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 resource_logger.py <pid> <output_csv>")
        sys.exit(1)

    try:
        target_pid = int(sys.argv[1])
        out_path   = sys.argv[2]
    except ValueError:
        print("PID harus integer.")
        sys.exit(1)

    running = [True]
    def _stop(signum, frame):
        running[0] = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT,  _stop)

    try:
        proc = psutil.Process(target_pid)
    except psutil.NoSuchProcess:
        print(f"PID {target_pid} tidak ditemukan.")
        sys.exit(1)

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "cpu_pct", "mem_rss_mb", "mem_pct",
            "num_threads", "num_fds",
        ])
        f.flush()

        while running[0]:
            try:
                cpu  = proc.cpu_percent(interval=0.5)
                mem  = proc.memory_info()
                nfd  = proc.num_fds() if hasattr(proc, "num_fds") else 0

                writer.writerow([
                    round(time.time(), 3),
                    round(cpu, 2),
                    round(mem.rss / 1024 / 1024, 3),   # RSS dalam MB
                    round(proc.memory_percent(), 3),
                    proc.num_threads(),
                    nfd,
                ])
                f.flush()

            except psutil.NoSuchProcess:
                break
            except Exception as e:
                print(f"[resource_logger] WARNING: {e}", file=sys.stderr)

            time.sleep(0.5)


if __name__ == "__main__":
    main()