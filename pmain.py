#!/usr/bin/env python3

import time
from prtsp import RecordRTSP
from ponvif import OnvifCam
import logging

from multiprocessing import Process, Event



if __name__ == "__main__":
    ipaddr = "172.16.0.7"
    port = "8899"
    # duration record before motion (in seconds)
    rec_before_motion = 15
    # duration record after motion (in seconds)
    rec_after_motion = 15
    min_duration = rec_before_motion + rec_after_motion
    count = 0
    motion = False
    last_motion = False
    rec = False
    stop_time_record = None

    cam=OnvifCam()
    cam.setup(ipaddr, port, 'admin', '')

    stop_record = Event()
    start_record = Event()

    config = {
        'rtsp_url': "rtsp://172.16.0.7:554/user=admin&password=&channel=1&stream=0.sdp",
        'client_ports':[60784, 60785],
        'ip_adress':ipaddr,
        'ip_port':554,
        'log_file':'rtsp_record.log',
        'log_level':logging.WARNING,
    }


    record = RecordRTSP(config)
    proc = Process(target=record.run_record_with_prebuffer, args=(rec_before_motion, start_record, stop_record))
    proc.daemon = True
    proc.start()
    for i in cam.createPullPointSubscription():
        if i:
            motion = True
            print('MOTION is True: {}'.format(time.strftime("%Y%m%d-%H%M%S")))
        else:
            motion = False
        if motion and not rec:
            start_record.set()
            rec = True
        elif motion and rec:
            stop_time_record = None
        elif not motion and rec:
            if last_motion:
                stop_time_record = time.time()
                print('last moition false: {}'.format(time.strftime("%Y%m%d-%H%M%S")))
            if time.time() - min_duration > stop_time_record:
                rec = False
                start_record.clear()
                print('stop record: {}'.format(time.strftime("%Y%m%d-%H%M%S")))
        last_motion = motion
        count += 1
    stop_record.set()
    proc.join()
    print('end')
