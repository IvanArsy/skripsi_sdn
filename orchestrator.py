import argparse
import csv
import itertools
import logging
import subprocess
import sys
import time
from pathlib import Path

from mininet.net  import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.log  import setLogLevel

from topology import PartialMeshTopo

import traffic
import ditg


RESULTS_DIR   = Path("./results")

CONTROLLERS   = {
    "static": "controllers/controller_static.py",
    "sp":     "controllers/controller_sp.py",
    "topsis": "controllers/controller_topsis.py",
}

ROUTING_MODES = ["static", "sp", "topsis"]
LOAD_LEVELS   = ["light", "medium", "heavy"]

WARMUP_SEC    = 90
STEADY_SEC    = 30
TRAFFIC_SEC   = 600

#   h6 →h56  : area bawah  (row 0 kiri → row 0 kanan)
#   h16→h66  : area tengah (row 1 kiri → row 1 kanan)
#   h46→h92  : area atas   (row 4 kiri → row 4 kanan)
DITG_PAIRS    = [("h6", "h56"), ("h16", "h66"), ("h46", "h92")]
DITG_DUR_MS   = 60_000  

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%H:%M:%S",
    handlers = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler("./logs/live.log"),
    ],
    force   = True,   
)
log = logging.getLogger("orchestrator")
logging.getLogger().handlers[0].setStream(sys.stdout)
for handler in logging.getLogger().handlers:
    handler.flush = lambda: sys.stdout.flush()

def cleanup():
    """Bunuh semua proses sisa. Aman dipanggil berkali-kali."""
    log.info("Cleanup...")
    cmds = [
        ["sudo", "mn",    "-c"],
        ["sudo", "pkill", "-9", "-f", "ryu-manager"],
        ["sudo", "pkill", "-9", "-f", "iperf3"],
        ["sudo", "pkill", "-9", "-f", "ITGSend"],
        ["sudo", "pkill", "-9", "-f", "ITGRecv"],
        ["sudo", "pkill", "-9", "-f", "resource_logger.py"],
    ]
    for cmd in cmds:
        subprocess.run(cmd, capture_output=True, timeout=10)
    time.sleep(3)
    log.info("Cleanup selesai.")


def start_controller(routing: str, log_path: Path) -> subprocess.Popen:
    ctrl_file = CONTROLLERS[routing]
    if not Path(ctrl_file).exists():
        raise FileNotFoundError(f"Controller tidak ditemukan: {ctrl_file}")

    log.info("Start controller: %s", ctrl_file)
    fh = open(log_path, "w")
    proc = subprocess.Popen(
        [
            "ryu-manager", ctrl_file,
            "ryu.topology.switches",
            "--observe-links",
            "--ofp-tcp-listen-port", "6633",
        ],
        stdout=fh, stderr=fh,
    )
    log.info("Controller PID: %d", proc.pid)
    return proc


def start_mininet() -> Mininet:
    setLogLevel("warning")   # kurangi noise Mininet
    logging.getLogger("orchestrator").setLevel(logging.INFO)
    logging.getLogger("traffic").setLevel(logging.INFO)
    logging.getLogger("ditg").setLevel(logging.INFO)

    net = Mininet(
        topo        = PartialMeshTopo(),
        controller  = RemoteController("c0", ip="127.0.0.1", port=6633),
        link        = TCLink,
        autoSetMacs = True,
    )
    net.start()
    log.info("Mininet started: %d switch, %d host",
             len(net.switches), len(net.hosts))
    return net


def start_resource_logger(controller_pid: int,
                           csv_path: Path) -> subprocess.Popen:
    log.info("Start resource logger (target PID: %d)", controller_pid)
    proc = subprocess.Popen(
        [sys.executable, "resource_logger.py",
         str(controller_pid), str(csv_path)]
    )
    return proc


