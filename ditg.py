import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

log = logging.getLogger("ditg")

ITGSEND = "/home/notes/D-ITG-2.8.1-r1023/bin/ITGSend"
ITGRECV = "/home/notes/D-ITG-2.8.1-r1023/bin/ITGRecv"
ITGDEC  = "/home/notes/D-ITG-2.8.1-r1023/bin/ITGDec"

LOG_BASE_DIR = "/home/notes/skripsi_sdn"

PKT_SIZE   = 512    
PKT_RATE   = 100    
RECV_WAIT  = 5       
FLUSH_WAIT = 8       


def run_probes(
    net,
    pairs: List[Tuple[str, str]],
    duration_ms: int,
    result_dir: Path,
) -> List[Dict]:

    result_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for i, (src_name, dst_name) in enumerate(pairs):
        log.info("  Probe %d/%d: %s → %s",
                 i + 1, len(pairs), src_name, dst_name)

        r = _run_one_probe(
            net, src_name, dst_name,
            duration_ms, result_dir, probe_idx=i + 1,
        )
        results.append(r)

        if i < len(pairs) - 1:
            log.info("  Jeda 15s antar probe...")
            time.sleep(15)

    return results


def _run_one_probe(
    net,
    src_name: str,
    dst_name: str,
    duration_ms: int,
    result_dir: Path,
    probe_idx: int,
) -> Dict:

    base_result = {
        "src": src_name, "dst": dst_name,
        "avg_delay_ms": "N/A", "avg_jitter_ms": "N/A",
        "loss_pct": "N/A", "avg_bitrate_kbps": "N/A",
        "pkts_sent": "N/A", "pkts_recv": "N/A",
    }

    src = net.get(src_name)
    dst = net.get(dst_name)

    if src is None or dst is None:
        log.warning("    Host tidak ditemukan: %s / %s", src_name, dst_name)
        return base_result

    dst_ip = dst.IP()

    recv_log   = f"{LOG_BASE_DIR}/recv_p{probe_idx}.bin"
    decode_out = result_dir / f"ditg_probe{probe_idx}_{src_name}_{dst_name}.txt"

    recv_proc = None
    send_proc = None

    try:
        Path(recv_log).unlink(missing_ok=True)

        recv_proc = dst.popen([ITGRECV, "-l", recv_log])
        log.debug("    ITGRecv started di %s", dst_name)

        time.sleep(10)
        
        send_proc = src.popen([
            ITGSEND,
            "-a", dst_ip,
            "-T", "UDP",
            "-C", str(PKT_RATE),
            "-c", str(PKT_SIZE),
            "-t", str(duration_ms),
            "-x", recv_log,         
        ])
        log.debug("    ITGSend started di %s (%ds)", src_name, duration_ms // 1000)

        ret = send_proc.wait()
        if ret != 0:
            log.warning("    ITGSend exit code %d", ret)

        log.debug("    Tunggu ITGRecv flush (%ds)...", FLUSH_WAIT)
        time.sleep(FLUSH_WAIT)

        recv_proc.terminate()
        try:
            recv_proc.wait(timeout=5)
        except Exception:
            pass

        recv_path = Path(recv_log)
        if not recv_path.exists() or recv_path.stat().st_size == 0:
            log.error("    recv_log tidak ada atau kosong: %s", recv_log)
            log.error("    Pastikan ITGRecv berhasil menerima paket dari ITGSend")
            return base_result

        log.debug("    recv_log: %d bytes", recv_path.stat().st_size)

        with open(decode_out, "w") as fout:
            subprocess.run(
                [ITGDEC, recv_log],
                stdout = fout,
                stderr = fout,
                timeout = 30,
            )
        log.debug("    ITGDec selesai → %s", decode_out.name)

        import shutil
        shutil.copy2(recv_log, result_dir / f"recv_p{probe_idx}.bin")

        result = _parse_itgdec(decode_out, src_name, dst_name)

        log.info("    delay=%s ms  jitter=%s ms  loss=%s%%  bitrate=%s Kbps",
                 result["avg_delay_ms"], result["avg_jitter_ms"],
                 result["loss_pct"], result["avg_bitrate_kbps"])

        return result

    except Exception as e:
        log.error("    Probe gagal: %s", e, exc_info=True)
        for p in [send_proc, recv_proc]:
            if p is not None:
                try:
                    p.terminate()
                    p.wait(timeout=3)
                except Exception:
                    pass
        return base_result


def _parse_itgdec(decode_file: Path, src: str, dst: str) -> Dict:
    result = {
        "src": src, "dst": dst,
        "avg_delay_ms":     "N/A",
        "avg_jitter_ms":    "N/A",
        "loss_pct":         "N/A",
        "avg_bitrate_kbps": "N/A",
        "pkts_sent":        "N/A",
        "pkts_recv":        "N/A",
    }

    if not decode_file.exists():
        log.warning("    File decode tidak ditemukan: %s", decode_file)
        return result

    text = decode_file.read_text(errors="replace")

    m = re.search(r"Average delay\s*=\s*([\d.]+)\s*s", text, re.IGNORECASE)
    if m:
        result["avg_delay_ms"] = str(round(float(m.group(1)) * 1000, 4))

    m = re.search(r"Average jitter\s*=\s*([\d.]+)\s*s", text, re.IGNORECASE)
    if m:
        result["avg_jitter_ms"] = str(round(float(m.group(1)) * 1000, 4))

    m = re.search(
        r"Packets dropped\s*=\s*(\d+)\s*\(([\d.]+)\s*%\)",
        text, re.IGNORECASE,
    )
    if m:
        result["loss_pct"] = m.group(2)

    m = re.search(r"Average bitrate\s*=\s*([\d.]+)\s*Kbit", text, re.IGNORECASE)
    if m:
        result["avg_bitrate_kbps"] = m.group(1)

    m = re.search(r"Total packets\s*=\s*(\d+)", text, re.IGNORECASE)
    pkts_recv = int(m.group(1)) if m else None
    if pkts_recv is not None:
        result["pkts_recv"] = str(pkts_recv)

    m = re.search(r"Packets dropped\s*=\s*(\d+)", text, re.IGNORECASE)
    dropped = int(m.group(1)) if m else 0
    if pkts_recv is not None:
        result["pkts_sent"] = str(pkts_recv + dropped)

    return result