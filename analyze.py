import argparse, glob, os, warnings
from pathlib import Path
 
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
 
warnings.filterwarnings("ignore")
 
ROUTING_ORDER = ["static", "sp", "topsis"]
LOAD_ORDER    = ["light", "medium", "heavy"]
 
LABELS = {"static": "Static", "sp": "Delay-based", "topsis": "TOPSIS"}
COLORS = {"static": "#8C9BAB", "sp": "#4A7BBF", "topsis": "#3A9E6F"}
HATCH  = {"static": "",        "sp": "///",       "topsis": "xxx"}
 
plt.rcParams.update({
    "font.family":       "serif",
    "font.serif":        ["Times New Roman", "DejaVu Serif", "Georgia"],
    "font.size":         10,
    "axes.titlesize":    11,
    "axes.labelsize":    10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   9,
    "axes.grid":         True,
    "grid.alpha":        0.25,
    "grid.linestyle":    "--",
    "grid.linewidth":    0.6,
    "axes.linewidth":    0.8,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})
 
 
# Data
def load_results(results_dir):
    files = glob.glob(os.path.join(results_dir, "*", "*", "run*", "summary.csv"))
    if not files:
        raise FileNotFoundError(f"Tidak ada summary.csv di {results_dir}")
    print(f"Ditemukan {len(files)} file summary.csv")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception as e:
            print(f"  [WARN] {f}: {e}")
    df = pd.concat(dfs, ignore_index=True)
    for col in ["avg_delay_ms","avg_jitter_ms","loss_pct","avg_bitrate_kbps"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"Total baris: {len(df)}")
    return df
 
 
def compute_averages(df):
    metrics = ["avg_delay_ms","avg_jitter_ms","loss_pct","avg_bitrate_kbps"]
    agg = df.groupby(["routing","load"])[metrics].agg(["mean","std"]).reset_index()
    agg.columns = ["_".join(c).strip("_") if c[1] else c[0] for c in agg.columns]
    return agg
 
 
# Panel
def _legend_patches(routings):
    return [
        mpatches.Patch(facecolor=COLORS[r], hatch=HATCH[r],
                       edgecolor="#555", linewidth=0.4, label=LABELS[r])
        for r in routings
    ]
 
 
def _draw_panel(ax, agg, mean_col, ylabel, title, show_xlabel=True):
    loads    = [l for l in LOAD_ORDER    if l in agg["load"].unique()]
    routings = [r for r in ROUTING_ORDER if r in agg["routing"].unique()]
    x        = np.arange(len(loads))
    n        = len(routings)
    width    = 0.24
    offsets  = np.linspace(-(n-1)/2, (n-1)/2, n) * width
 
    for i, routing in enumerate(routings):
        sub   = agg[agg["routing"] == routing].set_index("load")
        means = [sub.loc[l, mean_col] if l in sub.index else np.nan for l in loads]
 
        bars = ax.bar(
            x + offsets[i], means, width,
            label=LABELS.get(routing, routing),
            color=COLORS.get(routing, "#888"),
            hatch=HATCH.get(routing, ""),
            alpha=0.90,
            linewidth=0.6,
            edgecolor="white",
        )
 
        for bar, m in zip(bars, means):
            if not np.isnan(m):
                ax._pending_labels = getattr(ax, "_pending_labels", [])
                ax._pending_labels.append((bar, m))
 
    current_max = agg[mean_col].max()
    ax.set_ylim(0, current_max * 1.30)
 
    for bar, m in getattr(ax, "_pending_labels", []):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + current_max * 0.02,
            f"{m:.2f}",
            ha="center", va="bottom", fontsize=7.5, color="#333",
        )
    ax._pending_labels = []
 
    ax.set_xticks(x)
    ax.set_xticklabels(["Light", "Medium", "Heavy"])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold", pad=8)
    if show_xlabel:
        ax.set_xlabel("Network Load Condition")
    ax.yaxis.set_tick_params(length=3)
    ax.xaxis.set_tick_params(length=3)
 
 
