#!/usr/bin/env python3

"""
This is convenience module to make life a bit easier when using
Google Drive programmatically. The intention is not to have a general
interface, but to model the expected behavior under some simple
assumptions.

This code does not use the `Google Drive API <https://developers.google.com/drive/api/v3/>`_
directly. Instead it uses `google-api-python-client
<https://github.com/googleapis/google-api-python-client>`_, which in turn uses the rest API.
This client has `its own API documentation
<http://googleapis.github.io/google-api-python-client/docs/dyn/drive_v3.html>`_

Authentication
^^^^^^^^^^^^^^

This module handles authentication in two ways:

- Interactively using the `OAuth 2 standard <https://oauth.net/2/>`_.
  This process `is described here <https://developers.google.com/identity/protocols/OAuth2>`_. In this case, a browser window should popup and display an authorization page. After the user accepts, the program continues.
- In batch mode using a `Google Cloud service account <https://cloud.google.com/docs/authentication/getting-started>`_. In this case, the GOOGLE_APPLICATION_CREDENTIALS environmental variable must be defined.

Example Usage
^^^^^^^^^^^^^^

.. code-block:: python

      >>> from skare3_tools import gdrive
      >>> gdrive.init()
      >>> for file in gdrive.ls('/'):
      ...     print(file['name'])
      ...
      Javier Gonzalez - Weekly Meetings
      ska-ci
      SkaRE3 Packages Flowchart.pdf
      SkaRE3 Packages Flowchart
      >>> for file in gdrive.ls('/', drive='cxc_ops'):
      ...     print(file['name'])
      ...
      ska3
      Anomaly response whiteboards
      02-Manager-190813.txt
      >>> res = gdrive.download('SkaRE3 Packages Flowchart.pdf')

Known Issues
^^^^^^^^^^^^

- Auth2 authentication is enabled for CfA accounts only. This can be changed.
- When authenticating, the program locks if one tries to use a non-CfA account.
- When authenticating, the program locks if the user never answers the request.
- This program includes trashed files. In Google Drive, the trash is not a folder, it's a flag.
  The files' parent does not change when they are trashed. We would need to filter these out.
- I still do not know what happens if a folder is trashed. Children might persist parent-less.
- Google drive has a notion of file versions. This module does not handle that.
"""

import os
import logging
import pickle
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import mimetypes


DRIVE = None
LOGGER = logging.getLogger('gdrive')

class InitException(Exception):
    pass


