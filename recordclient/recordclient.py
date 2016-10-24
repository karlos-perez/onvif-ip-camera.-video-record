#!/usr/bin/env python3

import configparser
import logging
import os
import sys
import time
from multiprocessing import Process, Event

from pgoogledrive import GoogleDrive
from ponvif import OnvifCam
from prtsp import RecordRTSP


def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    result = {}
    for i in config:
        result[i] = dict(config[i])
    return result

def logs_setup(config):
    """
    Logging settings
    :param config: dict settings from config.ini
    :return:
    """
    if config.get('log_dir'):
        log_path = os.path.abspath(config.get('log_dir'))
        if not os.path.exists(log_path):
            try:
                os.mkdir(log_path)
            except:
                logging.error("Fail make dir: ", log_path)
                log_path = os.getcwd()
        else:
            log_path = os.getcwd()
    if not config.get('log_file'):
        log_filename = 'recordclient.log'
    else:
        log_filename = config.get('log_file')
    if not config.get('log_detect_file'):
        detect_filename = 'detect.log'
    else:
        detect_filename = config.get('log_detect_file')
    #  Main logging
    log_file = os.path.join(log_path, log_filename)
    log_level = logging.WARNING
    log_format = '%(asctime)s | %(module)s | line:%(lineno)d | %(levelname)-8s: %(message)s'
    logging.basicConfig(level=log_level, format=log_format, filename=log_file, filemode='w')
    #  Detect motion logging
    log_motion = logging.getLogger('detect motion')
    log_motion.setLevel(logging.INFO)
    formatter=logging.Formatter('%(asctime)s', '%Y-%m-%d %H:%M:%S')
    log_detect_file = os.path.join(log_path, detect_filename)
    handler=logging.FileHandler(log_detect_file, 'a')
    handler.setFormatter(formatter)
    log_motion.addHandler(handler)
    return log_motion

def record_motion():
    config = get_config()
    log_motion = logs_setup(config['Log'])
    record_conf = config['Record']

    cam=OnvifCam(config['Camera'])
    rtsp_url = cam.get_stream_uri()
    record_conf.update({'rtsp_url': rtsp_url})
    cam.synchronization_date_time()

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

def record_online():
    config = get_config()
    logs_setup(config['Log'])
    record_conf = config['Record']
    cam=OnvifCam(config['Camera'])
    rtsp_url = cam.get_stream_uri()
    cam.synchronization_date_time()
    record_conf.update({'rtsp_url': rtsp_url})
    rec = RecordRTSP(record_conf)
    stop_record = Event()
    try:
        proc = Process(target=rec.run_record_online, args=(stop_record,))
        proc.daemon = True
        proc.start()
        while True:
            pass
    except KeyboardInterrupt:
        stop_record.set()
    finally:
        proc.join()


if __name__ == "__main__":
    print('Change record:\n  Online record: 1\n  Detect motion record: 2')
    while True:
        s = input('> ')
        try:
            count = int(s)
            break
        except ValueError:
            print('Enter 1 or 2')
    if count == 1:
        print('Stop record: CTRL + C')
        record_online()
    elif count == 2:
        print('Stop record: CTRL + C')
        record_motion()
    else:
        print('Wrong input')
