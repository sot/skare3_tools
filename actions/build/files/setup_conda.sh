if [ -z "$CONDA_PASSWORD" ]
then
    echo Conda password needs to be given as environmental variable CONDA_PASSWORD
    exit 100
fi

wget=`which wget`
if [[ $wget ]]
then
  echo wget https://repo.anaconda.com/miniconda/Miniconda3-4.3.21-MacOSX-x86_64.sh
  wget https://repo.anaconda.com/miniconda/Miniconda3-4.3.21-MacOSX-x86_64.sh
else
  echo curl -O https://repo.anaconda.com/miniconda/Miniconda3-4.3.21-MacOSX-x86_64.sh
  curl -O https://repo.anaconda.com/miniconda/Miniconda3-4.3.21-MacOSX-x86_64.sh
fi

sed -e "s/\${CONDA_PASSWORD}/${CONDA_PASSWORD}/g" ./skare3_tools/actions/build/files/condarc.in > $HOME/.condarc
bash Miniconda3-4.3.21-MacOSX-x86_64.sh -b
export PATH=${HOME}/miniconda3/bin:$PATH
conda install python=3.6.2 conda=4.3.21 -q --yes
conda install ska3_builder -q --yes

