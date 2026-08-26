#!/bin/env bash
#cd /reg/g/pcds/pyps/apps/hutch-python/rix
source /reg/g/pcds/pyps/apps/hutch-python/rix/rixenv
#export PYTHONPATH="/reg/g/pcds/pyps/apps/hutch-python/rix:/reg/g/pcds/pyps/apps/hutch-python/rix/dev/devpath:/cds/home/s/seaberg/Python/lcls_beamline_toolbox"
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/Python/lcls_beamline_toolbox

chmod -R u+w ~/.cache/scikit-image

HERE=`dirname $(readlink -f $0)`

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM2K0"
fi

python $HERE/../run_interface.py -c $IMAGER &
