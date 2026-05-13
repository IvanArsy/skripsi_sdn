#!/bin/bash

sudo mn -c

sudo pkill -9 iperf3
sudo pkill -9 ryu-manager
sudo pkill -9 ovs-vswitchd
sudo pkill -9 ovsdb-server

sudo service openvswitch-switch restart

sleep 3