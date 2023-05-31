source $HOME/.ci-auth
skare3-dashboard -o /proj/sot/ska/jgonzalez/index.html
skare3-dashboard -o /proj/sot/ska/jgonzalez/packages.json
skare3-test-dashboard -o /proj/sot/ska/jgonzalez/test_results.html --static-dir https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/static --log-dir https://icxc.cfa.harvard.edu/aspect/skare3/dashboard/tests
skare3-test-dashboard -o /proj/sot/ska/jgonzalez/test_results.json

# horrible hack:
rm -f /proj/sot/ska/www/ASPECT_ICXC/skare3/dashboard/tests
ln -s `/proj/sot/ska/jgonzalez/git/skare3_tools/scripts/test_dir.py` /proj/sot/ska/www/ASPECT_ICXC/skare3/dashboard/tests
mv /proj/sot/ska/jgonzalez/index.html /proj/sot/ska/www/ASPECT/skare3/dashboard/
mv /proj/sot/ska/jgonzalez/packages.json /proj/sot/ska/www/ASPECT/skare3/dashboard/
mv /proj/sot/ska/jgonzalez/test_results.html /proj/sot/ska/www/ASPECT/skare3/dashboard/tests/index.html
mv /proj/sot/ska/jgonzalez/test_results.json /proj/sot/ska/www/ASPECT/skare3/dashboard/tests/

# echo files copied to /proj/sot/ska/www/ASPECT/skare3/dashboard
# echo dashboard at https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/
