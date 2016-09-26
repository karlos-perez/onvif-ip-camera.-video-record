#!/usr/bin/env python3

import datetime
from hashlib import sha1
import sys
import uuid
import logging


from random import SystemRandom
import string
import base64
import time

import requests
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

    def _onvif_auth_header(self):
        created = datetime.datetime.now().isoformat().split(".")[0]
        n64 = ''.join(SystemRandom().choice(string.ascii_letters + string.digits+string.punctuation) for _ in range(22))
        nc = base64.b64encode(n64.encode())
        conc = n64 + created + self.password
        pdigest= base64.b64encode(sha1(conc.encode()).digest())
        username = '<Username>{}</Username>'.format(self.username)
        password= '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{}</Password>'.format(pdigest.decode())
        nonce = '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{}</Nonce>'.format(nc.decode())
        created = '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{}</Created>'.format(created)
        usertoken= '<UsernameToken>{}{}{}{}</UsernameToken>'.format(username, password, nonce, created)
        header = '<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">{}</Security></s:Header>'.format(usertoken)
        return header

    def _createSOAPmsg(self, msg, header=''):
        envelope = '<?xml version="1.0" encoding="UTF-8"?>' \
                   '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"' \
                   'xmlns:a="http://www.w3.org/2005/08/addressing">{}</s:Envelope>'
        body = '<s:Body xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' \
               ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">{}</s:Body>'.format(msg)
        if header:
            fullmsg = '{}{}'.format(header, body)
            soapmsg = envelope.format(fullmsg)
        else:
            soapmsg = envelope.format(body)
        return soapmsg

    def _sendRequest(self, url, msg):
        headers = {'Content-Type':'application/soap+xml; charset=utf-8'}
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

    # def _get_all_node_recursively1(self, rt, s, res):
    #     try:
    #         name = (rt.name).split(':')[1]
    #     except:
    #         name = rt.name
    #     if rt.attrs:
    #         print('ATRIB: ', name,  rt.attrs)
    #         res[name] = rt.attrs
    #     if len(list(rt.findChildren())) == 0:
    #         print(' '*s, name, '---', rt.text)
    #         # res[name].update(rt.text)
    #         if not res.get(name):
    #             res[name] = rt.text
    #         else:
    #             res[name].update(rt.text)
    #     else:
    #         print(' '*s, name)
    #         if not res.get(name):
    #             res[name] = {}
    #         s += 4
    #         for i in rt.contents:
    #             self._get_all_node_recursively1(i, s, res[name])

    def get_capabilities(self):
        url = 'http://{ip}:{port}/onvif/'.format(ip=self.ip, port=self.port)
        msg = '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"><Category>All</Category></GetCapabilities>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('tds:capabilities'), result)
        return result['capabilities']

    def get_profiles(self):
        service = 'media'
        url = self.capabilities[service]
        msg='<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
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
        msg='<GetProfile xmlns="http://www.onvif.org/ver10/media/wsdl">{}</GetProfile>'.format(profiletoken)
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        return resp

    def get_device_information(self):
        service = 'device'
        url = self.capabilities[service]
        msg='<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('tds:getdeviceinformationresponse'), result)
        return result['getdeviceinformationresponse']

    def get_system_date_time(self):
        service = 'device'
        url = self.capabilities[service]
        msg = '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
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
        UTC_date_time = '<UTCDateTime>{t}{d}</UTCDateTime>'.format(t=time_, d=date_)
        msg = '<SetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl">' \
              '{dt}{dl}{tz}{utc}</SetSystemDateAndTime>'.format(dt=date_time_type,
                                                                dl=day_light_saving,
                                                                tz=time_zone,
                                                                utc=UTC_date_time)
        self._sendRequest(url, self._createSOAPmsg(msg))

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
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        for i in resp.find('tds:capabilities').contents:
            result[(i.name).split(':')[1]] = i.attrs
        return result

    def get_analytics_modules(self):
        service = 'analytics'
        url = self.capabilities[service]
        print(url)
        msg='<GetAnalyticsModules xmlns="http://www.onvif.org/ver10/analytics/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))

    def get_video_sources(self):
        service = 'media'
        url = self.capabilities[service]
        msg= '<GetVideoSources xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._get_all_node_recursively(resp.find('trt:videosources'), result)
        return result['videosources']

    def get_stream_uri(self):
        service = 'media'
        url = self.capabilities[service]
        stream = '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
        protocol = '<Protocol>RTSP</Protocol>'
        transport = '<Transport xmlns="http://www.onvif.org/ver10/schema">{}</Transport>'.format(protocol)
        streamsetup = '<StreamSetup>{}{}</StreamSetup>'.format(stream, transport)
        profiletoken = '<ProfileToken>{}</ProfileToken>'.format(self.profiletoken)
        msg = '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">{}{}</GetStreamUri>'.format(streamsetup, profiletoken)
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        return resp.find('tt:uri').text

    def _createHeadPullMessages(self, urlact, urlto):
        action =  '<a:Action s:mustUnderstand="1">{}</a:Action>'.format(urlact)
        massage_ID = '<a:MessageID>urn:uuid:{}</a:MessageID>'.format(uuid.uuid4())
        reply_to = '<a:ReplyTo><a:Address>"http://www.w3.org/2005/08/addressing/anonymous"</a:Address></a:ReplyTo>'
        to = '<a:To s:mustUnderstand="1">{}</a:To>'.format(urlto)
        header = '<s:Header>{}{}{}{}</s:Header>'.format(action, massage_ID, reply_to, to)
        return header

    def _convert_str_to_bool(self, string):
        if string.lower() == 'false':
            return False
        else:
            return True

    def _send_pull_messages(self, url):
        url_action = 'http://www.onvif.org/ver10/events/wsdl/PullPointSubscription/PullMessagesRequest'
        head = self._createHeadPullMessages(url_action, url)
        self.timeout = 'PT1M'
        self.msglimit = 1024
        tmout = '<Timeout>{}</Timeout>'.format(self.timeout)
        messagelimit = '<MessageLimit>{}</MessageLimit>'.format(self.msglimit)
        msg = '<PullMessages xmlns="http://www.onvif.org/ver10/events/wsdl">{}{}</PullMessages>'.format(tmout, messagelimit)
        a = self._createSOAPmsg(msg, head)
        resp = self._sendRequest(url, a)
        return resp

    def _send_unsubscribe(self, url):
        url_action = 'http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeRequest'
        head = self._createHeadPullMessages(url_action, url)
        msg = '<Unsubscribe xmlns="http://docs.oasis-open.org/wsn/b-2"/>'
        a = self._createSOAPmsg(msg, head)
        self._sendRequest(url, a)

    def _create_pull_point_subscription(self):
        service = 'events'
        url = self.capabilities[service]
        url_action = 'http://www.onvif.org/ver10/events/wsdl/EventPortType/CreatePullPointSubscriptionRequest'
        bmsg = '<CreatePullPointSubscription xmlns="http://www.onvif.org/ver10/events/wsdl"><InitialTerminationTime>PT600S</InitialTerminationTime></CreatePullPointSubscription>'
        h = self._createHeadPullMessages(url_action, url)
        msg = self._createSOAPmsg(bmsg, h)
        resp = self._sendRequest(url, msg)
        addr = resp.find('tev:subscriptionreference').findChild('wsa5:address').text
        return addr

    def run_detect_motion(self):
        url =  self._create_pull_point_subscription()
        stop = False
        try:
            while not stop:
                resp = self._send_pull_messages(url)
                data = resp.find('tt:data')
                motion = (data.findChild().attrs)['value']
                stop = yield self._convert_str_to_bool(motion)
                time.sleep(0.5)
        except:
            logging.error("run_detect_motion - Exception: {}".format(sys.exc_info()[0]))
        finally:
            self._send_unsubscribe(url)



if __name__ == "__main__":
    ipaddr = "172.16.0.7"
    port = "8899"
    cam=OnvifCam()
    cam.setup(ipaddr, port, 'admin', '')
    # print(cam.get_device_information())
    # print('==='*30)
    # print(cam.get_capabilities())
    print('==='*30)
    print(cam.get_system_date_time())
    print('==='*30)
    cam.synchronization_date_time()
    # print(cam.get_service_capabilities())
    # print('==='*30)
    # print(cam.get_profiles())
    # print('==='*30)
    # print(cam.get_video_sources())
    # print('==='*30)
    # print(cam.get_stream_uri())
    # print('==='*30)
    # print(cam.capabilities.keys())
    # print('==='*30)
    #
    # # print(cam.createPullPointSubscription())
    # count = 0
    # g = cam.run_detect_motion()
    # try:
    #     for i in g:
    #         if count > 3:
    #             g.send(True)
    #         print(count, i)
    #         # time.sleep(1)
    #         count += 1
    # except StopIteration:
    #     pass
    # print('end iteration')
    print('==='*30)
    ww = cam.get_profile_settings(cam.profiletoken)
    print('___'*30)






