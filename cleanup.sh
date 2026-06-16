#!/bin/bash

echo "Membersihkan eksperimen sebelumnya..."

sudo mn -c > /dev/null 2>&1

sudo pkill -9 iperf3
sudo pkill -9 ryu-manager
sudo pkill -9 ovs-vswitchd
sudo pkill -9 ovsdb-server
sudo pkill -f ITGSend
sudo pkill -f ITGRecv

sudo service openvswitch-switch restart


sleep 3

echo "Pembersihan selesai."