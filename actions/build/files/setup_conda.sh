if [ -z "$CONDA_PASSWORD" ]
then
    echo Conda password needs to be given as environmental variable CONDA_PASSWORD
    exit 100
fi

wget=`which wget`
if [[ $wget ]]
then
  echo wget https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-MacOSX-x86_64.sh
  wget https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-MacOSX-x86_64.sh
else
  echo curl -O https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-MacOSX-x86_64.sh
  curl -O https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-MacOSX-x86_64.sh
fi

sed -e "s/\${CONDA_PASSWORD}/${CONDA_PASSWORD}/g" ./skare3_tools/actions/build/files/condarc.in > $HOME/.condarc
bash Miniconda3-py38_4.8.3-MacOSX-x86_64.sh -b
export PATH=${HOME}/miniconda3/bin:$PATH
conda install -y -q setuptools_scm gitpython conda-build jinja2 pyyaml python=3.8 numpy packaging