def init(interactive=True, save_credentials=False):
    """
    Initialize the Google Drive API.

    :param interactive: bool
        If interactive == True, the user is referred to a page to give access to the application
        This is ignored if GOOGLE_APPLICATION_CREDENTIALS is defined or if
        $HOME/gdrive_credentials.json exists
    :param save_credentials: bool
        If save_credentials == True, the authentication credentials are saved in $HOME
    """
    global DRIVE

    default_credentials = os.path.join(os.path.expandvars('$HOME'), 'gdrive_credentials.json')
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ and os.path.exists(default_credentials):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = default_credentials

    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        DRIVE = build('drive', 'v3')

    if interactive and not DRIVE:
        # the following is a copy from https://developers.google.com/drive/api/v3/quickstart/python
        # see https://developers.google.com/identity/protocols/OAuth2
        # the client API config contains the "client secret", which one is supposed to
        # embed in the source code of the application.
        # (In this context, the client secret is obviously not treated as a secret.)
        SCOPES = ['https://www.googleapis.com/auth/drive',
                  'https://www.googleapis.com/auth/drive.metadata']
        creds = None
        credentials_file = os.path.join(os.environ['HOME'], '.gdrive_credentials.pkl')
        if os.path.exists(credentials_file):
            with open(credentials_file, 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                client_config = os.path.join(os.path.dirname(__file__), 'client_config.pkl')
                with open(client_config, 'rb') as client_config:
                    config = pickle.load(client_config)
                flow = InstalledAppFlow.from_client_config(config, SCOPES)
                creds = flow.run_local_server(authorization_prompt_message='', port=0)
            if save_credentials:
                # Save the credentials for the next run
                with open(credentials_file, 'wb') as out:
                    pickle.dump(creds, out)
        DRIVE = build('drive', 'v3', credentials=creds)

    if not DRIVE:
        msg = f"""Failed to initialize (interactive={interactive}).
        
        Authentication credentials are expected in one of these two ways:
        - a json file in $HOME/gdrive_credentials.json or pointed by the
          GOOGLE_APPLICATION_CREDENTIALS environment variable
        - interactive confirmation by navigating to a confirmation page. 
        """
        raise InitException(msg)


def get_drive_id(name):
    """
    Get the unique ID corresponding to a shared drive

    :param name: str
    :return: str
    """
    if name is None:
        return DRIVE.files().get(fileId='root').execute()['id']
    drives = [d for d in DRIVE.drives().list().execute()['drives'] if d['name'] == name]
    if len(drives) > 1:
        LOGGER.warning(f'There are {len(drives)} with name {name}, returning the first one')
    if not drives:
        return None
    return drives[0]['id']


def get_ids(path, parent_id=None, drive=None, limit=None, include_trashed=False):
    """
    Get the ID of all files that match the given path.

    The path can be absolute, in which case it is interpreted in relation to the root of the user's
    drive (My Drive), or it can be relative. If thepath is relative, the root can be anywhere in
    Google Drive as long as the user has access to it.

    With the following directory structure in My Drive (ids in parenthesis)::

       - directory              (id_1)
         - directory_1          (id_2)
           - directory_1        (id_3)
             - directory_1      (id_4)
           - directory_2        (id_5)
         - directory_2          (id_6)

    This is the output from different calls:

    .. code-block:: python

      >>>> get_ids('/directory')
      ['id_1']

      >>>> get_ids('/directory/directory_1')
      ['id_2']

      >>>> get_ids('directory_1')
      ['id_2', 'id_3', 'id_4']

      >>>> get_ids('/directory/directory_1/directory_1')
      ['id_3']

      >>>> get_ids('directory_1/directory_1')
      ['id_3', 'id_4']

      >>>> get_ids('/ska3')
      []

    And with this structure in the cxc_ops shared drive::

      - ska3                     (id_1)
        - conda-test             (id_2)
        - ska3                   (id_3)

    The output is:

    .. code-block:: python

      >>>> get_ids('ska3', drive='cxc_ops')
      ['id_1', 'id_3']

      >>>> get_ids('/ska3', drive='cxc_ops')
      ['id_1']

      >>>> get_ids('/ska3/ska3', drive='cxc_ops')
      ['id_3']

    NOTES:
      - this does not handle pagination (google drive's results are actually paginated)

    :param path: str
    :param parent_id: str (optional)
    :param drive: str (optional)
    :param limit: int (optional)
        maximum number of matching files returned. The rest are just discarded.
    :param include_trashed: bool (optional)
        Also include IDs of files/folders that are in the trash.
    :returns: str
    """
    # assert os.path.isabs(path)
    if not path:
        return []
    folders = [p for p in path.strip('/').split('/') if p]
    root = get_drive_id(drive)
    if not folders:
        # path is only forward slashes, so path is 'root'
        return [root]
    folder = folders[0]
    if path[0] == '/' and len(folders) == 1:
        parent_id = root

    args = {'q': f'name="{folder}"',
            'fields': 'files(id, name, trashed)'}
    if parent_id:
        args['q'] += f' and "{parent_id}" in parents'
    if drive is not None:
        args.update({
            'corpora': 'drive',
            'includeItemsFromAllDrives': True,
            'supportsAllDrives': True,
            'driveId': get_drive_id(drive)
        })
    files = [f for f in DRIVE.files().list(**args).execute()['files']]
    if not include_trashed:
        files = [f for f in files if not f['trashed']]
    ids = [f['id'] for f in files]
    if len(folders) > 1:
        children = [
            get_ids('/'.join(folders[1:]), parent, drive=drive, include_trashed=include_trashed)
            for parent in ids
        ]
        ids = sum(children, [])
    if limit is None:
        return ids
    elif limit == 1:
        return ids[0]
    return ids[:limit]


def get_children(file_id,
                 fields=('id, name, kind, version, mimeType, createdTime, trashed'
                         ', modifiedTime, headRevisionId, owners'),
                 drive=None,
                 include_trashed=False):
    """
    Get metadata for the given IDs.

    Possible metadata fields are listed in the documentation of get_meta

    :param path: str
    :param fields: str (optional)
        a comma-separated list of metadata fields.
    :param drive: str (optional)
    :returns: list of dict
    """
    args = {'q': f'"{file_id}" in parents',
            'fields': f'files({fields})'}
    if drive is not None:
        args.update({
            'corpora': 'drive',
            'includeItemsFromAllDrives': True,
            'supportsAllDrives': True,
            'driveId': get_drive_id(drive)
        })
    res = DRIVE.files().list(**args).execute()['files']
    if not include_trashed:
        res = [f for f in res if not f['trashed']]
    return res


def get_meta(file_ids, fields=('id, name, kind, version, mimeType, createdTime, trashed'
                     ', modifiedTime, headRevisionId, owners'), drive=None):
    """
    Get metadata for the given IDs.

    Possible metadata fields:

    - kind
    - id
    - name
    - mimeType
    - starred
    - trashed
    - explicitlyTrashed
    - parents
    - spaces
    - version
    - webContentLink
    - webViewLink
    - iconLink
    - hasThumbnail
    - thumbnailVersion
    - viewedByMe
    - createdTime
    - modifiedTime
    - modifiedByMeTime
    - modifiedByMe
    - owners
    - lastModifyingUser
    - shared
    - ownedByMe
    - capabilities
    - viewersCanCopyContent
    - copyRequiresWriterPermission
    - writersCanShare
    - permissions
    - permissionIds
    - originalFilename
    - fullFileExtension
    - fileExtension
    - md5Checksum
    - size
    - quotaBytesUsed
    - headRevisionId
    - isAppAuthorized

    :param path: str
    :param fields: str (optional)
        a comma-separated list of metadata fields.
    :param drive: str (optional)
    :returns: list of dict
    """
    res = []
    for file_id in file_ids:
        meta = DRIVE.files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()
        fields = [f.strip() for f in fields.split(',')]
        meta = {k: (meta[k] if k in meta else None) for k in fields}
        res.append(meta)
    return res


def ls(path,
       fields=('id, name, kind, version, mimeType, createdTime, trashed'
               ', modifiedTime, headRevisionId, owners'),
       drive=None,
       include_trashed=False):
    """
    Get metadata for a given path.

    :param path: str
    :param fields: str (optional)
        a comma-separated list of metadata fields.
    :param drive: str (optional)
    :param include_trashed: bool
    :returns: list
        list of pairs (metadata, children), where children is a list of metadata for the children.
    """
    file_ids = get_ids(path, drive=drive, include_trashed=include_trashed)
    file_meta = get_meta(file_ids, fields=fields, drive=drive)
    res = []
    for meta in file_meta:
        if meta['mimeType'] == 'application/vnd.google-apps.folder':
            children = get_children(meta['id'],
                                    fields=fields,
                                    drive=drive,
                                    include_trashed=include_trashed)
        else:
            children = None
        res.append([meta, children])
    return res


def trash(path=None, path_id=None, drive=None):
    """
    Move file/folder to the trash.

    Only path or path_id can be given at a time.

    NOTE:
    If a path is given, it will trash all files/folders matching the path.

    :param path: str
    :param path_id: str
    :param drive: str
    """
    if path is not None and path_id is not None:
        raise Exception('Only one of "path" or "path_id" can be give at a time')

    if path is not None:
        for path_id in get_ids(path, drive=drive, include_trashed=False):
            trash(path_id=path_id, drive=drive)
    elif path_id is not None:
        try:
            DRIVE.files().update(fileId=path_id,
                                 body={'trashed': True},
                                 supportsAllDrives=True).execute()
        except HttpError:
            raise


def delete(path=None, path_id=None, drive=None):
    """
    Remove file/folder without moving it to the trash.

    Only path or path_id can be given at a time.

    NOTE:
    If a path is given, it will permanently delete all files/folders matching the path.
    It will also include files/folders in the trash

    :param path: str
    :param path_id: str
    :param drive: str
    """
    if path is not None and path_id is not None:
        raise Exception('Only one of "path" or "path_id" can be give at a time')

    if path is not None:
        for path_id in get_ids(path, drive=drive):
            delete(path_id=path_id, drive=drive)
    elif path_id is not None:
        try:
            DRIVE.files().delete(fileId=path_id, supportsAllDrives=True).execute()
        except HttpError:
            raise


def _upload(filename, destination=None, parent=None, drive=None, force=True):
    """
    Upload a file into a given folder in Google Drive.

    Strictly speaking, folders are not actual folders in Google Drive.
    The file is uploaded and its parent is set to the given folder.
    The destination must not be in the trash.

    :param filename: str
        Input file name.
    :param parent: str (optional)
        The ID of the parent folder
    :param destination: str (optional)
        Destination directory. Required if parent is None.
    :param drive: str (optional)
    :param force: bool (optional, default=True)
        if force == True, overwrite any pre-existing file at the destination.
    """
    if parent is None:
        parent = get_ids(destination, drive=drive, include_trashed=False)
        if len(parent) > 1:
            raise Exception(f'Path is not unique: {destination}')
        if len(parent) == 0:
            raise Exception(f'Path does not exist: {destination}')
        parent = parent[0]

    filename = os.path.abspath(filename)

    if drive:
        drive_args = {
            'corpora': 'drive',
            'includeItemsFromAllDrives': True,
            'supportsAllDrives': True,
            'driveId': get_drive_id(drive)
        }
    else:
        drive_args = {}

    # check if file is there already
    q = f'"{parent}" in parents and name = "{os.path.basename(filename)}"'
    files = DRIVE.files().list(q=q, **drive_args).execute()['files']
    files = get_meta([f['id'] for f in files], drive=drive)
    files = [f for f in files if not f['trashed']]
    file_id = None
    if files:
        if files[0]['mimeType'] == 'application/vnd.google-apps.folder':
            # if it is there and is a directory, use it
            file_id = files[0]['id']
        else:
            if force:
                # it is there and is a file, remove it
                for file in files:
                    trash(path_id=file['id'], drive=drive)
            else:
                file_id = files[0]['id']

    # create if not there
    if file_id is None:
        metadata = {'name': os.path.basename(filename),
                    'parents': [parent]}
        if os.path.isdir(filename):
            metadata['mimeType'] = 'application/vnd.google-apps.folder'
            file_id = DRIVE.files().create(body=metadata,
                                           media_body=None,
                                           fields='id',
                                           supportsAllDrives=True).execute()['id']
        else:
            file_type, _ = mimetypes.guess_type(filename)
            mime_type = file_type if file_type else 'application/octet-stream'
            media = MediaFileUpload(filename, mimetype=mime_type)
            file_id = DRIVE.files().create(body=metadata,
                                           media_body=media,
                                           fields='id',
                                           supportsAllDrives=True).execute()
    return file_id


def upload(filename, destination, drive=None, force=False):
    """
    Recursively upload a file to a given folder in Google Drive.

    If argument is a directory, traverse the tree, uploading everything
    while keeping the hierarchy. This removes and replaces existing files.
    The destination must not be in the trash.

    :param filename: str
        Input file name.
    :param destination: str
        Destination directory.
    :param drive: str (optional)
    :param force: str (optional, default=False)
    """
    filename = os.path.abspath(filename)
    file_id = {filename: _upload(filename, destination, drive=drive, force=force)}
    destinations = {filename: os.path.join(destination, os.path.basename(filename))}
    #LOGGER.info(f'Upload: {filename:80s} -> {destination}')

    # traverse the tree
    for root, d_names, f_names in os.walk(filename,
                                          topdown=True, onerror=None, followlinks=False):
        parent = file_id[root]  # its is already there by construction
        for directory in d_names:
            name = os.path.join(root, directory)
            file_id[name] = _upload(name, parent=parent, drive=drive, force=force)
            destinations[name] = os.path.join(destinations[root], directory)
            LOGGER.info(f'{name} -> {destinations[root]}')

        for filename in f_names:
            name = os.path.join(root, filename)
            file_id[name] = _upload(name, parent=parent, drive=drive, force=force)
            destinations[name] = os.path.join(destinations[root], filename)
            LOGGER.info(f'{name} -> {destinations[root]}')


def _walk(path=None, file_id=None, fields='', drive=None, max_depth=None, _depth=0,
          include_trashed=False):
    """
    Generator to descend on a directory hierarchy starting at a given path.

    :param path: str
        If it is not provided, file_id must be provided
    :param file_id: str
        If not provided, it is found from path
    :param fields: str
        comma-separated list of fields to return in dictionary
    :param drive: str
        name of shareddrive
    :param max_depth: int
        maximum number of levels to descend on the hierarchy
    :param _depth: int
        Private. Do not use. It is used in recursive calls.
    :param include_trashed: bool
    :yields: dict
    """
    if max_depth is not None and _depth > max_depth:
        LOGGER.debug(f'reached max depth: {_depth} > {max_depth}')
        return

    # path is only set at the top-level call, all recursive calls use file_id
    if file_id is None:
        ids = get_ids(path, drive=drive, include_trashed=False)
        if len(ids) > 1:
            raise Exception(f'{path} is not a unique path')
        if not ids:
            LOGGER.debug(f'file {path} not found')
            return
        file_id = ids[0]

    if drive:
        drive_args = {
            'corpora': 'drive',
            'includeItemsFromAllDrives': True,
            'supportsAllDrives': True,
            'driveId': get_drive_id(drive)
        }
    else:
        drive_args = {}

    # fields passed to the drive API should not include our own custom fields
    # and should include at least the file name, ID, and trashed status.
    _fields = list(set([f.strip() for f in fields.split(',') if f] + ['id', 'name', 'trashed']))
    _fields = [field for field in _fields if field not in ['path', 'depth']]
    metadata = DRIVE.files().get(fileId=file_id,
                                 fields=','.join(_fields),
                                 supportsAllDrives=True).execute()
    metadata['depth'] = _depth
    metadata['path'] = path if path else metadata['name']

    if include_trashed or not metadata['trashed']:
        # this needs to be copied, because it can be modified in the outer scope (loop below)
        LOGGER.debug(f'walking... {metadata["name"]}')
        yield metadata.copy()

        children = DRIVE.files().list(q=f'"{file_id}" in parents', **drive_args).execute()['files']
        for child in children:
            for node in _walk(file_id=child['id'], fields=fields, drive=drive, max_depth=max_depth,
                              _depth=_depth + 1, include_trashed=include_trashed):
                node['path'] = os.path.join(metadata['path'], node['path'])
                LOGGER.debug(f'walking... {node["name"]}')
                yield node



def walk(path=None, fields='', drive=None, max_depth=None, include_trashed=False):
    """
    Generator to descend on a directory hierarchy starting at a given path.

    With this hierarchy::

      - gdrive-test
        - directory
          - directory
            - directory_2
          - file_3
        - file
        - file_1
        - file_2

    One gets this::

      for path, in gdrive.walk('gdrive-test', fields='path'):
          print(path)

     gdrive-test
     gdrive-test/file_2
     gdrive-test/file_1
     gdrive-test/file
     gdrive-test/directory
     gdrive-test/directory/file_3
     gdrive-test/directory/directory
     gdrive-test/directory/directory/directory_2

    :param path: str
        path where to start on Google drive
    :param fields: str
        comma-separated list of fields
    :param drive: str (optional)
        name of shared drive
    :param max_depth: int
        maximum number of levels to descend on the hierarchy
    :param include_trashed: bool
    :yields: tuple
        a tuple corresponding to the fields argument
    """
    field_list = [f.strip() for f in fields.split(',') if f]
    for node in _walk(path=path, fields=fields, drive=drive, max_depth=max_depth,
                      include_trashed=include_trashed):
        yield tuple([node[field] if field in node else None for field in field_list])


def download(path, destination=None, drive=None, include_trashed=False):
    """
    Recursively download a file and save it into a file (or create a local directory,
    if the remote one is of type folder).

    NOTE:
    The default is not to download files/folders from the trash.
    Setting include_trashed=True can potentially cause naming conflicts, as a file with the same
    name could be in the trash. This will cause the first downloaded file to be overwritten.

    :param path: str
    :param destination: str (optional, default=current directory)
        Destination file name.
    :param include_trashed: bool
    :param drive: str (optional)
    """
    if destination is None:
        destination = os.path.abspath('.')
    root_dir = os.path.dirname(path)
    LOGGER.debug(f'root_dir: {root_dir}')
    for file_id, filename, mime_type, md5Checksum_1 in walk(path,
                                                            fields='id,path,mimeType,md5Checksum',
                                                            drive=drive,
                                                            include_trashed=include_trashed):
        outfile = os.path.relpath(filename, root_dir)  # this will fail in windows
        if mime_type == 'application/vnd.google-apps.folder':
            directory = os.path.join(destination, outfile)
            LOGGER.debug(f'directory {filename} -> {directory}')
            os.makedirs(directory, exist_ok=True)
        else:
            if os.path.exists(outfile):
                md5Checksum_2 = \
                    subprocess.check_output(['md5', outfile]).decode().split('=')[1].strip()
                if md5Checksum_2 == md5Checksum_1:
                    continue
            # https://developers.google.com/drive/api/v3/manage-downloads
            LOGGER.debug(f'file {filename} -> {outfile}')
            if mime_type == 'application/vnd.google-apps.document':
                request = DRIVE.files().export_media(fileId=file_id,
                                                     mimeType='application/pdf')
            else:
                request = DRIVE.files().get_media(fileId=file_id)
            try:
                with open(outfile, 'wb') as out:
                    downloader = MediaIoBaseDownload(out, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
            except HttpError as e:
                LOGGER.error(f'{filename} of type {mime_type} skipped: {e}')




