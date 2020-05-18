#!/usr/bin/env python3

"""
This is convenience script to make life a bit easier when using
Google Drive programmatically. It is not to a general interface,
but provides some commands one expects with some simple assumptions.

Before using:

    pip install google-api-python-client google_auth_oauthlib

Example usage:

    export GOOGLE_APPLICATION_CREDENTIALS=`pwd`/cxc-ska3-ci-cf8821da91e7.json

    gdrive ls ska-ci
    gdrive upload ska_builder.py ska-ci
    gdrive download ska-ci/ska_builder.py
    gdrive rm ska-ci/ska_builder.py
"""

import sys
import os
import logging
from skare3_tools import gdrive


def cmd_ls(args):
    if not args.path:
        args.path = '/'
    for d in args.path:
        ls = gdrive.ls(d, drive=args.drive, include_trashed=args.trashed)
        n = max([len(f['name']) for _, children in ls for f in children]) if ls else 0
        if args.long:
            fmt = f'{{createdTime}} {{modifiedTime}}    ' \
                  f'{{name:{n}s}} v{{version}} {{id}}  {{trashed}}'
        else:
            fmt = f'{{name:{n}s}} ' + ('{trashed}' if args.trashed else '')
        for f, children in ls:
            f['trashed'] = '(trashed)' if f['trashed'] else ''
            print(fmt.format(**f))
            for c in children:
                c['trashed'] = '(trashed)' if c['trashed'] else ''
                print('    ' + fmt.format(**c))


def cmd_rm(args):
    for d in args.path:
        gdrive.trash(d, drive=args.drive)


def cmd_delete(args):
    for d in args.path:
        gdrive.delete(d, drive=args.drive)


def cmd_upload(args):
    #print(f"upload args: {args.path}")
    destination = args.path[-1]
    for filename in args.path[:-1]:
        if os.path.exists(filename):
            gdrive.upload(filename, destination, drive=args.drive, force=True)
            filename = os.path.abspath(filename)
            logging.getLogger('gdrive').info(f'Upload: {filename:80s} -> {destination}')


def cmd_download(args):
    for f in args.path:
        gdrive.download(f, drive=args.drive, include_trashed=args.trashed)


def cmd_id(args):
    for f in args.path:
        print(gdrive.get_ids(f, drive=args.drive, include_trashed=args.trashed))

ACTIONS = {'ls': cmd_ls,
           'rm': cmd_rm,
           'delete': cmd_delete,
           'upload': cmd_upload,
           'download': cmd_download,
           'id': cmd_id}


def get_parser():
    import argparse
    levels = ['debug', 'info', 'warn']
    levels += [l.upper() for l in levels]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cmd', choices=ACTIONS.keys())
    parser.add_argument('path', nargs='*')
    parser.add_argument('--drive', default=None)
    parser.add_argument('--trashed', action='store_true')
    parser.add_argument('--batch', dest='interactive', action='store_false')
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--save-credentials', action='store_true')
    parser.add_argument('--long', action='store_true')
    parser.add_argument('--log', default='INFO', help='', choices=levels)
    parser.add_argument('-v', action='store_const', const='DEBUG', dest='log')
    return parser


# Custom formatter
class Formatter(logging.Formatter):
    fmt = {
        logging.INFO: logging.Formatter("%(msg)s"),
        None: logging.Formatter("%(levelname)-10s %(name)s/%(module)s %(pathname)s:%(lineno)d -- %(msg)s")
    }
    def format(self, record):
        return self.fmt.get(record.levelno, self.fmt[None]).format(record)


def main():
    parser = get_parser()
    args = parser.parse_args()

    # logging config
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(Formatter())
    logging.getLogger('gdrive').addHandler(handler)
    logging.getLogger('gdrive').setLevel(args.log.upper())

    cred_filename = ''
    if 'GOOGLE_DRIVE_CREDENTIALS' in os.environ:
        cred_filename = '.gdrive_credentials'
        with open(cred_filename, 'w') as cred_file:
            cred_file.write(os.environ['GOOGLE_DRIVE_CREDENTIALS'])
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_filename

    try:
        gdrive.init(interactive=args.interactive, save_credentials=args.save_credentials)
    except gdrive.InitException as e:
        logging.getLogger('gdrive').info(e)
        parser.print_usage()
        parser.exit(1)
    finally:
        if cred_filename and os.path.exists(cred_filename):
            os.remove(cred_filename)

    try:
        ACTIONS[args.cmd](args)
    except Exception as e:
        import traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        trace = traceback.extract_tb(exc_traceback)
        logging.getLogger('gdrive').info(f'Exception:')
        logging.getLogger('gdrive').info(f'  Type: {exc_type.__name__}')
        logging.getLogger('gdrive').info(f'  Value: {exc_value} \n')
        for step in trace:
            logging.getLogger('gdrive').info(f'  in {step.filename}:{step.lineno}/{step.name}:')
            logging.getLogger('gdrive').info(f'    {step.line}')
        parser.exit(2)

if __name__ == '__main__':
    main()
