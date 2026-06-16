#!/bin/bash

# MODE:
# - light
# - medium
# - heavy


if [ $# -lt 2 ]; then
    echo "Penggunaan:"
    echo "./generate_traffic.sh [light|medium|heavy] [folder_log]"
    echo ""
    echo "Contoh:"
    echo "./generate_traffic.sh medium result/topsis/run1"
    exit 1
fi

MODE=$1
TARGET_DIR=$2

mkdir -p "$TARGET_DIR"

ABS_DIR=$(realpath "$TARGET_DIR")

OUT="eksekusi_${MODE}.txt"

rm -f "$OUT"
rm -f "$ABS_DIR"/*.json


if [[ "$MODE" != "light" && "$MODE" != "medium" && "$MODE" != "heavy" ]]; then
    echo "Mode harus:"
    echo "light / medium / heavy"
    exit 1
fi

echo "=================================================="
echo "GENERATING ${MODE^^} TRAFFIC"
echo "=================================================="


echo "sh echo '>>> STARTING IPERF3 SERVERS'" >> "$OUT"

for i in $(seq 1 100); do
    echo "h${i} iperf3 -s -D" >> "$OUT"
done

echo "sh sleep 5" >> "$OUT"


if [ "$MODE" == "light" ]; then

    ELEPHANT_BW="1M"
    MEDIUM_BW="500K"
    MICE_BW="100K"

elif [ "$MODE" == "medium" ]; then

    ELEPHANT_BW="3M"
    MEDIUM_BW="1M"
    MICE_BW="300K"

elif [ "$MODE" == "heavy" ]; then

    ELEPHANT_BW="5M"
    MEDIUM_BW="2M"
    MICE_BW="500K"

fi

DATASET=(

# ELEPHANT FLOWS

"h1   10.0.0.91   600 UDP ELEPHANT"
"h23  10.0.0.57   600 UDP ELEPHANT"
"h81  10.0.0.11   600 UDP ELEPHANT"
"h63  10.0.0.35   600 UDP ELEPHANT"

"h4   10.0.0.94   600 TCP ELEPHANT"
"h84  10.0.0.14   600 TCP ELEPHANT"

# MEDIUM FLOWS

"h2   10.0.0.72   600 TCP MEDIUM"
"h21  10.0.0.97   600 UDP MEDIUM"
"h24  10.0.0.98   600 TCP MEDIUM"

"h82  10.0.0.32   600 TCP MEDIUM"
"h61  10.0.0.15   600 UDP MEDIUM"
"h64  10.0.0.16   600 TCP MEDIUM"

"h27  10.0.0.83   600 UDP MEDIUM"
"h34  10.0.0.64   600 TCP MEDIUM"

"h85  10.0.0.22   600 UDP MEDIUM"
"h74  10.0.0.41   600 TCP MEDIUM"

# MICE FLOWS

"h3   10.0.0.53   600 UDP MICE"
"h22  10.0.0.76   600 TCP MICE"

"h83  10.0.0.51   600 UDP MICE"
"h62  10.0.0.55   600 TCP MICE"

"h9   10.0.0.44   600 TCP MICE"
"h10  10.0.0.31   600 UDP MICE"

"h35  10.0.0.87   600 TCP MICE"
"h52  10.0.0.13   600 UDP MICE"

"h37  10.0.0.95   600 TCP MICE"
"h86  10.0.0.24   600 UDP MICE"

"h11  10.0.0.46   600 TCP MICE"
"h12  10.0.0.49   600 UDP MICE"

"h13  10.0.0.28   600 TCP MICE"
"h14  10.0.0.47   600 UDP MICE"

"h73  10.0.0.96   600 TCP MICE"
"h75  10.0.0.89   600 UDP MICE"

)


counter=0

echo "sh echo '>>> STARTING ${MODE^^} TRAFFIC'" >> "$OUT"

for row in "${DATASET[@]}"; do

    read SRC DST TIME TYPE CLASS <<< "$row"

    if [ "$CLASS" == "ELEPHANT" ]; then

        BW=$ELEPHANT_BW

    elif [ "$CLASS" == "MEDIUM" ]; then

        BW=$MEDIUM_BW

    else

        BW=$MICE_BW

    fi

    RANDOM_DELAY=$(( (RANDOM % 3) + 1 ))

    echo "sh sleep $RANDOM_DELAY" >> "$OUT"

    FLOW_NAME="${SRC}_${CLASS}_${TYPE}"

    if [ "$TYPE" == "TCP" ]; then

        echo "$SRC iperf3 -c $DST -t $TIME -i 30 --json > $ABS_DIR/${FLOW_NAME}.json &" >> "$OUT"

    fi

    if [ "$TYPE" == "UDP" ]; then

        echo "$SRC iperf3 -c $DST -u -b $BW -t $TIME -i 30 --json > $ABS_DIR/${FLOW_NAME}.json &" >> "$OUT"

    fi

    counter=$((counter + 1))

    if [ $((counter % 6)) -eq 0 ]; then

        echo "sh sleep 2" >> "$OUT"

    fi

done

echo "sh echo '${MODE^^} TRAFFIC ACTIVE'" >> "$OUT"
echo "sh echo '=================================================='" >> "$OUT"

echo ""
echo "GENERATED ${MODE^^} TRAFFIC"
echo ""
echo "Mininet Script:"
echo "   $OUT"
echo ""
echo "JSON Result:"
echo "   $ABS_DIR"
echo ""
echo "Jalankan di Mininet:"
echo ""
echo "   mininet> source $OUT"
echo ""
echo "Bandwidth Profile:"
echo ""
echo "ELEPHANT : $ELEPHANT_BW"
echo "MEDIUM   : $MEDIUM_BW"
echo "MICE     : $MICE_BW"
echo ""