#!/bin/bash
source /reg/g/psdm/etc/psconda.sh

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--nodes)
            NODES="$2"
            shift
            shift
            ;;
        -n|--num)
            NUM="$2"
            shift
            shift
            ;;
        -e|--exp)
            EXP="$2"
            shift
            shift
            ;;
        -c|--config)
            CONFIG="$2"
            shift
            shift
            ;;
    esac
done

set -- "${POSITIONAL_ARGS[@]}"

`which mpirun` --oversubscribe -H $NODES -n $NUM ./run_multiple_nodes.sh -e $EXP -c $CONFIG
