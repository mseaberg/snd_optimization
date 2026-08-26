#!/bin/bash

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config)
            CONFIG="$2"
            shift
            shift
            ;;
        -e|--exp)
            EXP="$2"
            shift
            shift
            ;;
    esac
done

set -- "${POSITIONAL_ARGS[@]}"

home_path=/cds/home/s/seaberg
source $home_path/psana_setup3.sh
#source /reg/g/psdm/etc/psconda.sh -py2
cd $home_path/Python/shmem_pv
python -u mpi_control.py -e $EXP -c $CONFIG -l True

