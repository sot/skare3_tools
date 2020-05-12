#!/usr/bin/env bash

conda update -y `cat /export/jgonzale/ska3-masters-packages`
/export/jgonzale/ska_testr/run_task.sh --test-spec test_spec_SKA3_HEAD --outputs-dir /export/jgonzale/ska_testr/logs
/proj/sot/ska/bin/watch_cron_logs.pl -config /export/jgonzale/ska_testr/watch_cron.cfg
/proj/sot/ska/jgonzalez/git/skare3_tools/scripts/copy_logs.sh
skare3-test-results /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last -o /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last/test_results.json
