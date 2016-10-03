import httplib2
import json
import mimetypes
import oauth2client
import os

from datetime import datetime
from apiclient import discovery
from apiclient import errors
from apiclient.http import MediaFileUpload
from oauth2client import client
from oauth2client import tools


class GoogleDrive:

    def __init__(self, config):
        try:
            import argparse
            self.flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
        except ImportError:
            self.flags = None

        self.application_name = config.get('application_name')
        self.client_secret_file = config.get('client_secret_file')
        self.folder_id = config.get('folder_id')
        self.service = self._google_drive_servise()
        self.current_folder = datetime.now().strftime('%Y%m%d')

    def _google_drive_servise(self):
        """
        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Google Drive service object
        """
        scopes ='https://www.googleapis.com/auth/drive'
        app_dir = os.getcwd()
        credential_dir = os.path.join(app_dir, 'credentials')
        credential_path = os.path.join(credential_dir, 'drive-config-app.json')
        client_secret_path = os.path.join(credential_dir, self.client_secret_file)
        store = oauth2client.file.Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(client_secret_path, scopes)
            flow.user_agent = self.application_name
            if self.flags:
                credentials = tools.run_flow(flow, store, self.flags)
            else:
                credentials = tools.run(flow, store)
        http = credentials.authorize(httplib2.Http())
        return discovery.build('drive', 'v3', http=http)

    def upload_file(self, upload_file, folder):
        """
        Upload new file
        """
        mimetype_file = mimetypes.guess_type(upload_file)[0]
        if mimetype_file is None:
            mimetype_file = 'application/octet-stream'
        media_body = MediaFileUpload(upload_file, mimetype=mimetype_file, resumable=True)
        name = os.path.split(upload_file)[1]
        body = {
            'name': name,
            'parents': [folder,],
          }
        try:
            self.service.files().create(body=body, media_body=media_body).execute()
        except errors.HttpError:
            print('An error occured: ')

    def get_all_folders(self, trashed=False):
        result = {}
        page_token = None
        q = "mimeType='application/vnd.google-apps.folder' and trashed = {}".format(str(trashed).lower())
        while True:
            response = self.service.files().list(q=q,
                                                 spaces='drive',
                                                 fields='nextPageToken, files(id, name)',
                                                 pageToken=page_token).execute()
            for file in response.get('files', []):
                result.update({file.get('name'): file.get('id')})
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return result

    def create_folder(self, name, parent=None):
        if parent is None:
            parent_folder = self.folder_id
        else:
            parent_folder = parent
        file_metadata = {'name' : name,
                         'mimeType' : 'application/vnd.google-apps.folder',
                         'parents': [parent_folder]}
        file = self.service.files().create(body=file_metadata,
                                           fields='id, name').execute()
        return file

    def get_current_folder(self):
        """
        Check current folder for upload
        :return: ID folder
        """
        date = datetime.now().strftime('%Y%m%d')
        folders = self.get_all_folders()
        if self.current_folder in list(folders.keys()):
            result = folders[self.current_folder]
        else:
            self.current_folder = date
            folder = self.create_folder(self.current_folder)
            result = folder['id']
        return result

    def upload(self, file):
        try:
            folder = self.get_current_folder()
            self.upload_file(file, folder)
            return True
        except:
            return False