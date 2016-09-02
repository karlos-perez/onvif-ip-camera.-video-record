#!/usr/bin/env python3

import logging
import sys
import time

from multiprocessing import Process, Event

from prtsp import RecordRTSP
from ponvif import OnvifCam


# INITIAL SETTINGS:

# Logging settings:
##  Main logging
log_file = 'pmain.log'
log_level = logging.WARNING
log_format = '%(asctime)s | %(module)s | line:%(lineno)d | %(levelname)-8s: %(message)s'
logging.basicConfig(level=log_level, format=log_format, filename=log_file, filemode='w')
##  Detect motion logging
log_motion = logging.getLogger('detect motion')
log_motion.setLevel(logging.INFO)
formatter=logging.Formatter('%(asctime)s   %(levelname)s','%Y-%m-%d %H:%M:%S')
handler=logging.FileHandler('detect_motion.log', 'a')
handler.setFormatter(formatter)
# handler.setLevel(logging.INFO)
log_motion.addHandler(handler)

# Camera settings:
ip_adress = '172.16.0.7'
onvif_port = 8899
user = 'admin'
password = ''

# Record settings:
## Duration record before motion (in seconds)
rec_before_motion = 15
## Duration record after motion (in seconds)
rec_after_motion = 15
## Folder for video recording
dir_record = ''

def main():
    cam=OnvifCam()
    cam.setup(ip_adress, onvif_port, user, password)

    config = {
        'rtsp_url': cam.getStreamUri(),
    }

    stop_record = Event()
    start_record = Event()

    record = RecordRTSP(config)
    proc = Process(target=record.run_record_with_prebuffer, args=(rec_before_motion, start_record, stop_record))
    proc.daemon = True
    proc.start()
    last_motion = False
    rec = False
    stop_time_record = None
    min_duration = rec_before_motion + rec_after_motion
    try:
        for i in cam.run_detect_motion():
            if i:
                motion = True
                log_motion.info('Motion True')
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
                if time.time() - min_duration > stop_time_record:
                    rec = False
                    start_record.clear()
            last_motion = motion
    except:
        logging.error("{}: {}".format((__name__), sys.exc_info()[0]))
        pass
    finally:
        stop_record.set()
        proc.join()

if __name__ == "__main__":
    main()

