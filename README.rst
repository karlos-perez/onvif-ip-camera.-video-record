.. image:: http://www.onvif.org/Portals/_default/Skins/onvif/images/logo-new.jpg
       :scale: 20 %


ONVIF IP-camera. Video record
=============================

Simple client video records for IP camera supporting ONVIF protocol.

Client implements:
------------------
* Online video record
* Video motion detection recording
* Save snapshots in Google Drive

Client supported operations (ONVIF protocol):
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* CreatePullPointSubscription
* GetCapabilities
* GetDeviceInformation
* GetProfile
* GetProfiles
* GetRules
* GetServiceCapabilities
* GetSnapshotUri
* GetStreamUri
* GetSystemDateAndTime
* GetVideoSources
* PullMessages
* SetSystemDateAndTime


Quickstart
----------

#. Change config.ini
#. Run record: ::

    python3 recordclient.py

   and choice run online or detect record
