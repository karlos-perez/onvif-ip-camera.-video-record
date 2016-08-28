#!/usr/bin/env python3


from prtsp import ClientRTSP
from ponvif import OnvifCam



if __name__ == "__main__":
    ipaddr = "172.16.0.7"
    port = "8899"
    cam=OnvifCam()
    cam.setup(ipaddr, port, 'admin', '')
    print(cam.createPullPointSubscription())
