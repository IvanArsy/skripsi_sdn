import glob
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import pandas as pd
import streamlit as st

# KONFIGURASI

RESULTS_DIR  = Path("./results")
FIGURES_DIR  = Path("./figures")
LIVE_LOG     = Path("./logs/live.log")
ROUTING_MODES = ["static", "sp", "topsis"]
LOAD_LEVELS   = ["light", "medium", "heavy"]

LIVE_LOG.parent.mkdir(parents=True, exist_ok=True)

# PAGE CONFIG

st.set_page_config(
    page_title = "SDN TOPSIS Dashboard",
    page_icon  = "🌐",
    layout     = "wide",
)

st.markdown("""
<style>
[data-testid="stMetricLabel"] > div,
[data-testid="stCaptionContainer"] p,
.stRadio label, .stCheckbox label,
.stSelectbox label, .stMultiSelect label,
.stNumberInput label, .stSlider label,
.stTextArea label {
    color: var(--text-color) !important;
    opacity: 1 !important;
}
 

[data-testid="stTextArea"] textarea {
    opacity: 1 !important;
    color: var(--text-color) !important;
    -webkit-text-fill-color: var(--text-color) !important;
}
[data-testid="stTextArea"] textarea:disabled {
    opacity: 1 !important;
    color: var(--text-color) !important;
    -webkit-text-fill-color: var(--text-color) !important;
}
</style>
""", unsafe_allow_html=True)

# SESSION STATE INIT

if "proc_pid"    not in st.session_state:
    st.session_state.proc_pid    = None
if "proc_pgid"   not in st.session_state:
    st.session_state.proc_pgid   = None
if "running"     not in st.session_state:
    st.session_state.running     = False
if "log_content" not in st.session_state:
    st.session_state.log_content = ""
if "was_running" not in st.session_state:
    st.session_state.was_running = False

# HELPER: CEK PROSES MASIH BERJALAN

def is_running() -> bool:
    pid = st.session_state.proc_pid
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        # Proses sudah selesai — reset state
        st.session_state.proc_pid  = None
        st.session_state.proc_pgid = None
        st.session_state.running   = False
        return False
    except PermissionError:
        # PID ada tapi tidak bisa signal — tetap running
        return True


def read_log_tail(n_lines: int = 60) -> str:
    if not LIVE_LOG.exists():
        return ""
    lines = LIVE_LOG.read_text(errors="replace").splitlines()
    return "\n".join(lines[-n_lines:])


def count_completed_runs() -> dict:
    """Hitung berapa run sudah selesai per skenario."""
    result = {}
    for routing in ROUTING_MODES:
        for load in LOAD_LEVELS:
            key = f"{routing}/{load}"
            pattern = str(RESULTS_DIR / routing / load / "run*/summary.csv")
            done = len(glob.glob(pattern))
            result[key] = done
    return result

# HEADER

st.markdown("""
<h1 style='margin-bottom:0'>SDN TOPSIS Experiment</h1>
<p style='color:#888;margin-top:4px'>
    Implementasi TOPSIS untuk QoS-aware Routing pada SDN
</p>
""", unsafe_allow_html=True)

st.divider()

# STATUS BAR

col_s1, col_s2, col_s3, col_s4 = st.columns(4)

total_summary = len(glob.glob(str(RESULTS_DIR / "*/*/run*/summary.csv")))
total_runs    = total_summary  # 1 summary per run

with col_s1:
    st.metric("Total Run Selesai", total_runs, help="Jumlah file summary.csv")
with col_s2:
    na_count = 0
    if total_runs > 0:
        files = glob.glob(str(RESULTS_DIR / "*/*/run*/summary.csv"))
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_csv(f))
            except Exception:
                pass
        if dfs:
            df_all = pd.concat(dfs, ignore_index=True)
            na_count = df_all["avg_delay_ms"].isna().sum()
    st.metric("Probe N/A", na_count, help="Probe yang gagal (recv_log kosong)")
with col_s3:
    status_txt = "🟢 Berjalan" if is_running() else "⚪ Idle"
    st.metric("Status Orchestrator", status_txt)
with col_s4:
    fig_count = len(glob.glob(str(FIGURES_DIR / "*.png")))
    st.metric("Grafik Tersedia", fig_count)

st.divider()

# TABS

tab_exp, tab_analysis, tab_data = st.tabs([
    "Eksperimen",
    "Analisis & Grafik",
    "Data",
])

# TAB 1: EKSPERIMEN

