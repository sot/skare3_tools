skare3-github-info -c /home/jgonzale/.chandra_xray_github -o /proj/sot/ska/jgonzalez/skare3_repository_info.json
skare3-dashboard -i /proj/sot/ska/jgonzalez/skare3_repository_info.json -t /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last/test_results.json -o /proj/sot/ska/jgonzalez/index.html
/proj/sot/ska/jgonzalez/git/skare3_tools/skare3_tools/dashboard/test_results.py -i /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last/test_results.json -o /proj/sot/ska/jgonzalez/test_results.html

mv /proj/sot/ska/jgonzalez/index.html /proj/sot/ska/www/ASPECT/skare3/dashboard
mv /proj/sot/ska/jgonzalez/test_results.html /proj/sot/ska/www/ASPECT/skare3/dashboard

echo files copied to /proj/sot/ska/www/ASPECT/skare3/dashboard
echo dashboard at https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/