def save_summary(result_dir: Path, routing: str, load: str,
                 run_id: int, ditg_results: list):
    path = result_dir / "summary.csv"
    fields = [
        "routing", "load", "run_id", "probe",
        "src", "dst",
        "avg_delay_ms", "avg_jitter_ms",
        "loss_pct", "avg_bitrate_kbps",
        "pkts_sent", "pkts_recv",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(ditg_results):
            w.writerow({
                "routing":          routing,
                "load":             load,
                "run_id":           run_id,
                "probe":            i + 1,
                "src":              r.get("src",             "N/A"),
                "dst":              r.get("dst",             "N/A"),
                "avg_delay_ms":     r.get("avg_delay_ms",    "N/A"),
                "avg_jitter_ms":    r.get("avg_jitter_ms",   "N/A"),
                "loss_pct":         r.get("loss_pct",        "N/A"),
                "avg_bitrate_kbps": r.get("avg_bitrate_kbps","N/A"),
                "pkts_sent":        r.get("pkts_sent",       "N/A"),
                "pkts_recv":        r.get("pkts_recv",       "N/A"),
            })
    log.info("Summary disimpan: %s", path)



def run_single(routing: str, load: str, run_id: int, dry_run: bool = False):
    log.info("")
    log.info("=" * 55)
    log.info("RUN  routing=%-8s  load=%-8s  run=%d",
             routing, load, run_id)
    log.info("=" * 55)

    result_dir = RESULTS_DIR / routing / load / f"run{run_id}"
    result_dir.mkdir(parents=True, exist_ok=True)

    ctrl_proc     = None
    net           = None
    logger_proc   = None
    traffic_procs = []

    try:
        cleanup()

        ctrl_proc = start_controller(routing, result_dir / "controller.log")

        log.info("Tunggu controller bind (5s)...")
        time.sleep(5)

        net = start_mininet()

        log.info("Warmup %ds (LLDP discovery + flow table init)...",
                 WARMUP_SEC)
        _sleep_log(WARMUP_SEC,  "Warmup (LLDP discovery)")

        logger_proc = start_resource_logger(
            ctrl_proc.pid,
            result_dir / "controller_resource.csv",
        )

        if not dry_run:
            log.info("Start background traffic (%s, %ds)...",
                     load, TRAFFIC_SEC)
            traffic_procs = traffic.start(
                net, load, TRAFFIC_SEC,
                result_dir / "traffic_logs",
            )
            log.info("%d flow client berjalan.", len(traffic_procs))
        else:
            log.info("[DRY-RUN] Traffic dilewati.")

        log.info("Steady state %ds...", STEADY_SEC)
        _sleep_log(STEADY_SEC,  "Steady state")

        if load == "heavy":
            log.info("Heavy load stabilization (30s)...")
            time.sleep(30)

        ditg_results = []
        if not dry_run:
            log.info("Start D-ITG probes (%d pasang, %ds)...",
                     len(DITG_PAIRS), DITG_DUR_MS // 1000)
            ditg_results = ditg.run_probes(
                net, DITG_PAIRS, DITG_DUR_MS, result_dir / "ditg"
            )
        else:
            log.info("[DRY-RUN] D-ITG dilewati.")

        if traffic_procs:
            log.info("Menunggu background traffic selesai (max 620s)...")
            deadline = time.time() + 620
            for p in traffic_procs:
                remaining = max(1, int(deadline - time.time()))
                try:
                    p.wait(timeout=remaining)
                except Exception:
                    log.warning("  Traffic proc timeout, terminate paksa.")
                    try:
                        p.terminate()
                    except Exception:
                        pass

        if logger_proc:
            logger_proc.terminate()
            logger_proc.wait()
            log.info("Resource logger dihentikan.")

        save_summary(result_dir, routing, load, run_id, ditg_results)
        log.info("RUN SELESAI ✓  routing=%s  load=%s  run=%d",
                 routing, load, run_id)

    except KeyboardInterrupt:
        log.warning("Dihentikan pengguna (Ctrl+C).")

    except Exception as e:
        log.error("RUN GAGAL: %s", e, exc_info=True)

    finally:
        if logger_proc:
            try:
                logger_proc.terminate()
                logger_proc.wait(timeout=5)
            except Exception:
                pass
        if net:
            try:
                net.stop()
            except Exception:
                pass
        if ctrl_proc:
            try:
                ctrl_proc.terminate()
                ctrl_proc.wait(timeout=10)
            except Exception:
                pass
        cleanup()


def _sleep_log(seconds: int, label: str = "", step: int = 10):
    elapsed = 0
    while elapsed < seconds:
        remaining = seconds - elapsed
        done_pct  = int(elapsed / seconds * 20)
        bar = "█" * done_pct + "░" * (20 - done_pct)
        suffix = f"  {label}" if label else ""
        print(f"\r  [{bar}] {elapsed:3d}/{seconds}s{suffix}",
              end="", flush=True)
        time.sleep(min(step, remaining))
        elapsed += min(step, remaining)
    print(f"\r  [{'█'*20}] {seconds}/{seconds}s  selesai.        ")



def main():
    parser = argparse.ArgumentParser(
        description="Orchestrator eksperimen SDN TOPSIS"
    )
    parser.add_argument("--routing", choices=ROUTING_MODES)
    parser.add_argument("--load",    choices=LOAD_LEVELS)
    parser.add_argument("--runs",    type=int, default=10)
    parser.add_argument("--all",     action="store_true",
                        help="Seluruh matriks 3×3×runs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Uji timing tanpa traffic nyata")
    args = parser.parse_args()

    if args.all:
        combos = list(itertools.product(ROUTING_MODES, LOAD_LEVELS))
        total  = len(combos) * args.runs
        done   = 0
        for routing, load in combos:
            for run_id in range(1, args.runs + 1):
                done += 1
                log.info("\n[%d/%d]", done, total)
                run_single(routing, load, run_id, args.dry_run)
                if done < total:
                    log.info("Jeda 10s...")
                    time.sleep(10)

    elif args.routing and args.load:
        for run_id in range(1, args.runs + 1):
            run_single(args.routing, args.load, run_id, args.dry_run)
            if run_id < args.runs:
                log.info("Jeda 10s...")
                time.sleep(10)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()