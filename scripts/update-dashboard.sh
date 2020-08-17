source $HOME/.ci-auth
skare3-dashboard -o /proj/sot/ska/jgonzalez/index.html
skare3-test-dashboard -o /proj/sot/ska/jgonzalez/test_results.html

mv index.html /proj/sot/ska/www/ASPECT/skare3/dashboard/
mv /proj/sot/ska/www/ASPECT_ICXC/skare3/testr/logs/last/test_results.html /proj/sot/ska/www/ASPECT/skare3/dashboard/tests/index.html

# echo files copied to /proj/sot/ska/www/ASPECT/skare3/dashboard
# echo dashboard at https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/
