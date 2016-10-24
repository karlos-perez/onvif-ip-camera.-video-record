from setuptools import setup, find_packages
from os.path import join, dirname


PACKAGE = "recordclient"
NAME = "onvif-record"
DESCRIPTION = "Simple client video records for IP camera supporting ONVIF protocol."
AUTHOR = "Alexei Krivtsov"
AUTHOR_EMAIL = "kralole@gmail.com"
URL = "https://bitbucket.org/kalex13/onvif-ip-camera.-video-record"
VERSION = __import__(PACKAGE).__version__

setup(
    name=NAME,
    version=VERSION,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    description=DESCRIPTION,
    long_description=open(join(dirname(__file__), 'README.rst')).read(),
    license="MIT",
    url=URL,
    packages=find_packages(),
    install_requires=[
        "bitstring==3.1.5",
        "bs4==0.0.1",
        "google-api-python-client==1.5.3",
        "oauth2client==3.0.0",
        "requests==2.10.0",
    ],
)