with tab_exp:

    st.subheader("Konfigurasi Eksperimen")

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])

    with col_f1:
        mode = st.radio(
            "Mode",
            ["Single Skenario", "Semua Skenario (3×3)"],
            horizontal=True,
        )

    with col_f2:
        runs = st.number_input("Jumlah Run", min_value=1, max_value=30,
                               value=10, step=1)

    with col_f3:
        dry_run = st.checkbox("Dry Run", help="Uji timing tanpa traffic nyata")

    with col_f4:
        st.write("")  # spacer

    if mode == "Single Skenario":
        col_r, col_l = st.columns(2)
        with col_r:
            routing = st.selectbox("Routing Mode", ROUTING_MODES,
                                   format_func=lambda x: {
                                       "static": "Static",
                                       "sp":     "Shortest Path",
                                       "topsis": "TOPSIS",
                                   }[x])
        with col_l:
            load = st.selectbox("Load Level", LOAD_LEVELS,
                                format_func=str.capitalize)

    st.divider()

    # Estimasi waktu
    est_per_run  = 17   # menit
    if mode == "Semua Skenario (3×3)":
        total_est = 9 * runs * est_per_run
    else:
        total_est = runs * est_per_run

    hrs  = total_est // 60
    mins = total_est % 60
    st.caption(
        f"Estimasi waktu: **{hrs}j {mins}m** "
        f"({'9 skenario × ' if mode == 'Semua Skenario (3×3)' else ''}"
        f"{runs} run × ~{est_per_run} menit/run)"
    )

    # Tombol kontrol
    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 6])

    with col_btn1:
        start_clicked = st.button(
            "Jalankan",
            type="primary",
            disabled=is_running(),
            use_container_width=True,
        )

    with col_btn2:
        stop_clicked = st.button(
            "Stop",
            disabled=not is_running(),
            use_container_width=True,
        )

    # Handle start
    if start_clicked and not is_running():
        LIVE_LOG.write_text("")  

        cmd = [sys.executable, "orchestrator.py"]

        if mode == "Semua Skenario (3×3)":
            cmd += ["--all", "--runs", str(runs)]
        else:
            cmd += ["--routing", routing, "--load", load,
                    "--runs", str(runs)]

        if dry_run:
            cmd.append("--dry-run")

        try:
            log_fh = open(LIVE_LOG, "w")
            proc = subprocess.Popen(
                cmd,
                stdout  = log_fh,
                stderr  = log_fh,
                bufsize = 1,
                preexec_fn = os.setsid,
            )
            import signal
            st.session_state.proc_pid  = proc.pid
            st.session_state.proc_pgid = os.getpgid(proc.pid)
            st.session_state.running   = True
            st.session_state.log_fh    = log_fh
            st.success(f"Orchestrator dimulai (PID {proc.pid})")
        except Exception as e:
            st.error(f"Gagal menjalankan orchestrator: {e}")
            st.code(f"Command: {' '.join(cmd)}")
        st.rerun()

    # Handle stop
    if stop_clicked and is_running():
        try:
            import signal
            pgid = st.session_state.get("proc_pgid")
            if pgid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(st.session_state.proc_pid, signal.SIGTERM)
        except Exception as e:
            st.warning(f"Stop error: {e}")
        st.session_state.running   = False
        st.session_state.proc_pid  = None
        st.session_state.proc_pgid = None
        st.warning("Orchestrator dihentikan.")
        st.rerun()

    # Live log
    st.subheader("Live Log")

    col_log1, col_log2, col_log3, col_log4 = st.columns([2, 2, 2, 4])
    with col_log1:
        refresh_clicked = st.button("Refresh Log",
                                    use_container_width=True)
    with col_log2:
        if st.button("Bersihkan Log",
                     use_container_width=True,
                     disabled=is_running()):
            LIVE_LOG.write_text("")
            st.rerun()
    with col_log3:
        if is_running():
            st.info("Berjalan — refresh manual")
        else:
            if st.session_state.get("was_running"):
                st.success("Selesai")
                st.session_state.was_running = False

    # Update flag
    if is_running():
        st.session_state.was_running = True

    log_text = LIVE_LOG.read_text(errors="replace") if LIVE_LOG.exists() else ""
    st.text_area(
        label            = "log",
        value            = log_text if log_text else "— belum ada log —",
        height           = 400,
        disabled         = True,
        label_visibility = "collapsed",
    )

    if LIVE_LOG.exists() and LIVE_LOG.stat().st_size > 0:
        with open(LIVE_LOG, "rb") as f:
            st.download_button(
                "⬇ Download Log",
                f,
                file_name="experiment.log",
                mime="text/plain",
            )

    if is_running():
        time.sleep(3)
        st.rerun()

    # Progress per skenario
    st.subheader("Progress per Skenario")
    completed = count_completed_runs()

    rows = []
    for routing_m in ROUTING_MODES:
        row = {"Routing": routing_m.upper()}
        for load_l in LOAD_LEVELS:
            done = completed.get(f"{routing_m}/{load_l}", 0)
            row[load_l.capitalize()] = f"{done}/10"
        rows.append(row)

    df_progress = pd.DataFrame(rows).set_index("Routing")
    st.dataframe(df_progress, use_container_width=True)


# TAB 2: ANALISIS & GRAFIK

