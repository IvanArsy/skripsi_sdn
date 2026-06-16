import argparse
import glob
import os
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

ROUTING_ORDER = ["static", "sp", "topsis"]
LOAD_ORDER    = ["light", "medium", "heavy"]

LABELS = {
    "static": "Static",
    "sp":     "Shortest Path",
    "topsis": "TOPSIS",
}
COLORS = {
    "static": "#6c757d",
    "sp":     "#0d6efd",
    "topsis": "#198754",
}

plt.rcParams.update({
    "font.size":      11,
    "axes.titlesize": 12,
    "axes.grid":      True,
    "grid.alpha":     0.3,
    "grid.linestyle": "--",
})


def load_results(results_dir: str) -> pd.DataFrame:
    pattern = os.path.join(results_dir, "*", "*", "run*", "summary.csv")
    files   = glob.glob(pattern)

    if not files:
        raise FileNotFoundError(
            f"Tidak ada summary.csv di {results_dir}\n"
            "Pastikan eksperimen sudah dijalankan."
        )

    print(f"Ditemukan {len(files)} file summary.csv")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception as e:
            print(f"  [WARN] {f}: {e}")

    df = pd.concat(dfs, ignore_index=True)

    for col in ["avg_delay_ms", "avg_jitter_ms", "loss_pct",
                "avg_bitrate_kbps", "pkts_sent", "pkts_recv"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"Total baris: {len(df)}")
    print(f"Routing    : {sorted(df['routing'].unique())}")
    print(f"Load       : {sorted(df['load'].unique())}")
    print(f"Run IDs    : {sorted(df['run_id'].unique())}")
    return df


def compute_averages(df: pd.DataFrame) -> pd.DataFrame:
    metrics = ["avg_delay_ms", "avg_jitter_ms", "loss_pct", "avg_bitrate_kbps"]

    agg = (
        df.groupby(["routing", "load"])[metrics]
        .agg(["mean", "std"])
        .reset_index()
    )
    agg.columns = [
        "_".join(c).strip("_") if c[1] else c[0]
        for c in agg.columns
    ]
    return agg

def _bar_chart(agg, mean_col, std_col, ylabel, title, out_path,
               lower_is_better=True):
    loads    = [l for l in LOAD_ORDER    if l in agg["load"].unique()]
    routings = [r for r in ROUTING_ORDER if r in agg["routing"].unique()]

    x      = np.arange(len(loads))
    n      = len(routings)
    width  = 0.22
    offset = np.linspace(-(n-1)/2, (n-1)/2, n) * width

    fig, ax = plt.subplots(figsize=(7, 4.5))

    for i, routing in enumerate(routings):
        sub = agg[agg["routing"] == routing].set_index("load")

        means = [sub.loc[l, mean_col] if l in sub.index else np.nan
                 for l in loads]
        stds  = [sub.loc[l, std_col]
                 if l in sub.index and not pd.isna(sub.loc[l, std_col])
                 else 0 for l in loads]

        bars = ax.bar(
            x + offset[i], means, width,
            yerr=stds, label=LABELS.get(routing, routing),
            color=COLORS.get(routing, "#555"),
            alpha=0.85, capsize=4,
            error_kw={"elinewidth": 1.2, "ecolor": "#333"},
        )

        for bar, m in zip(bars, means):
            if not np.isnan(m):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() * 1.02,
                        f"{m:.2f}",
                        ha="center", va="bottom", fontsize=8)

    y_top = ax.get_ylim()[1]
    for li, load in enumerate(loads):
        sub = agg[agg["load"] == load].set_index("routing")
        valid = {r: sub.loc[r, mean_col]
                 for r in routings
                 if r in sub.index and not pd.isna(sub.loc[r, mean_col])}
        if not valid:
            continue
        best = min(valid, key=valid.get) if lower_is_better \
               else max(valid, key=valid.get)
        bi   = routings.index(best)
        ax.text(li + offset[bi], y_top * 0.97, "★",
                ha="center", va="top", fontsize=12,
                color=COLORS.get(best, "#333"))

    ax.set_xticks(x)
    ax.set_xticklabels([l.capitalize() for l in loads])
    ax.set_xlabel("Kondisi Beban Jaringan")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper left", framealpha=0.85)
    ax.annotate("★ = nilai terbaik", xy=(0.99, 0.01),
                xycoords="axes fraction", ha="right",
                va="bottom", fontsize=8, color="#666")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  {out_path}")


