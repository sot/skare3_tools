export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.gdrive_credentials.json
cd /proj/sot/ska/jgonzalez
echo "download"
echo "--------"
echo ""
gdrive --drive cxc_ops download /ska3/conda-test
echo "rsync"
echo "-----"
echo ""
rsync --checksum --exclude="*.json*" -av /proj/sot/ska/jgonzalez/conda-test/ /proj/sot/ska/www/ASPECT/ska3-conda/masters/
echo "index"
echo "-----"
echo ""
for d in /proj/sot/ska/www/ASPECT/ska3-conda/masters/*; do conda index $d/; done;

echo "repository at https://cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters updated"
