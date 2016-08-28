#!/usr/bin/env python3

import bitstring
import logging
import re
import socket
import time

from collections import deque
from multiprocessing import Process, Event


LOG_FILE = 'rtsp_record.log'
URL_CAM = "rtsp://172.16.0.7:554/user=admin&password=&channel=1&stream=0.sdp"
IP_CAM_ADDR = '172.16.0.7'
IP_CAM_PORT = 554
CLIENT_PORTS = [60784, 60785]


class ClientRTSP(Process):
    '''
        Recording ip video camera with defined duration.
        Video file format: 20160101-121134-0.h264
    '''
    m_describe = ("DESCRIBE {url} RTSP/1.0\r\n"
                  "CSeq: 2\r\n"
                  "User-Agent: python\r\n"
                  "Accept: application/sdp\r\n\r\n").format(url=URL_CAM)
    m_setup = ("SETUP {url} RTSP/1.0\r\n"
              "CSeq: 3\r\n"
              "User-Agent: python\r\n"
              "Transport: RTP/AVP;unicast;client_port={port1}-{port2}\r\n"
              "\r\n").format(url=URL_CAM, port1=CLIENT_PORTS[0], port2=CLIENT_PORTS[1])
    m_play = ("PLAY {url} RTSP/1.0\r\n"
              "CSeq: 5\r\n"
              "User-Agent: python\r\n"
              "Session: {id}\r\n"
              "Range: npt=0.000-\r\n\r\n")
    m_close = ("TEARDOWN {url} RTSP/1.0\r\nCSeq: 8\r\nSession: {id}\r\n\r\n")
    format_file = '{}{}.h264'


    def __init__(self):
        self.rtsp_url = URL_CAM
        self.msg_describe = self.m_describe.encode()
        self.msg_setup = self.m_setup.encode()

    def _id_session(self, response):
        """
            Search session id from rtsp strings
        """
        resp = response.split('\r\n')
        for r in resp:
            ss = r.split()
            if ss[0].strip() == "Session:":
                return int(ss[1].split(";")[0].strip())

    def _RTP_handler(self, st):
        """
            This routine takes a UDP packet, i.e. a string of bytes and ..
            (a) strips off the RTP header
            (b) adds NAL "stamps" to the packets, so that they are recognized as NAL's
            (c) Concantenates frames
            (d) Returns a packet that can be written to disk as such and that is recognized
                by stock media players as h264 stream
        """
        startbytes = b"\x00\x00\x00\x01"  # this is the sequence of four bytes that identifies a NAL packet
        result = {}
        bt = bitstring.BitArray(bytes=st)  # turn the whole string-of-bytes packet into a string of bits
        lc = 12  # bytecounter
        bc = 12 * 8  # bitcounter
        # ******* Parse RTP header ********
        version = bt[0:2].uint  # version
        p = bt[2]  # P
        x = bt[3]  # X
        cc = bt[4:8].uint  # CC
        m = bt[8]  # M
        pt = bt[9:16].uint  # PT
        sn = bt[16:32].uint  # sequence number
        timestamp = bt[32:64].uint  # timestamp
        ssrc = bt[64:96].uint  # ssrc identifier
        logging.debug("version:{0}, p: {1}, x: {2}, cc: {3}, m: {4}, pt: {5}".format(version, p, x, cc, m, pt))
        logging.debug("sequence number: {0}, timestamp: {1}".format(sn, timestamp))
        logging.debug("sync. source identifier: {}".format(ssrc))
        if cc:
            cids = []
            for i in range(cc):
                cids.append(bt[bc:bc+32].uint)
                bc += 32
                lc += 4
            logging.debug("csrc identifiers: {}".format(cids))
        if x:
            # TODO: check this section
            logging.info('X - is True')
            hid = bt[bc:bc+16].uint
            bc += 16
            lc += 2
            hlen = bt[bc:bc+16].uint
            bc += 16
            lc += 2
            logging.debug("ext. header id: {0}, ext. header len: {1}".format(hid, hlen))
            bc += 32 * hlen
            lc += 4 * hlen
        # ********** NAL packet ************
        # ********** Parse "First byte" a NAL packet ************
        fb = bt[bc]  # "F"
        nri = bt[bc+1:bc+3].uint  # "NRI"
        nlu0 = bt[bc:bc+3]  # "3 NAL UNIT BITS" (i.e. [F | NRI])
        typ = bt[bc+3:bc+8].uint  # "Type"
        logging.debug("F: {0}, NRI: {1}, Type: {2}".format(fb, nri, typ))
        if 0 <= typ <= 12:
            if typ == 7:
                logging.debug(">>>>> SPS packet")
                result['typ'] = 'SPS'
            elif typ == 8:
                logging.debug(">>>>> PPS packet")
                result['typ'] = 'PPS'
            else:
                logging.debug("Unknow TYPE packet: {}".format(typ))
                result['typ'] = 'UNKW'
            result['data'] = startbytes + st[lc:]
            return result
        # ********** Parse "Second byte" a NAL packet ************
        if typ == 28:  # Handles only "Type" = 28, i.e. "FU-A"
            bc += 8
            lc += 1
            start = bt[bc]  # start bit
            end = bt[bc+1]  # end bit
            nlu1 = bt[bc+3:bc+8]  # 5 nal unit bits
            logging.debug("Start bit: {}".format(start))
            logging.debug("End bit: {}".format(end))
            logging.debug("Reserved bit: {}".format(bt[bc+2]))
            result['start'] = start
            result['end'] = end
            head = b''
            if start:
                logging.debug(">>> first fragment found")
                nlu = nlu0 + nlu1  # Create "[3 NAL UNIT BITS | 5 NAL UNIT BITS]"
                head = startbytes + nlu.bytes  # add the NAL starting sequence
                lc += 1
            elif start == False and end == False:  # intermediate fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
                lc += 1  # Skip the "Second byte"
            elif end:  # last fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
                logging.debug(">>> last fragment found")
                lc += 1  # Skip the "Second byte"
            result['data'] = head + st[lc:]
            result['typ'] = 'FU'
            return result
        else:
            logging.error("Unknown frame type ({}) for this fragment".format(typ))
            raise(Exception, "unknown frame type for this piece of s***")

    def _log_record(self, response):
        """
            Pretty-printing rtsp strings
        """
        resp = response.split('\r\n')
        for r in resp:
            logging.info(r)

    def _get_ports(self, searchst, st):
        """
            Searching port numbers from rtsp strings using regular expressions
        """
        pat = re.compile(searchst+"=\d*-\d*")
        pat2 = re.compile('\d+')
        mstring = pat.findall(st)[0]
        nums = pat2.findall(mstring)
        numas = []
        for num in nums:
            numas.append(int(num))
        return numas

    def _filename(self, idr=''):
        if idr:
            id_rec = '-{}'.format(idr)
        else:
            id_rec = ''
        return self.format_file.format(time.strftime("%Y%m%d-%H%M%S"), id_rec)

    def _r(self, b, filename):
        with open(filename, 'wb') as h264:
            for i in b:
                h264.write(i)

    def _get_frame(self):
        SPS_count = 0
        chunk = []
        while True:
            resp = self.udp_socket.recv(4096)
            st = self._RTP_handler(resp)
            if st['typ'] == 'SPS':
                SPS_count += 1
                if SPS_count == 2:
                    SPS_count -= 1
                    yield chunk
                    chunk.clear()
            chunk.append(st['data'])

    def _record_online(self, filename, durations=None):
        chunks = self._get_frame()
        with open(filename, 'wb') as h264:
            begin_rec = time.time()
            for chunk in chunks:
                for frame in chunk:
                    h264.write(frame)
                if stop_record.is_set():
                    break
                if durations:
                    if time.time() - begin_rec > durations:
                        break

    def _record_with_pre_buffer(self, size_buffer):
        buffer = deque()
        chunks = self._get_frame()
        record = False
        id_record = 0
        start_buffer = time.time()
        for chunk in chunks:
            if start_record.is_set() and not record:
                fn = self._filename(str(id_record))
                h264 = open(fn, 'wb')
                record = True
            if time.time() - start_buffer < int(size_buffer):
                buffer.append(chunk)
                if record:
                    for f in buffer.index(0):
                        h264.write(f)
            else:
                if record:
                    for f in buffer.popleft():
                        h264.write(f)
                else:
                    buffer.popleft()
                buffer.append(chunk)
            if not start_record.is_set() and record:
                record =False
                id_record += 1
                h264.close()
                if stop_record.is_set():
                    break
            if stop_record.is_set():
                if not start_record.is_set() and not record:
                    break
                else:
                    start_record.clear()

    def _make_send_msg(self, idr, msg):
        result = msg.format(url=self.rtsp_url, id=idr)
        return result.encode()

    def _make_UDP_socket(self, ports):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for p in ports:
            try:
                sock.bind(("", p))
                break
            except:
                continue
        sock.settimeout(5)
        return sock

    def _make_control_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((IP_CAM_ADDR, IP_CAM_PORT))
        return sock

    def _start(self):
        self.ctrl_socket = self._make_control_socket()
        self.ctrl_socket.send(self.msg_describe)
        self._log_record(self.ctrl_socket.recv(4096).decode())
        self.ctrl_socket.send(self.msg_setup)
        resp = self.ctrl_socket.recv(4096).decode()
        self._log_record(resp)
        id_session = self._id_session(resp)  # Get id session
        self.msg_play = self._make_send_msg(id_session, self.m_play)  # Make PLAY message
        self.msg_close = self._make_send_msg(id_session, self.m_close)  # Make CLOSE message
        clientports = self._get_ports("client_port", resp)
        self.udp_socket = self._make_UDP_socket(clientports)
        self.ctrl_socket.send(self.msg_play)
        self._log_record(self.ctrl_socket.recv(4096).decode())

    def _finish(self):
        self.ctrl_socket.send(self.msg_close)
        self._log_record(self.ctrl_socket.recv(4096).decode())
        self.ctrl_socket.close()
        self.udp_socket.close()
        stop_record.clear()

    def run_record_online(self, durations=None, id_record=None):
        self._start()
        if id_record:
            filename = self._filename(id_record)
        else:
            filename = self._filename()
        self._record_online(filename, durations)
        self._finish()

    def run_record_with_prebuffer(self, size_buffer=5):
        self._start()
        self._record_with_pre_buffer(size_buffer)
        self._finish()


if __name__ == "__main__":
    log_file = LOG_FILE
    log_level = logging.WARNING
    log_format = '[%(asctime)s] %(levelname)-8s: %(message)s'
    logging.basicConfig(level=log_level, format=log_format, filename=log_file)
    dur = 10  # Durations record video in second
    c = ClientRTSP()
    # c.run_record(dur)
    stop_record = Event()
    start_record = Event()

    proc = Process(target=c.run_record_with_prebuffer, args=(10,))
    proc.daemon = True
    proc.start()

    print('start proccess:')
    time.sleep(15)
    start_record.set()
    print(time.strftime("%Y%m%d-%H%M%S"))
    time.sleep(20)
    start_record.clear()
    print('stop rec')
    print(time.strftime("%Y%m%d-%H%M%S"))
    time.sleep(15)
    print('start proccess:')
    start_record.set()
    print(time.strftime("%Y%m%d-%H%M%S"))
    time.sleep(20)
    start_record.clear()
    print('stop rec')
    print(time.strftime("%Y%m%d-%H%M%S"))
    stop_record.set()
    proc.join()
    print('end')
