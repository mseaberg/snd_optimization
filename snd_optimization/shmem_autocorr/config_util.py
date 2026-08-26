import configparser
import os
import numpy as np

def get_immediate_subdirectories(a_dir,hutch):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name)) and
            name[:3].lower()==hutch.lower()]

def parse_config(configFile):
    print(configFile)
    config = configparser.ConfigParser()
    config.read(configFile)
    pars = {}
    #pars['exp_name'] = config.get('Main','exp_name')
    pars['hutch'] = config.get('Main','hutch')
    pars['update_events'] = config.getint('Update','update_events')
    xmin = config.getint('Processing','xmin')
    xmax = config.getint('Processing','xmax')
    ymin = config.getint('Processing','ymin')
    ymax = config.getint('Processing','ymax')
    pars['pixel'] = config.getfloat('Setup','pixel')
    pars['roi'] = [xmin,xmax,ymin,ymax]
    pars['detName'] = config.get('Setup','detName')
    pars['ipmName'] = config.get('Setup','ipmname')
    pars['energy'] = config.getfloat('Main','energy')
    pars['thresh'] = config.getint('Processing','thresh')
    pars['ipm_threshold'] = config.getint('Processing','ipm_threshold')
    #det_str = config.get('Setup','detnames')
    #pars['detnames'] = [x.strip() for x in det_str.split(',')]


    return pars


