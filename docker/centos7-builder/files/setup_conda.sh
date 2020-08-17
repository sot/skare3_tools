if [ -z "$CONDA_PASSWORD" ]
then
    echo Conda password needs to be given as environmental variable CONDA_PASSWORD
    exit 100
fi

sed -e "s/\${CONDA_PASSWORD}/${CONDA_PASSWORD}/g" ./docker/centos5-builder/files/condarc.in > $HOME/.condarc
curl -O https://repo.continuum.io/miniconda/Miniconda3-4.3.21-MacOSX-x86_64.sh
bash Miniconda3-4.3.21-MacOSX-x86_64.sh -b
export PATH=${HOME}/miniconda3/bin:$PATH
conda install python=3.6.2 conda=4.3.21 -q --yes
conda install ska3_builder -q --yes
