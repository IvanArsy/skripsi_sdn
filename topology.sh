#!/bin/bash
sudo mn --custom topology.py --topo mytopo --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13 --mac --link tc