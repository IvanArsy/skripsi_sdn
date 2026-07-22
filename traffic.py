"""
traffic.py
==========
Adaptasi dari generate_traffic.sh ke Python Mininet API.

Menggunakan dataset, bandwidth profile, dan flow class
yang IDENTIK dengan generate_traffic.sh — hanya mekanisme
eksekusinya yang berubah dari 'source eksekusi.txt di CLI
Mininet' menjadi host.cmd() + host.popen().

Perbedaan mekanisme:
    LAMA: generate_traffic.sh → eksekusi_{mode}.txt
          → Mininet CLI: source eksekusi_medium.txt
    BARU: traffic.start(net, load, ...) langsung memanggil
          host.cmd() / host.popen() pada objek Mininet

Kenapa host.popen() lebih baik dari source .txt:
    - Tidak butuh file perantara
    - Return Popen objects → bisa wait() di orchestrator
    - Tidak bergantung pada Mininet CLI yang interaktif
    - Error tertangkap langsung, bukan hilang di .txt file

Urutan eksekusi (sama dengan generate_traffic.sh):
    1. Start iperf3 server daemon di semua 100 host
    2. sleep 5s
    3. Start client per flow dengan random delay 1-3s
    4. Batch delay setiap 6 flow
    5. Return list Popen client — caller memanggil .wait()
"""

import logging
import random
import time
from pathlib import Path
from typing import List

log = logging.getLogger("traffic")

# ──────────────────────────────────────────────────────────
# DATASET — identik dengan generate_traffic.sh
# Format: (src_host, dst_ip, duration_sec, protocol, flow_class)
# ──────────────────────────────────────────────────────────

DATASET = [
    # ELEPHANT FLOWS
    ("h1",  "10.0.0.91", 600, "UDP", "ELEPHANT"),
    ("h23", "10.0.0.57", 600, "UDP", "ELEPHANT"),
    ("h81", "10.0.0.11", 600, "UDP", "ELEPHANT"),
    ("h63", "10.0.0.35", 600, "UDP", "ELEPHANT"),
    ("h4",  "10.0.0.94", 600, "TCP", "ELEPHANT"),
    ("h84", "10.0.0.14", 600, "TCP", "ELEPHANT"),

    # MEDIUM FLOWS
    ("h2",  "10.0.0.72", 600, "TCP", "MEDIUM"),
    ("h21", "10.0.0.97", 600, "UDP", "MEDIUM"),
    ("h24", "10.0.0.98", 600, "TCP", "MEDIUM"),
    ("h82", "10.0.0.32", 600, "TCP", "MEDIUM"),
    ("h61", "10.0.0.15", 600, "UDP", "MEDIUM"),
    ("h64", "10.0.0.16", 600, "TCP", "MEDIUM"),
    ("h27", "10.0.0.83", 600, "UDP", "MEDIUM"),
    ("h34", "10.0.0.64", 600, "TCP", "MEDIUM"),
    ("h85", "10.0.0.22", 600, "UDP", "MEDIUM"),
    ("h74", "10.0.0.41", 600, "TCP", "MEDIUM"),

    # MICE FLOWS
    ("h3",  "10.0.0.53", 600, "UDP", "MICE"),
    ("h22", "10.0.0.76", 600, "TCP", "MICE"),
    ("h83", "10.0.0.51", 600, "UDP", "MICE"),
    ("h62", "10.0.0.55", 600, "TCP", "MICE"),
    ("h9",  "10.0.0.44", 600, "TCP", "MICE"),
    ("h10", "10.0.0.31", 600, "UDP", "MICE"),
    ("h35", "10.0.0.87", 600, "TCP", "MICE"),
    ("h52", "10.0.0.13", 600, "UDP", "MICE"),
    ("h37", "10.0.0.95", 600, "TCP", "MICE"),
    ("h86", "10.0.0.24", 600, "UDP", "MICE"),
    ("h11", "10.0.0.46", 600, "TCP", "MICE"),
    ("h12", "10.0.0.49", 600, "UDP", "MICE"),
    ("h13", "10.0.0.28", 600, "TCP", "MICE"),
    ("h14", "10.0.0.47", 600, "UDP", "MICE"),
    ("h73", "10.0.0.96", 600, "TCP", "MICE"),
    ("h75", "10.0.0.89", 600, "UDP", "MICE"),
]

