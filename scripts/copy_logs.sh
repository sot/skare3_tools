#!/usr/bin/env bash

NOW=$(date +"%Y-%d-%mT%H:%M:%S")
rm /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last
cp -fr /export/jgonzale/ska_testr/logs/last/ /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/$NOW
ln -s /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/$NOW /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last
