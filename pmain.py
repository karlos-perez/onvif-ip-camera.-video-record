#!/usr/bin/env python3

import configparser
import json
import logging
import sys
import time

from multiprocessing import Process, Event

from prtsp import RecordRTSP
from ponvif import OnvifCam
from pgoogledrive import GoogleDrive


# Logging settings:
##  Main logging
log_file = 'pmain.log'
log_level = logging.WARNING
log_format = '%(asctime)s | %(module)s | line:%(lineno)d | %(levelname)-8s: %(message)s'
logging.basicConfig(level=log_level, format=log_format, filename=log_file, filemode='w')
##  Detect motion logging
log_motion = logging.getLogger('detect motion')
log_motion.setLevel(logging.INFO)
formatter=logging.Formatter('%(asctime)s', '%Y-%m-%d %H:%M:%S')
handler=logging.FileHandler('detect_motion.log', 'a')
handler.setFormatter(formatter)
log_motion.addHandler(handler)


def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    result = {}
    for i in config:
        result[i] = dict(config[i])
    return result


def record_motion():
    config = get_config()
    record_conf = config['Record']

    cam=OnvifCam(config['Camera'])
    rtsp_url = cam.get_stream_uri()
    record_conf.update({'rtsp_url': rtsp_url})

    drive = GoogleDrive(config['GoogleDrive'])

    record = RecordRTSP(record_conf)
    stop_record = Event()
    start_record = Event()
    proc = Process(target=record.run_record_with_prebuffer, args=(start_record, stop_record))
    proc.daemon = True
    proc.start()

    last_motion = False
    rec = False
    stop_time_record = None
    min_duration = int(record_conf['rec_before_motion']) + int(record_conf['rec_after_motion'])
    try:
        for i in cam.run_detect_motion():
            if i:
                motion = True
                log_motion.info('Motion True')
                snapshot = cam.save_snapshot(record_conf['dir_snapshots'])
                if snapshot:
                    drive.upload(snapshot)
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
    record_motion()

