#!/usr/bin/env python3


import json
import argparse
import logging


def check(packages, channel):
    not_ok = []
    for p in packages:
        if p[channel] and p['last_tag'] != p[channel]:
            p['releases'] = [r['release_tag'] for r in p['release_info']]
            if p[channel] not in p['releases']:
                not_ok.append(f"{p['name']}: {p[channel]}, {p['releases']}")

    if not_ok:
        logging.warning('Current package version is not in info:')
        for entry in not_ok:
            logging.warning(' - ' + entry)


def summarize(packages, channel):
    summary = []
    for p in packages:
        if p[channel] and p['last_tag'] != p[channel]:
            releases = [r['release_tag'] for r in p['release_info']]
            if p[channel] not in releases:
                logging.warning(f" - current version of {p['name']} is not in release list:"
                                f" {p[channel]}, {releases}")
            if len(releases) == 1 and releases[0] == '':
                logging.warning(f'Package {p["name"]} has no releases?')
                continue
            if p[channel] in releases:
                releases = releases[releases.index(p['last_tag']):releases.index(p[channel])]
            else:
                releases = releases[releases.index(p['last_tag']):]
            release_info = {r['release_tag']: r['merges'] for r in p['release_info']}
            merges = []
            for merge in sum([release_info[k] for k in releases], []):
                pr = merge['pr_number']
                url = f'{p["owner"]}/{p["name"]}/pull/{pr}' if merge['pr_number'] else ''
                merges.append({
                    'PR': pr,
                    'url': url,
                    'description': merge['title']
                })
            summary.append({
                'name': p['name'],
                'current_version': p[channel],
                'latest_version': p['last_tag'],
                'versions': releases[::-1] + [p[channel]],
                'merges': merges[::-1]
            })
    return summary


def parser():
    parse = argparse.ArgumentParser()
    parse.add_argument('-c', '--channel', default='flight')
    parse.add_argument('-i', default='repository_info.json')
    return parse


def main():
    args = parser().parse_args()
    with open(args.i) as f:
        data = json.load(f)

    packages = sorted(data['packages'], key=lambda pkg: pkg['name'])

    check(packages, args.channel)
    summary = summarize(packages, args.channel)
    summary = sorted(summary, key=lambda pkg: pkg['name'].lower())

    for p in summary:
        print('**{name}: {current_version} -> {latest_version}**'.format(**p),
              f'(all versions: {" -> ".join(p["versions"])})')
        for merge in p['merges']:
            print('  - [PR {PR}](https://github.com/{url}): {description}'.format(**merge))
        print('')


if __name__ == '__main__':
    main()