# Grafik individual
def plot_single(agg, mean_col, ylabel, title, out_path):
    fig, ax = plt.subplots(figsize=(6.5, 4.8))
    _draw_panel(ax, agg, mean_col, ylabel, title, show_xlabel=True)
 
    routings = [r for r in ROUTING_ORDER if r in agg["routing"].unique()]
    # Legend di dalam panel, pojok kanan atas — jauh dari bar (bar tumbuh dari kiri)
    ax.legend(handles=_legend_patches(routings),
              loc="upper right", framealpha=0.9, edgecolor="#ccc",
              borderpad=0.6, handlelength=1.4, fontsize=9)
 
    fig.tight_layout(pad=1.8)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Tersimpan: {out_path}")
 
 
# Grafik 2×2 combined
def plot_combined(agg, out_path):
    configs = [
        ("avg_delay_ms_mean",     "Delay (ms)",        "End-to-End Delay"),
        ("avg_jitter_ms_mean",    "Jitter (ms)",       "Jitter"),
        ("loss_pct_mean",         "Packet Loss (%)",   "Packet Loss"),
        ("avg_bitrate_kbps_mean", "Throughput (Kbps)", "Throughput"),
    ]
 
    # Ruang bawah untuk legend
    fig = plt.figure(figsize=(12, 9.5))
    fig.suptitle(
        "QoS Comparison: Static vs Delay-based vs TOPSIS Routing",
        fontsize=13, fontweight="bold", y=0.97,
    )
 
    gs = GridSpec(2, 2, figure=fig,
                  hspace=0.45, wspace=0.33,
                  top=0.91, bottom=0.12)
 
    for idx, (mc, ylabel, subtitle) in enumerate(configs):
        ax = fig.add_subplot(gs[idx // 2, idx % 2])
        _draw_panel(ax, agg, mc, ylabel, subtitle, show_xlabel=(idx >= 2))
 
    # Legend bersama — di bawah panel, di atas batas figure
    routings = [r for r in ROUTING_ORDER if r in agg["routing"].unique()]
    fig.legend(
        handles=_legend_patches(routings),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=len(routings),
        framealpha=0.9, edgecolor="#ccc",
        fontsize=10, borderpad=0.7, handlelength=1.8,
        title="Routing Method", title_fontsize=10,
    )
 
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Tersimpan: {out_path}")
 
 
# CPU/Memory
def plot_cpu(results_dir, out_path):
    files = glob.glob(os.path.join(results_dir, "*","*","run*","controller_resource.csv"))
    if not files:
        print("  [INFO] controller_resource.csv tidak ditemukan — dilewati.")
        return
 
    rows = []
    for f in files:
        parts = Path(f).parts
        try:
            df_r = pd.read_csv(f)
            rows.append({
                "routing": parts[-4], "load": parts[-3],
                "avg_cpu": pd.to_numeric(df_r["cpu_pct"],    errors="coerce").mean(),
                "avg_mem": pd.to_numeric(df_r["mem_rss_mb"], errors="coerce").mean(),
            })
        except Exception:
            continue
    if not rows:
        return
    
    df_summary = pd.DataFrame(rows)
    summary = (
        df_summary
        .groupby(["routing", "load"])
        .agg({
            "avg_cpu": ["mean", "std"],
            "avg_mem": ["mean", "std"],
        })
        .round(2)
    )

    out_dir = Path(out_path).parent

    summary.to_csv(
        out_dir / "controller_resource_summary.csv",
        index=True
    )
 
    agg_cpu  = pd.DataFrame(rows).groupby(["routing","load"])[["avg_cpu","avg_mem"]].mean().reset_index()
    loads    = [l for l in LOAD_ORDER    if l in agg_cpu["load"].unique()]
    routings = [r for r in ROUTING_ORDER if r in agg_cpu["routing"].unique()]
    x        = np.arange(len(loads))
    n        = len(routings)
    width    = 0.24
    offsets  = np.linspace(-(n-1)/2, (n-1)/2, n) * width
 
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    fig.suptitle("SDN Controller Resource Utilization", fontsize=12, fontweight="bold")
 
    for col, ax, label, title in [
        ("avg_cpu", axes[0], "CPU Usage (%)",    "CPU Utilization"),
        ("avg_mem", axes[1], "Memory Usage (MB)","Memory Utilization"),
    ]:
        for i, routing in enumerate(routings):
            sub  = agg_cpu[agg_cpu["routing"] == routing].set_index("load")
            vals = [sub.loc[l, col] if l in sub.index else np.nan for l in loads]
            ax.bar(x + offsets[i], vals, width,
                   label=LABELS.get(routing, routing),
                   color=COLORS.get(routing, "#888"),
                   hatch=HATCH.get(routing, ""),
                   alpha=0.90, linewidth=0.6, edgecolor="white")
        ax.set_xticks(x); ax.set_xticklabels(["Light","Medium","Heavy"])
        ax.set_xlabel("Network Load Condition")
        ax.set_ylabel(label); ax.set_title(title, fontweight="bold")
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
 
    fig.legend(handles=_legend_patches(routings),
               loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.04),
               framealpha=0.9, fontsize=9, edgecolor="#ccc")
    fig.tight_layout(pad=1.5)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Tersimpan: {out_path}")
 
 
# Tabel
def export_table(agg, out_path):
    rows = []
    for routing in ROUTING_ORDER:
        for load in LOAD_ORDER:
            sub = agg[(agg["routing"] == routing) & (agg["load"] == load)]
            if sub.empty: continue
            r = sub.iloc[0]
            def fmt(mc, sc, d=2):
                m, s = r.get(mc, np.nan), r.get(sc, np.nan)
                if pd.isna(m): return "N/A"
                return f"{m:.{d}f} ± {s:.{d}f}" if not pd.isna(s) and s > 0 else f"{m:.{d}f}"
            rows.append({
                "Routing Method":    LABELS.get(routing, routing),
                "Load":              load.capitalize(),
                "Delay (ms)":        fmt("avg_delay_ms_mean",     "avg_delay_ms_std"),
                "Jitter (ms)":       fmt("avg_jitter_ms_mean",    "avg_jitter_ms_std"),
                "Packet Loss (%)":   fmt("loss_pct_mean",         "loss_pct_std", 3),
                "Throughput (Kbps)": fmt("avg_bitrate_kbps_mean", "avg_bitrate_kbps_std", 1),
            })
    tbl = pd.DataFrame(rows)
    tbl.to_csv(out_path, index=False)
    print(f"  Tersimpan: {out_path}\n")
    print(tbl.to_string(index=False))
    return tbl
 
 
# Main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="./results")
    parser.add_argument("--out",     default="./figures")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
 
    print("=" * 55)
    print("  Analisis QoS SDN — Format Skripsi")
    print("=" * 55)
 
    df  = load_results(args.results)
    agg = compute_averages(df)
 
    print("\nMembuat grafik individual …")
    plot_single(agg, "avg_delay_ms_mean",     "End-to-End Delay (ms)", "End-to-End Delay",    f"{args.out}/qos_delay.png")
    plot_single(agg, "avg_jitter_ms_mean",    "Jitter (ms)",           "Jitter",              f"{args.out}/qos_jitter.png")
    plot_single(agg, "loss_pct_mean",         "Packet Loss (%)",       "Packet Loss",         f"{args.out}/qos_loss.png")
    plot_single(agg, "avg_bitrate_kbps_mean", "Throughput (Kbps)",     "Throughput",          f"{args.out}/qos_throughput.png")
 
    print("\nMembuat grafik gabungan …")
    plot_combined(agg, f"{args.out}/qos_combined.png")
 
    print("\nMembuat grafik resource controller …")
    plot_cpu(args.results, f"{args.out}/controller_resource.png")
 
    print("\nEkspor tabel …")
    export_table(agg, f"{args.out}/summary_table.csv")
 
    print(f"\n✓ Selesai. Output di: {args.out}/")
 
 
if __name__ == "__main__":
    main()