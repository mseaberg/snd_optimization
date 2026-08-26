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

from bluesky.suspenders import SuspendFloor

duration = 2



IP_x = AvgSignal(EpicsSignalRO('XCS:USER:SND:X_CENTROID_SHMEM',name='IP_x'),int(60*1.5),duration,name='IP_x')
IP_y = AvgSignal(EpicsSignalRO('XCS:USER:SND:Y_CENTROID_SHMEM',name='IP_y'),int(60*1.5),duration,name='IP_y')
IP_intensity = AvgSignal(EpicsSignalRO('XCS:USER:SND:INTENSITY_SHMEM',name='IP_intensity'),int(60*1.5),duration,name='IP_intensity')
dd_x = AvgSignal(EpicsSignalRO('XCS:GIGE:SND:DD:X_BM_CTR',name='dd_x'),9,duration,name='dd_x')
dd_y = AvgSignal(EpicsSignalRO('XCS:GIGE:SND:DD:Y_BM_CTR',name='dd_y'),9,duration,name='dd_y')
do_x = AvgSignal(EpicsSignalRO('XCS:GIGE:25:X_BM_CTR',name='do_x'),9,duration,name='do_x')
do_y = AvgSignal(EpicsSignalRO('XCS:GIGE:25:Y_BM_CTR',name='do_y'),9,duration,name='do_y')

ipm4 = AvgSignal(EpicsSignalRO('XCS:SB1:BMMON:SUM',name='ipm4'),int(1.5*120),duration,name='ipm4')

def make_run_engine(with_bec=True):
    RE = RunEngine({})
    if with_bec:
        RE.subscribe(BestEffortCallback())
    return RE

snd = SplitAndDelay('XCS:SND', name='snd')
time.sleep(1)

RE = make_run_engine()

sus = SuspendFloor(ipm4,5000)
RE.install_suspender(sus)


data_delay = []
data_IP_x = []
data_IP_y = []
data_IP_intensity = []
data_dd_x = []
data_dd_y = []
data_do_x = []
data_do_y = []

def collect(name, doc):
    if name == "event":
        data_delay.append(doc["data"]['snd_delay_readback'])
        data_IP_x.append(doc["data"][IP_x.name])
        data_IP_y.append(doc["data"][IP_y.name])
        data_IP_intensity.append(doc["data"][IP_intensity.name])
        data_dd_x.append(doc["data"][dd_x.name])
        data_dd_y.append(doc["data"][dd_y.name])
        data_do_x.append(doc["data"][do_x.name])
        data_do_y.append(doc["data"][do_y.name])

token = RE.subscribe(collect)
time.sleep(0.1)
positions = np.linspace(-10,120,651)
A = 14.376
T = 2.364
phi = -.543
p1 = 0.371
pix_per_urad = 8.7
chi_pix_per_urad = -2.685
correction = -(A*np.sin(2*np.pi/T*positions+phi)+p1*positions)/pix_per_urad*1e-6*180/np.pi

lut_data = np.load('hxrsd_delay_wobble_run_10.npz')
delay_lut = lut_data['delay']
dx_lut = lut_data['dx']
dy_lut = lut_data['dy']+50
dx_interp = np.interp(positions, delay_lut, dx_lut)
dy_interp = np.interp(positions, delay_lut, dy_lut)
d_theta = dx_interp/pix_per_urad*1e-6*180/np.pi
d_chi = dy_interp/chi_pix_per_urad*1e-6*180/np.pi

t1_chi2_start = 0.497229
t4_chi2_start = 0.994609
t1_chi2_end = 0.473119
t4_chi2_end = 1.02385

t1_th2_pos = np.linspace(17.251931655141476,17.252372871275213,651)
t1_th2_pos -= t1_th2_pos[0]
t4_th2_pos = np.linspace(17.253296784634976,17.25286577539392,651)
t4_th2_pos -= t4_th2_pos[0]
t1_chi2_pos = np.linspace(t1_chi2_start,t1_chi2_end,651)
t1_chi2_pos -= t1_chi2_pos[0]
t4_chi2_pos = np.linspace(t4_chi2_start,t4_chi2_end,651)
t4_chi2_pos -= t4_chi2_pos[0]

#RE(rel_list_scan([IP_x,IP_y,IP_intensity,dd_x,dd_y,do_x,do_y], snd.delay, positions, snd.t1.th2, d_theta, snd.t1.chi2, d_chi))
RE(rel_list_scan([IP_x,IP_y,IP_intensity,dd_x,dd_y,do_x,do_y], snd.delay, positions, snd.t1.chi2, t1_chi2_pos, snd.t4.chi2,t4_chi2_pos,snd.t1.th2,t1_th2_pos,snd.t4.th2,t4_th2_pos))

RE.unsubscribe(token)

filepath = '/cds/home/opr/xcsopr/experiments/xcs101611626/delay_scans/'
timestamp = str(int(datetime.now().timestamp()))
filename = 'delay_scan_{}'.format(timestamp)
data_delay = np.array(data_delay)
data_IP_x = np.array(data_IP_x)
data_IP_y = np.array(data_IP_y)
data_IP_intensity = np.array(data_IP_intensity)
data_dd_x = np.array(data_dd_x)
data_dd_y = np.array(data_dd_y)
data_do_x = np.array(data_do_x)
data_do_y = np.array(data_do_y)

plt.figure()
plt.plot(data_delay,data_IP_x)
plt.figure()
plt.plot(data_delay,data_IP_intensity)
plt.show()

print(filepath+filename)
np.savez(filepath+filename,delay=data_delay,IP_x=data_IP_x,IP_y=data_IP_y,IP_intensity=data_IP_intensity,dd_x=data_dd_x,dd_y=data_dd_y,do_x=data_do_x,do_y=data_do_y)
