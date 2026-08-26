# run these commands in the "amoh1315" directory

# mpirun -n 2 python mpi_driver.py  exp=xpptut15:run=54 cspad -n 10
# in batch:
# bsub -q psanaq -n 2 -o %J.log -a mympi python mpi_driver.py exp=xpptut15:run=54

from data_processing import runmaster, runclient
import config_util


from mpi4py import MPI
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
assert size>1, 'At least 2 MPI ranks required'
numClients = size-1

import argparse
#import ConfigParser
parser = argparse.ArgumentParser()
parser.add_argument("-b","--hutch", help="hutch name",type=str)
parser.add_argument("-r","--run", help="run number from DAQ",default="1",type=str)
parser.add_argument("-n","--noe",help="number of events, all events=0",default=-1, type=int)
parser.add_argument("-e","--experiment",help="experiment name",type=str)
parser.add_argument("-c","--config",help="config file name",default='wfs',type=str)
parser.add_argument("-s","--server",help="server name",type=str)
parser.add_argument("-l","--live",help="run live",type=bool,default=False)
args = parser.parse_args()

pars = config_util.parse_config(args.config)

if rank==0:
    runmaster(numClients,args,pars,comm,rank,size)
else:
    runclient(args,pars,comm,rank,size)

MPI.Finalize()
