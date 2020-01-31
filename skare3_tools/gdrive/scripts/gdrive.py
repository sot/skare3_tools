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
        print(d)
        print('  ' + '\n  '.join([f['name'] for f in gdrive.ls(d, drive=args.drive)]))


def cmd_rm(args):
    for d in args.path:
        gdrive.rm(d, drive=args.drive)


def cmd_delete(args):
    for d in args.path:
        gdrive.delete(d, drive=args.drive)


def cmd_upload(args):
    for file in args.path[:-1]:
        if os.path.exists(file):
            gdrive.upload(file, args.path[-1], drive=args.drive)
        else:
            print(f'no such file {file}')


def cmd_download(args):
    for f in args.path:
        gdrive.download(f, drive=args.drive)


def cmd_id(args):
    for f in args.path:
        print(gdrive.get_ids(f, drive=args.drive))

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
    parser.add_argument('--batch', dest='interactive', action='store_false')
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--save-credentials', action='store_true')
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

    try:
        gdrive.init(interactive=args.interactive, save_credentials=args.save_credentials)
    except gdrive.InitException as e:
        logging.getLogger('gdrive').info(e)
        parser.print_usage()
        parser.exit(1)

    ACTIONS[args.cmd](args)


if __name__ == '__main__':
    main()
