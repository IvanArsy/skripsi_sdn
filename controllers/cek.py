import pandas as pd, ast

static = pd.read_csv("STATIC_controller_log.csv")
sp = pd.read_csv("SHORTEST_PATH_controller_log.csv")

probes = [("10.0.0.6", "10.0.0.56"), ("10.0.0.16", "10.0.0.66"), ("10.0.0.46", "10.0.0.92")]

for src, dst in probes:
    s_path = static[(static.src_ip == src) & (static.dst_ip == dst)]["selected_path"]
    d_path = sp[(sp.src_ip == src) & (sp.dst_ip == dst)]["selected_path"]
    s_val = s_path.iloc[0] if len(s_path) else "TIDAK DITEMUKAN"
    d_val = d_path.iloc[0] if len(d_path) else "TIDAK DITEMUKAN"
    sama = "SAMA" if s_val == d_val else "BEDA"
    print(f"{src}->{dst}: Static={s_val} | SP={d_val} -> {sama}")

print("Jumlah baris static:", len(static))
print("Jumlah baris sp:", len(sp))
print("Jumlah unique (src,dst) di static:", static[["src_ip","dst_ip"]].drop_duplicates().shape[0])
print("Jumlah unique (src,dst) di sp:", sp[["src_ip","dst_ip"]].drop_duplicates().shape[0])

# cek spesifik: apakah IP h16/h46/h6/h56/h66/h92 pernah muncul SAMA SEKALI
target_hosts = ["6", "56", "16", "66", "46", "92"]
for h in target_hosts:
    ip = f"10.0.0.{h}"
    in_static = ((static.src_ip == ip) | (static.dst_ip == ip)).sum()
    in_sp = ((sp.src_ip == ip) | (sp.dst_ip == ip)).sum()
    print(f"h{h} ({ip}): muncul {in_static}x di static, {in_sp}x di sp")
print(static["timestamp"].min(), "-", static["timestamp"].max())
print(sp["timestamp"].min(), "-", sp["timestamp"].max())