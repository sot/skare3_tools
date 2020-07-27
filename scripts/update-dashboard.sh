source $HOME/.ci-auth
last=`readlink -f /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last`
last=$(basename -- $last)
skare3-dashboard
skare3-test-dashboard -b /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/${last} --log-dir https://icxc.cfa.harvard.edu/aspect/skare3/testr/logs/${last} --static-dir /mta/ASPECT/skare3/dashboard/static

mv index.html /proj/sot/ska/www/ASPECT/skare3/dashboard/
mv /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last/test_results.html /proj/sot/ska/www/ASPECT/skare3/dashboard/tests/index.html

echo files copied to /proj/sot/ska/www/ASPECT/skare3/dashboard
echo dashboard at https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/
