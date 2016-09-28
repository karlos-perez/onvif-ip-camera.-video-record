#!/usr/bin/env python3

import datetime
import logging
import os
import requests
import sys
import time
import uuid

from bs4 import BeautifulSoup


class OnvifCam:
    def __init__(self):
        self.stop = False

    def setup(self, ipaddr, ipport, user, psw):
        self.ip = ipaddr
        self.port = ipport
        self.username = user
        self.password = psw
        self.capabilities = {}
        cap = self.get_capabilities()
        for k in cap.keys():
            if cap[k].get('xaddr'):
                self.capabilities[k] = cap[k]['xaddr']
            else:
                key = list(cap[k]['extensions'].keys())[0]
                val = list(cap[k]['extensions'].values())[0]['xaddr']
                self.capabilities[key] = val
                for m in cap[k].keys():
                    if cap[k][m].get('xaddr'):
                        self.capabilities[m] = cap[k][m]['xaddr']
                    else:
                        for n in cap[k][m].keys():
                            self.capabilities[n] = cap[k][m][n]['xaddr']
        self.profiles = self.get_profiles()
        self.profilename = list(self.profiles[0].keys())[0]
        self.profiletoken = self.profiles[0][self.profilename]
        self.profile_settings = self.get_profile_settings(self.profiletoken)
        self.snapshot_uri = self.get_snapshot_uri()

    def _create_soap_msg(self, msg, header=''):
        envelope = '<?xml version="1.0" encoding="UTF-8"?>' \
                   '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"' \
                   'xmlns:a="http://www.w3.org/2005/08/addressing">{}</s:Envelope>'
        body = '<s:Body xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' \
               ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">{}</s:Body>'.format(msg)
        if header:
            fullmsg = '{h}{b}'.format(h=header, b=body)
            soapmsg = envelope.format(fullmsg)
        else:
            soapmsg = envelope.format(body)
        return soapmsg

    def _send_request(self, url, msg):
        headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
        # TODO: try: request except:
        response = requests.post(url, msg, headers=headers)
        # TODO: change return {'error': False, 'response': BeautifulSoup(response.content, 'lxml')}
        if response.status_code == 200:
            return  BeautifulSoup(response.content, 'lxml')
        elif response.status_code == 400:
            resp = BeautifulSoup(response.content, 'lxml')
            raise Exception(resp.find('soap-env:text').text)
        else:
            print(response.content.decode())
            raise Exception("Status code: ", response.status_code)

    def _get_all_node_recursively(self, rt, res):
        try:
            name = (rt.name).split(':')[1]
        except:
            name = rt.name
        if len(list(rt.findChildren())) == 0:
            res[name] = rt.text
        else:
            res[name] = {}
            for i in rt.contents:
                self._get_all_node_recursively(i, res[name])

    def get_capabilities(self):
        url = 'http://{ip}:{port}/onvif/'.format(ip=self.ip, port=self.port)
        msg = '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl">' \
              '<Category>All</Category></GetCapabilities>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('tds:capabilities'), result)
        return result['capabilities']

    def get_profiles(self):
        service = 'media'
        url = self.capabilities[service]
        msg = '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        result = []
        for p in resp.find_all('trt:profiles'):
            prof = p.findChild('tt:name')
            pr = {}
            pr[prof.text] = p.attrs['token']
            result.append(pr)
        return result

    def get_profile_settings(self, token):
        service = 'media'
        url = self.capabilities[service]
        profiletoken = '<ProfileToken>{}</ProfileToken>'.format(token)
        msg = '<GetProfile xmlns="http://www.onvif.org/ver10/media/wsdl">{}</GetProfile>'.format(profiletoken)
        resp = self._send_request(url, self._create_soap_msg(msg))
        return resp

    def get_device_information(self):
        service = 'device'
        url = self.capabilities[service]
        msg = '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('tds:getdeviceinformationresponse'), result)
        return result['getdeviceinformationresponse']

    def get_system_date_time(self):
        service = 'device'
        url = self.capabilities[service]
        msg = '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        sdt = {}
        self._get_all_node_recursively(resp.find('tds:systemdateandtime'), sdt)
        result = {}
        result['timezone'] = sdt['systemdateandtime']['timezone']['tz']
        camera_date = sdt['systemdateandtime']['localdatetime']['date']
        camera_time = sdt['systemdateandtime']['localdatetime']['time']
        dt = datetime.datetime(int(camera_date['year']),
                               int(camera_date['month']),
                               int(camera_date['day']),
                               int(camera_time['hour']),
                               int(camera_time['minute']),
                               int(camera_time['second']))
        result['date'] = '{:%Y%m%d-%H%M%S}'.format(dt)
        result['datetime'] = dt
        return result

    def set_system_date_time(self, utc_date_time, timezone):
        service = 'device'
        url = self.capabilities[service]
        date_time_type = '<DateTimeType>Manual</DateTimeType>'
        day_light_saving = '<DaylightSavings>false</DaylightSavings>'
        time_zone = '<TimeZone><TZ xmlns="http://www.onvif.org/ver10/schema">{}</TZ></TimeZone>'.format(timezone)
        hour = '<Hour>{}</Hour>'.format(utc_date_time.hour)
        minute = '<Minute>{}</Minute>'.format(utc_date_time.minute)
        second = '<Second>{}</Second>'.format(utc_date_time.second)
        time_ = '<Time xmlns="http://www.onvif.org/ver10/schema">{h}{m}{s}</Time>'.format(h=hour,
                                                                                          m=minute,
                                                                                          s=second)
        year = '<Year>{}</Year>'.format(utc_date_time.year)
        month = '<Month>{}</Month>'.format(utc_date_time.month)
        day = '<Day>{}</Day>'.format(utc_date_time.day)
        date_ = '<Date xmlns="http://www.onvif.org/ver10/schema">{y}{m}{d}</Date>'.format(y=year,
                                                                                          m=month,
                                                                                          d=day)
        utc_date_time = '<UTCDateTime>{t}{d}</UTCDateTime>'.format(t=time_, d=date_)
        msg = '<SetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl">' \
              '{dt}{dl}{tz}{utc}</SetSystemDateAndTime>'.format(dt=date_time_type,
                                                                dl=day_light_saving,
                                                                tz=time_zone,
                                                                utc=utc_date_time)
        self._send_request(url, self._create_soap_msg(msg))

    def synchronization_date_time(self, delta=1):
        camera_datetime = self.get_system_date_time()
        camera_time = camera_datetime['datetime']
        camera_timezone = camera_datetime['timezone']
        current_time = datetime.datetime.now()
        allowed_divergence = datetime.timedelta(minutes=delta)
        if abs(current_time - camera_time) > allowed_divergence:
            self.set_system_date_time(datetime.datetime.utcnow(), camera_timezone)

    def get_service_capabilities(self):
        service = 'device'
        url = self.capabilities[service]
        msg = '<GetServiceCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"></GetServiceCapabilities>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        result = {}
        for i in resp.find('tds:capabilities').contents:
            result[(i.name).split(':')[1]] = i.attrs
        return result

    def get_video_sources(self):
        service = 'media'
        url = self.capabilities[service]
        msg = '<GetVideoSources xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._send_request(url, self._create_soap_msg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('trt:videosources'), result)
        return result['videosources']

    def get_stream_uri(self):
        service = 'media'
        url = self.capabilities[service]
        stream = '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
        protocol = '<Protocol>RTSP</Protocol>'
        transport = '<Transport xmlns="http://www.onvif.org/ver10/schema">{}</Transport>'.format(protocol)
        streamsetup = '<StreamSetup>{s}{t}</StreamSetup>'.format(s=stream, t=transport)
        profiletoken = '<ProfileToken>{}</ProfileToken>'.format(self.profiletoken)
        msg = '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">' \
              '{s}{p}</GetStreamUri>'.format(s=streamsetup, p=profiletoken)
        resp = self._send_request(url, self._create_soap_msg(msg))
        return resp.find('tt:uri').text

    def _create_head_pull_messages(self, urlact, urlto):
        action = '<a:Action s:mustUnderstand="1">{}</a:Action>'.format(urlact)
        massage_id = '<a:MessageID>urn:uuid:{}</a:MessageID>'.format(uuid.uuid4())
        reply_to = '<a:ReplyTo><a:Address>"http://www.w3.org/2005/08/addressing/anonymous"</a:Address></a:ReplyTo>'
        to = '<a:To s:mustUnderstand="1">{}</a:To>'.format(urlto)
        header = '<s:Header>{a}{m}{r}{t}</s:Header>'.format(a=action, m=massage_id, r=reply_to, t=to)
        return header

    def _convert_str_to_bool(self, string):
        if string.lower() == 'false':
            return False
        else:
            return True

    def _send_pull_messages(self, url):
        url_action = 'http://www.onvif.org/ver10/events/wsdl/PullPointSubscription/PullMessagesRequest'
        head = self._create_head_pull_messages(url_action, url)
        self.timeout = 'PT1M'
        self.msglimit = 1024
        tmout = '<Timeout>{}</Timeout>'.format(self.timeout)
        messagelimit = '<MessageLimit>{}</MessageLimit>'.format(self.msglimit)
        msg = '<PullMessages xmlns="http://www.onvif.org/ver10/events/wsdl">' \
              '{t}{m}</PullMessages>'.format(t=tmout, m=messagelimit)
        a = self._create_soap_msg(msg, head)
        resp = self._send_request(url, a)
        return resp

    def _send_unsubscribe(self, url):
        url_action = 'http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeRequest'
        head = self._create_head_pull_messages(url_action, url)
        msg = '<Unsubscribe xmlns="http://docs.oasis-open.org/wsn/b-2"/>'
        a = self._create_soap_msg(msg, head)
        self._send_request(url, a)

    def _create_pull_point_subscription(self):
        service = 'events'
        url = self.capabilities[service]
        url_action = 'http://www.onvif.org/ver10/events/wsdl/EventPortType/CreatePullPointSubscriptionRequest'
        bmsg = '<CreatePullPointSubscription xmlns="http://www.onvif.org/ver10/events/wsdl">' \
               '<InitialTerminationTime>PT600S</InitialTerminationTime></CreatePullPointSubscription>'
        h = self._create_head_pull_messages(url_action, url)
        msg = self._create_soap_msg(bmsg, h)
        resp = self._send_request(url, msg)
        addr = resp.find('tev:subscriptionreference').findChild('wsa5:address').text
        return addr

    def run_detect_motion(self):
        url = self._create_pull_point_subscription()
        stop = False
        try:
            while not stop:
                resp = self._send_pull_messages(url)
                data = resp.find('tt:data')
                motion = (data.findChild().attrs)['value']
                stop = yield self._convert_str_to_bool(motion)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        except:
            logging.error("run_detect_motion - Exception: {}".format(sys.exc_info()[0]))
        finally:
            self._send_unsubscribe(url)

    def get_snapshot_uri(self):
        """
        GetSnapshotUri - command to obtain a JPEG snapshot from the device
        :return: url to be getting snapshot
        """
        service = 'media'
        url = self.capabilities[service]
        profiletoken = '<ProfileToken>{}</ProfileToken>'.format(self.profiletoken)
        msg = '<GetSnapshotUri xmlns="http://www.onvif.org/ver10/media/wsdl">' \
              '{}</GetSnapshotUri>'.format(profiletoken)
        resp = self._send_request(url, self._create_soap_msg(msg))
        snapshot_url = resp.find('tt:uri').text
        return snapshot_url

    def get_snapshot(self, uri):
        try:
            response = requests.get(uri)
        except requests.ConnectionError():
            logging.error("Connection error: ", uri)
            return None
        return response

    def save_snapshot(self, path=''):
        filename = '{}.jpg'.format(time.strftime("%Y%m%d-%H%M%S"))
        if path:
            abs_path = os.path.abspath(path)
            if not os.path.exists(path):
                try:
                    os.mkdir(abs_path)
                except:
                    logging.error("Fail make dir: ", abs_path)
                    abs_path = os.getcwd()
        else:
            abs_path = os.getcwd()
        file = os.path.join(abs_path, filename)
        response = self.get_snapshot(self.snapshot_uri)
        if not response:
            return
        elif response.status_code != 200:
            logging.error("Get snapshot request.status_code: ", response.status_code)
            self.snapshot_uri = self.get_snapshot_uri()
            response = self.get_snapshot(self.snapshot_uri)
            if not response or response.status_code != 200:
                logging.error("Get snapshot again request.status_code: ", response.status_code)
                return
        with open(file, 'wb') as fl:
            fl.write(response.content)
