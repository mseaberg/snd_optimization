#!/bin/env bash
#source /cds/home/s/seaberg/setup_python.sh
#source /reg/g/pcds/pyps/apps/hutch-python/xcs/xcsenv
#source /reg/g/pcds/pyps/apps/hutch-python/tmo/tmoenv
#source /reg/g/pcds/pyps/apps/hutch-python/xpp/xppenv

#source /cds/home/s/seaberg/beamlineconda.sh
#!!! following two lines likely need to change.
source /reg/g/pcds/pyps/apps/hutch-python/xcs/xcsenv
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/snd_exp/PPM_screen
#!!!
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS=1

#cd /cds/home/s/seaberg/TMO_IP2/Commissioning_Tools/PPM_centroid
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )

cd "$parent_path"
cd ../snd_optimization/camera_centroid

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM3L0"
fi

python run_interface.py -c $IMAGER &
