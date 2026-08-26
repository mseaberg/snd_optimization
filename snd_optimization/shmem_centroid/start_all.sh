source /reg/g/psdm/etc/psconda.sh

# find available nodes
NODES=`wherepsana`
# get name of first node
IND=$((`expr index "$NODES" ,`-1))
NODE1=`expr substr $NODES 1 $IND`
# get number of cores (nodes*8)
RES="${NODES//[^,]}"
NUM=$(((${#RES}+1)*8))
echo $NODES
echo $NODE1
echo $NUM
# get directory where this script lives
HEREDIR=`dirname $(readlink -f $0)`
# get current experiment for calib directory
EXP=`get_curr_exp`
# define which configuration file to read from
CONFIG=config.cfg

# start plots
psplot -s $NODE1 centroid_image &

# start shared memory process
ssh $NODE1 "source /reg/g/psdm/etc/psconda.sh; cd $HEREDIR; source start_shmem2.sh -s $NODES -n $NUM -e $EXP -c $CONFIG"
