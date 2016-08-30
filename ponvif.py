#!/usr/bin/env python3

import datetime
from hashlib import sha1
import uuid
import logging
log = logging.getLogger(__name__)
D = log.debug

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
        # self.url = 'http://{ip}:{port}/onvif/Events'.format(ip=self.ip, port=self.port)
        prof = self.getProfiles()[0]
        self.profilename = list(prof.keys())[0]
        self.profiletoken = prof[self.profilename]

    # TODO: ?????
    def onvifAuthHeader(self):
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
        envelope = '<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://www.w3.org/2005/08/addressing">{}</s:Envelope>'
        body = '<s:Body xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">{}</s:Body>'.format(msg)
        if header:
            fullmsg = '{}{}'.format(header, body)
            soapmsg = envelope.format(fullmsg)
        else:
            soapmsg = envelope.format(body)
        return soapmsg

    def _sendRequest(self, url, msg):
        headers = {'Content-Type':'application/soap+xml; charset=utf-8'}
        response = requests.post(url, msg, headers=headers)
         # TODO: переделать формат return {'error': False, 'response': BeautifulSoup(response.content, 'lxml')}
        if response.status_code == 200:
            return  BeautifulSoup(response.content, 'lxml')
        elif response.status_code == 400:
            resp = BeautifulSoup(response.content, 'lxml')
            raise Exception(resp.find('soap-env:text').text)
        else:
            print(response.content.decode())
            raise Exception("Status code: ", response.status_code)

    # TODO: remove s
    def _getAllNodeRecursively(self, rt, s, res):
        try:
            name = (rt.name).split(':')[1]
        except:
            name = rt.name
        # if rt.attrs:
        #     print('ATRIB: ', name,  rt.attrs)
        if len(list(rt.findChildren())) == 0:
            # print(' '*s, name, '---', rt.text)
            res[name] = rt.text
        else:
            # print(' '*s, name)
            res[name] = {}
            s += 4
            for i in rt.contents:
                self._getAllNodeRecursively(i, s, res[name])

    def getDeviceInformation(self):
        url = 'http://{ip}:{port}/onvif/device_service'.format(ip=self.ip, port=self.port)
        msg='<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._getAllNodeRecursively(resp.find('tds:getdeviceinformationresponse'), 0, result)
        return result['getdeviceinformationresponse']

    def getCapabilities(self):
        url = 'http://{ip}:{port}/onvif/device_service'.format(ip=self.ip, port=self.port)
        msg = '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"><Category>All</Category></GetCapabilities>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._getAllNodeRecursively(resp.find('tds:capabilities'), 0, result)
        return result['capabilities']

    def getSystemDateAndTime(self):
        url = 'http://{ip}:{port}/onvif/device_service'.format(ip=self.ip, port=self.port)
        msg = '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        sdt = {}
        self._getAllNodeRecursively(resp.find('tds:systemdateandtime'), 0, sdt)
        result = {}
        result['timezone'] = sdt['systemdateandtime']['timezone']['tz']
        date = sdt['systemdateandtime']['localdatetime']['date']
        time = sdt['systemdateandtime']['localdatetime']['time']
        # TODO: 2016818-21712
        dt = datetime.datetime(int(date['year']),
                               int(date['month']),
                               int(date['day']),
                               int(time['hour']),
                               int(time['minute']),
                               int(time['second']))
        result['date'] = '{:%Y%m%d-%H%M%S}'.format(dt)
        return result

    def getServiceCapabilities(self):
        url = 'http://{ip}:{port}/onvif/device_service'.format(ip=self.ip, port=self.port)
        msg = '<GetServiceCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"></GetServiceCapabilities>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        for i in resp.find('tds:capabilities').contents:
            result[(i.name).split(':')[1]] = i.attrs
        return result

    def getVideoSources(self):
        url = 'http://{ip}:{port}/onvif/Media'.format(ip=self.ip, port=self.port)
        msg= '<GetVideoSources xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = {}
        self._getAllNodeRecursively(resp.find('trt:videosources'), 0, result)
        return result['videosources']

    def getStreamUri(self):
        url = 'http://{ip}:{port}/onvif/Media'.format(ip=self.ip, port=self.port)
        stream = '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
        protocol = '<Protocol>RTSP</Protocol>'
        transport = '<Transport xmlns="http://www.onvif.org/ver10/schema">{}</Transport>'.format(protocol)
        streamsetup = '<StreamSetup>{}{}</StreamSetup>'.format(stream, transport)
        profiletoken = '<ProfileToken>{}</ProfileToken>'.format(self.profiletoken)
        msg = '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">{}{}</GetStreamUri>'.format(streamsetup, profiletoken)
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        # print(resp.prettify())
        return resp.find('tt:uri').text

    def getProfiles(self):
        url = 'http://{ip}:{port}/onvif/Media'.format(ip=self.ip, port=self.port)
        msg='<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        resp = self._sendRequest(url, self._createSOAPmsg(msg))
        result = []
        for p in resp.find_all('trt:profiles'):
            prof = p.findChild('tt:name')
            pr = {}
            pr[prof.text] = p.attrs['token']
            result.append(pr)
        return result

    def _createHeadPullMessages(self, urlact, urlto):
        action =  '<a:Action s:mustUnderstand="1">{}</a:Action>'.format(urlact)
        massageID = '<a:MessageID>urn:uuid:{}</a:MessageID>'.format(uuid.uuid4())
        replyTo = '<a:ReplyTo><a:Address>"http://www.w3.org/2005/08/addressing/anonymous"</a:Address></a:ReplyTo>'
        to = '<a:To s:mustUnderstand="1">{}</a:To>'.format(urlto)
        header = '<s:Header>{}{}{}{}</s:Header>'.format(action, massageID, replyTo, to)
        return header

    def _convertStrToBool(self, string):
        if string.lower() == 'false':
            return False
        else:
            return True

    def _sendPullMessages(self, url):
        self.timeout = 'PT1M'
        self.msglimit = 1024
        tmout = '<Timeout>{}</Timeout>'.format(self.timeout)
        messagelimit = '<MessageLimit>{}</MessageLimit>'.format(self.msglimit)
        msg = '<PullMessages xmlns="http://www.onvif.org/ver10/events/wsdl">{}{}</PullMessages>'.format(tmout, messagelimit)
        urlAction = 'http://www.onvif.org/ver10/events/wsdl/PullPointSubscription/PullMessagesRequest'
        head = self._createHeadPullMessages(urlAction, url)
        a = self._createSOAPmsg(msg, head)
        resp = self._sendRequest(url, a)
        return resp

    def createPullPointSubscription(self):
        url = 'http://{}:{}/onvif/Events'.format(self.ip, self.port)
        urlAction = 'http://www.onvif.org/ver10/events/wsdl/EventPortType/CreatePullPointSubscriptionRequest'
        bmsg = '<CreatePullPointSubscription xmlns="http://www.onvif.org/ver10/events/wsdl"><InitialTerminationTime>PT600S</InitialTerminationTime></CreatePullPointSubscription>'
        h = self._createHeadPullMessages(urlAction, url)
        msg = self._createSOAPmsg(bmsg, h)
        resp = self._sendRequest(url, msg)
        addr = resp.find('tev:subscriptionreference').findChild('wsa5:address').text


        # TODO: !!!!!!
        while True:
        # for i in range(100):
            a = self._sendPullMessages(addr)
            # print(a.prettify())
            # print('-----------')
            tt = a.find('tev:currenttime').text
            aa = a.find('tt:data')
            aaa = aa.findChild().attrs
            motion = aaa['value']
            # print('{}.  {} - {}'.format(i, tt, motion))
            yield self._convertStrToBool(motion)
            time.sleep(0.5)


# if __name__ == "__main__":
#     ipaddr = "172.16.0.7"
#     port = "8899"
#     cam=OnvifCam()
#     cam.setup(ipaddr, port, 'admin', '')
#     print(cam.getDeviceInformation())
#     print('==='*30)
#     print(cam.getCapabilities())
#     print('==='*30)
#     print(cam.getSystemDateAndTime())
#     print('==='*30)
#     print(cam.getServiceCapabilities())
#     print('==='*30)
#     print(cam.getProfiles())
#     print('==='*30)
#     print(cam.getVideoSources())
#     print('==='*30)
#     print(cam.getStreamUri())
#     print('==='*30)
#     print(cam.createPullPointSubscription())


