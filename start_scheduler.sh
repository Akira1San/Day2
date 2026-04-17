#!/bin/bash
cd /home/akira/akira/day2
source venv/bin/activate
exec python daypart_scheduler.py 2>&1
read -p "Press Enter to exit..."