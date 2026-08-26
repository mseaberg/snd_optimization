#!/bin/env bash
source /reg/g/pcds/pyps/apps/hutch-python/cxi/cxienv
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/Python/lcls_beamline_toolbox

HERE=`dirname $(readlink -f $0)`

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM2L0"
fi

python $HERE/../run_interface.py -c $IMAGER &
