#!/bin/bash
top -b -d 1 -n 720 | grep "Cpu(s)" > log_cpu_usage.txt