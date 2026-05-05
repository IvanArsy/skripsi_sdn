#!/bin/bash
OUT="eksekusi_mininet.txt"
rm -f $OUT log_dataset_*.txt

echo "Membangun instruksi dari Dataset (Skala 100 Host, 20 Flow, Durasi 15 Menit)..."

# Menyalakan 50 Server Penerima
echo "sh echo '>>> Menyalakan Server Standby di Sisi Kanan...'" >> $OUT
for i in {11..20} {31..40} {51..60} {71..80} {91..100}; do 
    echo "h${i} iperf3 -s -D" >> $OUT
done
echo "sh sleep 5" >> $OUT

# 2. DATASET TABEL INSTRUKSI

DATASET=(
    # --- Alur dari Switch s1 menuju s6 ---
    "h1 10.0.0.11 900 TCP 0"        # Flow 1: Non-delay-sensitive (Transfer File)
    "h2 10.0.0.12 900 UDP 10M"      # Flow 2: Delay-sensitive (Video)
    "h3 10.0.0.13 900 TCP 0"        # Flow 3: Non-delay-sensitive 
    "h4 10.0.0.14 900 UDP 1M"       # Flow 4: Critical (Monitoring kecil)

    # --- Alur dari Switch s7 menuju s12 ---
    "h21 10.0.0.31 900 TCP 0"       # Flow 5: Non-delay-sensitive 
    "h22 10.0.0.32 900 UDP 15M"     # Flow 6: Delay-sensitive (Gaming)
    "h23 10.0.0.33 900 TCP 0"       # Flow 7: Non-delay-sensitive
    "h24 10.0.0.34 900 UDP 5M"      # Flow 8: Delay-sensitive

    # --- Alur dari Switch s13 menuju s18 ---
    "h41 10.0.0.51 900 TCP 0"       # Flow 9: Non-delay-sensitive
    "h42 10.0.0.52 900 UDP 10M"     # Flow 10: Delay-sensitive
    "h43 10.0.0.53 900 TCP 0"       # Flow 11: Non-delay-sensitive
    "h44 10.0.0.54 900 UDP 1M"      # Flow 12: Critical (Monitoring kecil)

    # --- Alur dari Switch s19 menuju s24 ---
    "h61 10.0.0.71 900 TCP 0"       # Flow 13: Non-delay-sensitive
    "h62 10.0.0.72 900 UDP 15M"     # Flow 14: Delay-sensitive
    "h63 10.0.0.73 900 TCP 0"       # Flow 15: Non-delay-sensitive
    "h64 10.0.0.74 900 UDP 10M"     # Flow 16: Delay-sensitive

    # --- Alur dari Switch s25 menuju s30 ---
    "h81 10.0.0.91 900 TCP 0"       # Flow 17: Non-delay-sensitive
    "h82 10.0.0.92 900 UDP 5M"      # Flow 18: Delay-sensitive
    "h83 10.0.0.93 900 TCP 0"       # Flow 19: Non-delay-sensitive
    "h84 10.0.0.94 900 UDP 1M"      # Flow 20: Critical (Monitoring kecil)
)

# 3. PROSES AKTIVASI DATASET

for baris_data in "${DATASET[@]}"; do
    read src dst time type bw <<< $baris_data
    
    if [ "$type" == "TCP" ]; then
        echo "$src iperf3 -c $dst -i 60 -t $time > log_dataset_${src}_TCP.txt &" >> $OUT
    elif [ "$type" == "UDP" ]; then
        echo "$src iperf3 -c $dst -u -b $bw -i 60 -t $time > log_dataset_${src}_UDP.txt &" >> $OUT
    fi
done

echo "sh echo '>>> 20 Flow Dataset sedang dieksekusi selama 15 Menit (900 detik)...'" >> $OUT
echo "Selesai."