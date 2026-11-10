#!/usr/bin/env python3
"""Convert an ArduPilot DataFlash .bin log to log.json for render_log_panel.py.  Usage: python3 parse_log.py flight.bin"""
import sys, json
from pymavlink import mavutil
m = mavutil.mavlink_connection(sys.argv[1], dialect='ardupilotmega')
out = {k:[] for k in ['MODE','PL','CTUN','ATT','RCIN','EV','ARM','MSG','GPS','BAT','POS','XKF1']}
while True:
    msg = m.recv_match(blocking=False)
    if msg is None: break
    t = msg.get_type()
    if t in out:
        d = msg.to_dict(); d['_ts'] = getattr(msg,'_timestamp',None)
        out[t].append(d)
json.dump(out, open('log.json','w'), default=str)
for k,v in out.items(): print(k, len(v), list(v[0].keys())[:25] if v else '')
