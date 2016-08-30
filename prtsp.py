#!/usr/bin/env python3

import bitstring
import logging
import re
import socket
import time

from collections import deque


class RecordRTSP:
    '''
        Recording ip video camera.
        Video file format: 20160101-121134-0.h264
    '''
    def __init__(self, config):
        self.rtsp_url = config['rtsp_url']
        self.ip_cam_adress, port  = self._get_ip_port(self.rtsp_url)
        self.ip_cam_port = int(port)
        if config.get('client_ports'):
            self.client_ports = config['client_ports']
        else:
            self.client_ports = [60784, 60785]
        if config.get('log_file'):
            log_file = config['log_file']
        else:
            log_file = 'record_rtsp.log'
        if config.get('log_level'):
            log_level = config['log_level']
        else:
            log_level = logging.WARNING
        log_format = '[%(asctime)s] %(levelname)-8s: %(message)s'
        logging.basicConfig(level=log_level, format=log_format, filename=log_file)
        m_describe = ("DESCRIBE {url} RTSP/1.0\r\n"
                      "CSeq: 2\r\n"
                      "User-Agent: python\r\n"
                      "Accept: application/sdp\r\n\r\n").format(url=self.rtsp_url)
        m_setup = ("SETUP {url} RTSP/1.0\r\n"
                  "CSeq: 3\r\n"
                  "User-Agent: python\r\n"
                  "Transport: RTP/AVP;unicast;client_port={port1}-{port2}\r\n"
                  "\r\n").format(url=self.rtsp_url, port1=self.client_ports[0], port2=self.client_ports[1])
        self.m_play = ("PLAY {url} RTSP/1.0\r\n"
                  "CSeq: 5\r\n"
                  "User-Agent: python\r\n"
                  "Session: {id}\r\n"
                  "Range: npt=0.000-\r\n\r\n")
        self.m_close = ("TEARDOWN {url} RTSP/1.0\r\nCSeq: 8\r\nSession: {id}\r\n\r\n")
        self.msg_describe = m_describe.encode()
        self.msg_setup = m_setup.encode()
        self.format_file = '{}{}.h264'

    def _get_ip_port(self, url):
        '''
        Get IP adress and port camera from URL.
        :param url: rtsp url
        :return: [ip, port]
        '''
        ipp = url.split('/')
        return ipp[2].split(':')

    def _id_session(self, response):
        '''
        Search session id from rtsp strings
        :param response: Response from the camera
        :return: ID session
        '''
        resp = response.split('\r\n')
        for r in resp:
            ss = r.split()
            if ss[0].strip() == "Session:":
                return int(ss[1].split(";")[0].strip())

    def _RTP_handler_h264(self, st):
        '''
        This routine takes a UDP packet, i.e. a string of bytes and ..
            1) strips off the RTP header
            2) adds NAL "stamps" to the packets, so that they are recognized as NAL's
            3) Concantenate frames
            40 Returns a packet that can be written to disk as such and that is recognized
                by stock media players as h264 stream
        :param st: RTP packet
        :return: packet h264 stream
        '''
        """

        """
        startbytes = b'\x00\x00\x00\x01'  # This is the sequence of four bytes that identifies a NAL packet
        result = {}
        bt = bitstring.BitArray(bytes=st)  # Turn the whole string-of-bytes packet into a string of bits
        lc = 12  # Byte counter
        bc = 12 * 8  # Bit counter
        # ******* Parse RTP header ********
        version = bt[0:2].uint  # Version
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
            logging.debug('X (additional header) - is True')
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
                logging.debug("SPS packet")
                result['typ'] = 'SPS'
            elif typ == 8:
                logging.debug("PPS packet")
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
            start = bt[bc]  # Start bit
            end = bt[bc+1]  # End bit
            nlu1 = bt[bc+3:bc+8]  # 5 nal unit bits
            logging.debug("Start bit: {}".format(start))
            logging.debug("End bit: {}".format(end))
            logging.debug("Reserved bit: {}".format(bt[bc+2]))
            result['start'] = start  # Start of frame
            result['end'] = end  # End of the frame
            head = b''
            if start:
                logging.debug(">>> first fragment found")
                nlu = nlu0 + nlu1  # Create "[3 NAL UNIT BITS | 5 NAL UNIT BITS]"
                head = startbytes + nlu.bytes  # Add the NAL starting sequence
                lc += 1
            elif start == False and end == False:  # Intermediate fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
                lc += 1  # Skip the "Second byte"
            elif end:  # Last fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
                logging.debug(">>> last fragment found")
                lc += 1  # Skip the "Second byte"
            result['data'] = head + st[lc:]
            result['typ'] = 'FU'
            return result
        else:
            logging.error("Unknown frame type ({}) for this fragment".format(typ))
            raise(Exception, "unknown frame type for this piece of s***")

    def _log_record(self, response):
        '''
        Pretty-printing rtsp response in log
        :param response: Response from the camera
        :return: None
        '''
        resp = response.split('\r\n')
        for r in resp:
            logging.info(r)

    def _get_ports(self, search_str, response):
        '''
        Searching port numbers from rtsp strings
        :param search_str: Search string
        :param response: Response from the camera
        :return: Ports
        '''
        pat = re.compile(search_str+"=\d*-\d*")
        pat2 = re.compile('\d+')
        mstring = pat.findall(response)[0]
        nums = pat2.findall(mstring)
        numas = []
        for num in nums:
            numas.append(int(num))
        return numas

    def _filename(self, idr=''):
        '''
        Creating a record file name
        :param idr: The serial number of the record for integrity monitoring
        :return: File name in format YYYYYMMDD-HHMMSS-ID.h264
        '''
        if idr:
            id_rec = '-{}'.format(idr)
        else:
            id_rec = ''
        return self.format_file.format(time.strftime("%Y%m%d-%H%M%S"), id_rec)

    def _get_frame(self):
        '''
        Read a UDP packets and creating of list packages of stream 264
        Return chunk video between SPS packages.
        Video chunk approximately 2 seconds duration
        :return: [SPS, PPS, Unknow type, FU-A, FU-A, ...,  FU-A]
        '''
        SPS_count = 0
        chunk = []
        while True:
            resp = self.udp_socket.recv(4096)
            st = self._RTP_handler_h264(resp)
            if st['typ'] == 'SPS':
                SPS_count += 1
                if SPS_count == 2:
                    SPS_count -= 1
                    yield chunk
                    chunk.clear()
            chunk.append(st['data'])

    def _record_online(self, filename, stop, durations=None):
        '''
        Online record h264 video stream.
        :param filename: str(file name)
        :param stop: multiprocessing.Event() - for stoping video
        :param durations: Durations record
        :return: None
        '''
        chunks = self._get_frame()
        with open(filename, 'wb') as h264:
            begin_rec = time.time()
            for chunk in chunks:
                for frame in chunk:
                    h264.write(frame)
                if stop.is_set():
                    break
                if durations:
                    if time.time() - begin_rec > durations:
                        break

    def _record_with_pre_buffer(self, size_buffer, start, stop):
        '''
        Record video stream h264 with pre-record buffer.
        Ring buffer size of 'size_buffer' is constant cyclic flow record.
        Designed to record video to trigger motion detection.
        :param size_buffer: Size buffer per seconds
        :param start: multiprocessing.Event() -  start records
        :param stop: multiprocessing.Event() - stop records
        :return: None
        '''
        buffer = deque(maxlen=int(size_buffer/2))
        chunks = self._get_frame()
        record = False
        id_record = 0
        for chunk in chunks:
            a = list(chunk)
            buffer.append(a)
            if start.is_set() and not record:
                fn = self._filename(str(id_record))
                h264 = open(fn, 'wb')
                record = True
            if record:
                e = buffer[0]
                for f in e:
                    h264.write(f)
            if not start.is_set() and record:
                record =False
                id_record += 1
                h264.close()
                if stop.is_set():
                    break
            if stop.is_set():
                if not start.is_set() and not record:
                    break
                else:
                    start.clear()

    def _make_send_msg(self, ids, msg):
        '''
        Create RTSP message
        :param ids: ID session
        :param msg: message
        :return: RTSP message for send IP camera
        '''
        result = msg.format(url=self.rtsp_url, id=ids)
        return result.encode()

    def _make_UDP_socket(self, ports):
        '''
        Create UDP socket for receipt RTP packets
        :param ports: Client port
        :return: Socket
        '''
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
        '''
        Create TCP socket for control RTSP stream
        :return: Socket
        '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.ip_cam_adress, self.ip_cam_port))
        return sock

    def _start(self):
        '''
        Start and log control RTSP stream
        :return:
        '''
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
        '''
        Close connection
        :return:
        '''
        self.ctrl_socket.send(self.msg_close)
        self._log_record(self.ctrl_socket.recv(4096).decode())
        self.ctrl_socket.close()
        self.udp_socket.close()

    def run_record_online(self, stop, durations=None, filename=None):
        '''
        Run recording online video
        :param stop: multiprocessing.Event() - stop online record
        :param durations: Duration record in seconds
        :param filename:
        :return:
        '''
        stop_event = stop
        self._start()
        if filename:
            file_name = filename
        else:
            file_name = self._filename()
        self._record_online(file_name, stp, durations)
        self._finish()

    def run_record_with_prebuffer(self, size_buffer, start, stop):
        '''
        Run record video with pre-recording
        :param size_buffer: Duration pre-recording in second
        :param start: multiprocessing.Event() - start online record
        :param stop: multiprocessing.Event() - stop online record
        :return:
        '''
        self._start()
        strt = start
        stp = stop
        self._record_with_pre_buffer(size_buffer, strt, stp)
        self._finish()

