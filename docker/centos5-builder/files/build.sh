#!/bin/sh -l

package=`basename $1`
echo "Building $package"

if [ -z "$CONDA_PASSWORD" ]
then
    echo Conda password needs to be given as environmental variable CONDA_PASSWORD
    exit 100
fi

if [ -d "skare3" ]
then
    cd skare3
    git pull
    cd -
else
    git clone --single-branch --branch master https://github.com/sot/skare3.git
fi

sed -i -e "s/\${CONDA_PASSWORD}/${CONDA_PASSWORD}/g" $HOME/.condarc
cat $HOME/.condarc
which python
python --version
./skare3/ska_builder.py --build-list ./skare3/ska3_flight_build_order.txt --tag master --force $package

rm `find builds -name \*.json\* -and -path \*noarch\* -or -name \*.json\* -and -path \*linux-64\* -name \*.json\* -and -path \*osx-64\*`
rm -fr builds/work

files=`find builds -name \*.tar.bz2\* -and -path \*noarch\* -or -name \*.tar.bz2\* -and -path \*linux-64\* -name \*.tar.bz2\* -and -path \*osx-64\*`
echo "Built files: $files"
echo ::set-output name=files::$files
