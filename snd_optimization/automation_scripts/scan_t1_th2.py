from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace
import time
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from bluesky import RunEngine
from bluesky import plan_stubs as bps
#import bluesky.plans as bp

from bluesky.plans import rel_list_scan
from bluesky.callbacks.best_effort import BestEffortCallback
from databroker import Broker
from ophyd.signal import EpicsSignal
from ophyd.signal import EpicsSignalRO
from PyQt5 import QtWidgets, uic
from pydm.widgets import PyDMPushButton
from scipy.optimize import curve_fit
from pcdsdevices.signal import AvgSignal
sys.path.append('/reg/g/pcds/pyps/apps/hutch-python/xcs/dev')
from hxrsnd.sndsystem import SplitAndDelay

duration = 4.5


IP_x = AvgSignal(EpicsSignalRO('XCS:USER:SND:X_CENTROID_SHMEM',name='IP_x'),60,duration,name='IP_x')
IP_y = AvgSignal(EpicsSignalRO('XCS:USER:SND:Y_CENTROID_SHMEM',name='IP_y'),60,duration,name='IP_y')
IP_intensity = AvgSignal(EpicsSignalRO('XCS:USER:SND:INTENSITY_SHMEM',name='IP_intensity'),60,duration,name='IP_intensity')
dd_x = AvgSignal(EpicsSignalRO('XCS:GIGE:SND:DD:X_BM_CTR',name='dd_x'),20,duration,name='dd_x')
dd_y = AvgSignal(EpicsSignalRO('XCS:GIGE:SND:DD:Y_BM_CTR',name='dd_y'),20,duration,name='dd_y')
do_x = AvgSignal(EpicsSignalRO('XCS:GIGE:25:X_BM_CTR',name='do_x'),20,duration,name='do_x')
do_y = AvgSignal(EpicsSignalRO('XCS:GIGE:25:Y_BM_CTR',name='do_y'),20,duration,name='do_y')

t1_chi2 = EpicsSignal('XCS:SND:T1:CHI2:CMD:TARGET',name='t1_chi2')
t4_chi2 = EpicsSignal('XCS:SND:T4:CHI2:CMD:TARGET',name='t4_chi2')

def make_run_engine(with_bec=True):
    RE = RunEngine({})
    if with_bec:
        RE.subscribe(BestEffortCallback())
    return RE

snd = SplitAndDelay('XCS:SND', name='snd')
time.sleep(1)

RE = make_run_engine()


data_t4_chi2 = []
data_IP_x = []
data_IP_y = []
data_IP_intensity = []
data_dd_x = []
data_dd_y = []
data_do_x = []
data_do_y = []

def collect(name, doc):
    if name == "event":
        data_t4_chi2.append(doc["data"][t4_chi2.name])
        data_IP_x.append(doc["data"][IP_x.name])
        data_IP_y.append(doc["data"][IP_y.name])
        data_IP_intensity.append(doc["data"][IP_intensity.name])
        data_dd_x.append(doc["data"][dd_x.name])
        data_dd_y.append(doc["data"][dd_y.name])
        data_do_x.append(doc["data"][do_x.name])
        data_do_y.append(doc["data"][do_y.name])

token = RE.subscribe(collect)
time.sleep(0.1)
positions = np.linspace(-5e-6*180/np.pi,5e-6*180/np.pi,11)
RE(rel_list_scan([IP_x,IP_y,IP_intensity,dd_x,dd_y,do_x,do_y], t4_chi2, positions))
RE.unsubscribe(token)

filepath = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/'
timestamp = str(int(datetime.now().timestamp()))
filename = 't4_chi2_scan_{}'.format(timestamp)
data_t4_chi2 = np.array(data_t4_chi2)
data_IP_x = np.array(data_IP_x)
data_IP_y = np.array(data_IP_y)
data_IP_intensity = np.array(data_IP_intensity)
data_dd_x = np.array(data_dd_x)
data_dd_y = np.array(data_dd_y)
data_do_x = np.array(data_do_x)
data_do_y = np.array(data_do_y)

plt.show()

print(filepath+filename)
np.savez(filepath+filename,t4_chi2=data_t4_chi2,IP_x=data_IP_x,IP_y=data_IP_y,IP_intensity=data_IP_intensity,dd_x=data_dd_x,dd_y=data_dd_y,do_x=data_do_x,do_y=data_do_y)