with tab_analysis:

    st.subheader("Generate Grafik")

    col_a1, col_a2 = st.columns([2, 8])
    with col_a1:
        if st.button("Jalankan analyze.py",
                     use_container_width=True,
                     disabled=is_running()):
            with st.spinner("Menjalankan analyze.py..."):
                result = subprocess.run(
                    [sys.executable, "analyze.py",
                     "--results", str(RESULTS_DIR),
                     "--out",     str(FIGURES_DIR)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            if result.returncode == 0:
                st.success("Grafik berhasil dibuat.")
            else:
                st.error("analyze.py error:")
                st.code(result.stderr[-2000:])

    with col_a2:
        if FIGURES_DIR.exists():
            png_files = sorted(FIGURES_DIR.glob("*.png"))
            if png_files:
                st.caption(f"{len(png_files)} grafik tersedia di `{FIGURES_DIR}/`")

    st.divider()

    # Tampilkan grafik
    FIGURE_DEFS = [
        ("qos_combined.png",        "QoS Gabungan (Delay, Jitter, Loss, Bitrate)"),
        ("qos_delay.png",           "Delay"),
        ("qos_jitter.png",          "Jitter"),
        ("qos_loss.png",            "Packet Loss"),
        ("qos_bitrate.png",         "Bitrate"),
        ("controller_resource.png", "Resource Controller (CPU & RAM)"),
    ]

    if not FIGURES_DIR.exists() or not any(FIGURES_DIR.glob("*.png")):
        st.info("Belum ada grafik. Klik 'Jalankan analyze.py' di atas.")
    else:
        combined = FIGURES_DIR / "qos_combined.png"
        if combined.exists():
            st.image(str(combined), caption="QoS Gabungan", use_container_width=True)
            st.divider()

        individual = [
            (FIGURES_DIR / fname, caption)
            for fname, caption in FIGURE_DEFS
            if fname != "qos_combined.png"
        ]

        for i in range(0, len(individual), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j < len(individual):
                    fpath, caption = individual[i + j]
                    if fpath.exists():
                        with col:
                            st.image(str(fpath), caption=caption,
                                     use_container_width=True)
                            with open(fpath, "rb") as f:
                                st.download_button(
                                    f"⬇ {caption}",
                                    f,
                                    file_name=fpath.name,
                                    mime="image/png",
                                    key=f"dl_{fpath.name}",
                                )


# TAB 3: DATA

with tab_data:

    st.subheader("Data Hasil Eksperimen")

    files = glob.glob(str(RESULTS_DIR / "*/*/run*/summary.csv"))

    if not files:
        st.info("Belum ada data. Jalankan eksperimen terlebih dahulu.")
    else:
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_csv(f))
            except Exception:
                pass

        df = pd.concat(dfs, ignore_index=True)

        for col in ["avg_delay_ms", "avg_jitter_ms", "loss_pct",
                    "avg_bitrate_kbps"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            f_routing = st.multiselect(
                "Routing", ROUTING_MODES,
                default=ROUTING_MODES,
                format_func=str.upper,
            )
        with col_f2:
            f_load = st.multiselect(
                "Load", LOAD_LEVELS,
                default=LOAD_LEVELS,
                format_func=str.capitalize,
            )
        with col_f3:
            show_na = st.checkbox("Tampilkan baris N/A", value=False)

        df_filtered = df[
            df["routing"].isin(f_routing) &
            df["load"].isin(f_load)
        ]
        if not show_na:
            df_filtered = df_filtered.dropna(subset=["avg_delay_ms"])

        st.caption(f"{len(df_filtered)} baris ditampilkan "
                   f"({df['avg_delay_ms'].isna().sum()} baris N/A disembunyikan)")

        st.dataframe(
            df_filtered.style.format({
                "avg_delay_ms":     "{:.3f}",
                "avg_jitter_ms":    "{:.3f}",
                "loss_pct":         "{:.4f}",
                "avg_bitrate_kbps": "{:.2f}",
            }, na_rep="N/A"),
            use_container_width=True,
            height=400,
        )

        # Tabel agregat
        st.subheader("Rata-rata per Skenario")

        metrics = ["avg_delay_ms", "avg_jitter_ms",
                   "loss_pct", "avg_bitrate_kbps"]

        agg = (
            df_filtered.groupby(["routing", "load"])[metrics]
            .agg(["mean", "std"])
            .round(3)
        )
        st.dataframe(agg, use_container_width=True)

        # Download
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            csv_all = df_filtered.to_csv(index=False).encode()
            st.download_button(
                "Download Data Lengkap (CSV)",
                csv_all,
                file_name="results_all.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_d2:
            agg_csv = agg.to_csv().encode()
            st.download_button(
                "Download Tabel Agregat (CSV)",
                agg_csv,
                file_name="results_aggregated.csv",
                mime="text/csv",
                use_container_width=True,
            )