def plot_combined(agg: pd.DataFrame, out_path: str):
    configs = [
        ("avg_delay_ms_mean",     "avg_delay_ms_std",     "Delay (ms)",      "Rata-rata Delay",       True),
        ("avg_jitter_ms_mean",    "avg_jitter_ms_std",    "Jitter (ms)",     "Rata-rata Jitter",      True),
        ("loss_pct_mean",         "loss_pct_std",         "Packet Loss (%)", "Rata-rata Packet Loss", True),
        ("avg_bitrate_kbps_mean", "avg_bitrate_kbps_std", "Bitrate (Kbps)",  "Rata-rata Bitrate",     False),
    ]

    loads    = [l for l in LOAD_ORDER    if l in agg["load"].unique()]
    routings = [r for r in ROUTING_ORDER if r in agg["routing"].unique()]
    x        = np.arange(len(loads))
    n        = len(routings)
    width    = 0.22
    offset   = np.linspace(-(n-1)/2, (n-1)/2, n) * width

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        "Perbandingan QoS: Static vs Shortest Path vs TOPSIS",
        fontsize=13, fontweight="bold",
    )

    for ax, (mc, sc, ylabel, subtitle, _lib) in zip(axes.flat, configs):
        for i, routing in enumerate(routings):
            sub   = agg[agg["routing"] == routing].set_index("load")
            means = [sub.loc[l, mc] if l in sub.index else np.nan for l in loads]
            stds  = [sub.loc[l, sc]
                     if l in sub.index and not pd.isna(sub.loc[l, sc])
                     else 0 for l in loads]
            ax.bar(x + offset[i], means, width, yerr=stds,
                   label=LABELS.get(routing, routing),
                   color=COLORS.get(routing, "#555"),
                   alpha=0.85, capsize=3,
                   error_kw={"elinewidth": 1.0, "ecolor": "#333"})

        ax.set_xticks(x)
        ax.set_xticklabels([l.capitalize() for l in loads])
        ax.set_ylabel(ylabel)
        ax.set_title(subtitle)
        ax.legend(fontsize=8, loc="upper left")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  {out_path}")