# BANDWIDTH PROFILE — identik dengan generate_traffic.sh

BW_PROFILES = {
    "light":  {"ELEPHANT": "2M",  "MEDIUM": "800K", "MICE": "200K"},
    "medium": {"ELEPHANT": "4M",  "MEDIUM": "2M",   "MICE": "400K"},
    "heavy":  {"ELEPHANT": "7M",  "MEDIUM": "3M",   "MICE": "700K"},
}


def start(net, load: str, duration_sec: int, log_dir: Path) -> List:
    """
    Jalankan semua background traffic flows.

    Alur (sama dengan source eksekusi_{load}.txt):
        1. Start iperf3 server daemon di semua host
        2. Sleep 5s
        3. Start client tiap flow dengan random delay + batch delay
        4. Return list Popen client

    Return: list of Popen — orchestrator memanggil .wait() setelah selesai.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    bw_map = BW_PROFILES.get(load, BW_PROFILES["medium"])

    # ── 1. Start iperf3 server daemon di semua host ────────
    # host.cmd() blocking tapi -D (daemon) membuat iperf3
    # langsung fork ke background — cmd() kembali cepat.
    # Tidak perlu Popen karena server daemon tidak kita wait().
    log.info("  Menjalankan iperf3 server di semua host...")
    all_hosts = [f"h{i}" for i in range(1, 101)]
    for h_name in all_hosts:
        h = net.get(h_name)
        if h:
            h.cmd("iperf3 -s -D")

    # ── 2. Sleep 5s (server binding) ──────────────────────
    log.info("  Menunggu server siap (5s)...")
    time.sleep(5)

    # ── 3. Start client per flow ──────────────────────────
    log.info("  Menjalankan %d flows (%s)...", len(DATASET), load)
    client_procs = []
    counter = 0

    for src_name, dst_ip, dur, proto, flow_class in DATASET:
        src = net.get(src_name)
        if src is None:
            log.warning("    Host %s tidak ditemukan, dilewati.", src_name)
            continue

        bw = bw_map[flow_class]

        # Random start delay 1-3s (identik dengan generate_traffic.sh)
        delay = random.randint(1, 3)
        time.sleep(delay)

        # Nama file log unik per flow
        flow_name = f"{src_name}_{flow_class}_{proto}"
        log_file  = log_dir / f"{flow_name}.json"

        # Bangun command iperf3
        if proto == "TCP":
            cmd = [
                "iperf3",
                "-c", dst_ip,
                "-t", str(dur),
                "-i", "30",
                "--json",
                "--logfile", str(log_file),
            ]
        else:  # UDP
            cmd = [
                "iperf3",
                "-c", dst_ip,
                "-u",
                "-b", bw,
                "-t", str(dur),
                "-i", "30",
                "--json",
                "--logfile", str(log_file),
            ]

        proc = src.popen(cmd)
        client_procs.append(proc)
        counter += 1

        log.debug("    [%d] %s → %s  %s  %s  bw=%s",
                  counter, src_name, dst_ip, proto, flow_class, bw)

        # Batch delay setiap 6 flow (identik dengan generate_traffic.sh)
        if counter % 6 == 0:
            log.info("    Batch %d selesai, sleep 2s...", counter // 6)
            time.sleep(2)

    log.info("  %d flow client berjalan.", len(client_procs))
    return client_procs


def stop(procs: List):
    """
    Terminate semua client proc.
    Dipanggil saat cleanup darurat — kondisi normal
    procs sudah selesai sendiri (timeout iperf3 600s).
    """
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass