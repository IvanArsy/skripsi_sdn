#!/bin/bash
OUT="eksekusi_mininet.txt"
rm -f $OUT log_dataset_*.txt

echo "Membangun instruksi dari Dataset (Skala 100 Host, 20 Flow, Durasi 10 Menit)..."

# Menyalakan 50 Server Penerima
echo "sh echo '>>> Menyalakan Server Standby di Sisi Kanan...'" >> $OUT
for i in {11..20} {31..40} {51..60} {71..80} {91..100}; do 
    echo "h${i} iperf3 -s -D" >> $OUT
done
echo "sh sleep 5" >> $OUT

# 2. DATASET TABEL INSTRUKSI

DATASET=(
    # s1
    "h1 10.0.0.91 600 TCP 3M"    # s30
    "h2 10.0.0.72 600 UDP 5M"    # s24 
    "h3 10.0.0.53 600 TCP 2M"    # s18
    "h4 10.0.0.94 600 UDP 1.5M"  # s30

    # s25
    "h81 10.0.0.11 600 TCP 3M"   # s6
    "h82 10.0.0.32 600 UDP 5M"   # s12
    "h83 10.0.0.51 600 TCP 2M"   # s18
    "h84 10.0.0.14 600 UDP 1.5M" # s6

    # s13
    "h41 10.0.0.33 600 TCP 3.5M" # s12
    "h42 10.0.0.74 600 UDP 6M"   # 24
    "h43 10.0.0.95 600 TCP 1.5M" # s30
    "h44 10.0.0.36 600 UDP 3M"   # s12

    # s19
    "h61 10.0.0.15 600 TCP 3.5M" # s6
    "h62 10.0.0.55 600 UDP 6M"   # s18
    "h63 10.0.0.35 600 TCP 1.5M" # s12
    "h64 10.0.0.16 600 UDP 3M"   # s6

    # s7
    "h21 10.0.0.97 600 TCP 3.5M" # s30
    "h22 10.0.0.76 600 UDP 6M"   # s24
    "h23 10.0.0.57 600 TCP 1.5M" # s18
    "h24 10.0.0.98 600 UDP 3M"   # s30
)

# 3. PROSES AKTIVASI DATASET

for baris_data in "${DATASET[@]}"; do
    read src dst time type bw <<< $baris_data
    
    if [ "$type" == "TCP" ]; then
        echo "$src iperf3 -c $dst -b $bw -i 60 -t $time > log_dataset_${src}_TCP.txt &" >> $OUT
    elif [ "$type" == "UDP" ]; then
        echo "$src iperf3 -c $dst -u -b $bw -i 60 -t $time > log_dataset_${src}_UDP.txt &" >> $OUT
    fi
done

echo "sh echo '>>> 20 Flow Dataset sedang dieksekusi selama 10 Menit (600 detik)...'" >> $OUT
echo "Selesai."