def plot_cpu(results_dir: str, out_path: str):
    pattern = os.path.join(
        results_dir, "*", "*", "run*", "controller_resource.csv"
    )
    files = glob.glob(pattern)
    if not files:
        print("  [WARN] controller_resource.csv tidak ditemukan, grafik CPU dilewati.")
        return

    rows = []
    for f in files:
        parts = Path(f).parts
        try:
            routing = parts[-4]
            load    = parts[-3]
            run_id  = parts[-2]
            df_r    = pd.read_csv(f)
            avg_cpu = pd.to_numeric(df_r["cpu_pct"], errors="coerce").mean()
            avg_mem = pd.to_numeric(df_r["mem_rss_mb"], errors="coerce").mean()
            rows.append({"routing": routing, "load": load,
                         "avg_cpu": avg_cpu, "avg_mem_mb": avg_mem})
        except Exception:
            continue

    if not rows:
        return

    df_cpu = pd.DataFrame(rows)
    agg_cpu = df_cpu.groupby(["routing", "load"])[["avg_cpu", "avg_mem_mb"]]\
                    .mean().reset_index()

    loads    = [l for l in LOAD_ORDER    if l in agg_cpu["load"].unique()]
    routings = [r for r in ROUTING_ORDER if r in agg_cpu["routing"].unique()]
    x        = np.arange(len(loads))
    n        = len(routings)
    width    = 0.22
    offset   = np.linspace(-(n-1)/2, (n-1)/2, n) * width

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.suptitle("Resource Controller: CPU & Memory", fontsize=12)

    for col, ax, label, title in [
        ("avg_cpu",    axes[0], "CPU (%)",  "Rata-rata CPU Controller"),
        ("avg_mem_mb", axes[1], "RAM (MB)", "Rata-rata Memory Controller"),
    ]:
        for i, routing in enumerate(routings):
            sub  = agg_cpu[agg_cpu["routing"] == routing].set_index("load")
            vals = [sub.loc[l, col] if l in sub.index else np.nan for l in loads]
            ax.bar(x + offset[i], vals, width,
                   label=LABELS.get(routing, routing),
                   color=COLORS.get(routing, "#555"), alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels([l.capitalize() for l in loads])
        ax.set_xlabel("Kondisi Beban")
        ax.set_ylabel(label)
        ax.set_title(title)
        ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  {out_path}")


def export_table(agg: pd.DataFrame, out_path: str):
    rows = []
    for routing in ROUTING_ORDER:
        for load in LOAD_ORDER:
            sub = agg[(agg["routing"] == routing) & (agg["load"] == load)]
            if sub.empty:
                continue
            r = sub.iloc[0]

            def fmt(mc, sc, d=3):
                m, s = r.get(mc, np.nan), r.get(sc, np.nan)
                if pd.isna(m):
                    return "N/A"
                return f"{m:.{d}f} ± {s:.{d}f}" if not pd.isna(s) and s > 0 \
                       else f"{m:.{d}f}"

            rows.append({
                "Routing":        LABELS.get(routing, routing),
                "Load":           load.capitalize(),
                "Delay (ms)":     fmt("avg_delay_ms_mean",     "avg_delay_ms_std"),
                "Jitter (ms)":    fmt("avg_jitter_ms_mean",    "avg_jitter_ms_std"),
                "Loss (%)":       fmt("loss_pct_mean",         "loss_pct_std", 4),
                "Bitrate (Kbps)": fmt("avg_bitrate_kbps_mean", "avg_bitrate_kbps_std", 2),
            })

    tbl = pd.DataFrame(rows)
    tbl.to_csv(out_path, index=False)
    print(f"  {out_path}")
    print()
    print(tbl.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="./results")
    parser.add_argument("--out",     default="./figures")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print("=" * 50)
    print("  Analisis Hasil Eksperimen SDN")
    print("=" * 50)

    df  = load_results(args.results)
    agg = compute_averages(df)

    print("\nMembuat grafik...")

    _bar_chart(agg, "avg_delay_ms_mean",     "avg_delay_ms_std",
               "Delay (ms)",      "Rata-rata Delay",
               f"{args.out}/qos_delay.png",   lower_is_better=True)

    _bar_chart(agg, "avg_jitter_ms_mean",    "avg_jitter_ms_std",
               "Jitter (ms)",     "Rata-rata Jitter",
               f"{args.out}/qos_jitter.png",  lower_is_better=True)

    _bar_chart(agg, "loss_pct_mean",         "loss_pct_std",
               "Packet Loss (%)", "Rata-rata Packet Loss",
               f"{args.out}/qos_loss.png",    lower_is_better=True)

    _bar_chart(agg, "avg_bitrate_kbps_mean", "avg_bitrate_kbps_std",
               "Bitrate (Kbps)",  "Rata-rata Bitrate",
               f"{args.out}/qos_bitrate.png", lower_is_better=False)

    plot_combined(agg, f"{args.out}/qos_combined.png")
    plot_cpu(args.results, f"{args.out}/controller_resource.png")

    print("\nEkspor tabel agregat...")
    export_table(agg, f"{args.out}/summary_table.csv")

    print(f"\nSelesai. Output: {args.out}/")


if __name__ == "__main__":
    main()