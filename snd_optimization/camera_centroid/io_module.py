#!/usr/bin/env python
# coding: utf-8

import numpy as np
import os
from pcdsdevices.areadetector.detectors import PCDSAreaDetector
from subprocess import check_output
from pcdsdevices.pim import PPM, XPIM
from epics import PV
from elog import ELog, HutchELog
import textwrap
import time

class ImagerHdf5():
    # taken from /reg/g/pcds/pyps/apps/hutch-python/xcs/experiments/x43118.py
    def __init__(self, prefix=None, name=None):

        if 'MONO' not in prefix or 'CVV' not in prefix:
            detector_prefix = prefix + 'CAM:'
        else:
            detector_prefix = prefix

        imager = PCDSAreaDetector(detector_prefix, name=name)

        self.name = name
        self.prefix = prefix
        try:
            self.imagerh5 = imager.hdf51
            self.imager = imager.cam
        except:
            self.imagerh5 = None
            self.imager = None
            
    def setImager(self, imager):
        self.imagerh5 = imager.hdf51
        self.imager = imager.cam
        
    def stop(self):
        self.imagerh5.enable.set(0)

    def status(self):
        print('Enabled',self.imagerh5.enable.get())
        print('File path',self.imagerh5.file_path.get())
        print('File name',self.imagerh5.file_name.get())
        print('File template (should be %s%s_%d.h5)',self.imagerh5.file_template.get())

        print('File number',self.imagerh5.file_number.get())
        print('Frame to capture per file',self.imagerh5.num_capture.get())
        print('autoincrement ',self.imagerh5.auto_increment.get())
        print('file_write_mode ',self.imagerh5.file_write_mode.get())
        #IM1L0:XTES:CAM:HDF51:Capture_RBV 0: done, 1: capturing
        print('captureStatus ',self.imagerh5.capture.get())

    def prepare(self, baseName=None, pathName=None, nImages=None, nSec=None):
        if self.imagerh5.enable.get() != 'Enabled':
            self.imagerh5.enable.put(1)
        iocdir=self.imager.prefix.split(':')[0].lower()
        if pathName is not None:
            self.imagerh5.file_path.set(pathName)
        #elif len(self.imagerh5.file_path.get())==0:
        else:
            #this is a terrible hack.
            iocdir=self.imager.prefix.split(':')[0].lower()
            camtype='opal'
            if (self.imager.prefix.find('PPM')>0): camtype='gige'
            self.imagerh5.file_path.put('/reg/d/iocData/ioc-%s-%s/hdf5/'%(iocdir, camtype))
        if baseName is not None:
            # check imager state
            #state = self.imager_mms.target.position
            self.imagerh5.file_name.put('%s_%s' % (self.name, baseName))
        else:
            expname = check_output('get_curr_exp').decode('utf-8').replace('\n','')
            try:
                lastRunResponse = check_output('get_lastRun').decode('utf-8').replace('\n','')
                if lastRunResponse == 'no runs yet': 
                    runnr=0
                else:
                    runnr = int(check_output('get_lastRun').decode('utf-8').replace('\n',''))
            except:
                runnr = 0
            self.imagerh5.file_name.put('%s_%s_Run%03d'%(iocdir,expname, runnr+1))

        self.imagerh5.file_template.put('%s%s_%d.h5')
        #check that file to be written does not exist
        already_present = True
        while (already_present):
            fnum = self.imagerh5.file_number.get()
            fname = self.imagerh5.file_path.get() + self.imagerh5.file_name.get() + \
                    '_%d'%fnum + '.h5'
            if os.path.isfile(fname):
                print('File %s already exists'%fname)
                self.imagerh5.file_number.put(1 + fnum)
                time.sleep(0.2)
            else:
                already_present = False

        self.imagerh5.auto_increment.put(1)
        self.imagerh5.file_write_mode.put(2)
        if nImages is not None:
            self.imagerh5.num_capture.put(nImages)
        if nSec is not None:
            if self.imager.acquire.get() > 0:
                rate = self.imager.array_rate.get()
                self.imagerh5.num_capture.put(nSec*rate)
            else:
                print('Imager is not acquiring, cannot use rate to determine number of recorded frames')

    def write(self, nImages=None):
        if nImages is not None:
            self.imagerh5.num_capture.put(nImages)
        if self.imager.acquire.get() == 0:
            self.imager.acquire.put(1)
        self.imagerh5.capture.put(1)

    def write_wait(self, nImages=None):
        if nImages is not None:
            self.imagerh5.num_capture.put(nImages)
        if self.imager.acquire.get() == 0:
            self.imager.acquire.put(1)
        self.imagerh5.capture.put(1)
        time.sleep(0.25)
        while (self.imagerh5.num_capture.get() > 
               self.imagerh5.num_captured.get()):
            time.sleep(0.25)

    def write_stop(self):
        self.imagerh5.capture.put(0)


class ElogHandler:
    def __init__(self):
        # check which hutch we're in
        
        try:
            #expname = check_output('get_curr_exp').decode('utf-8').replace('\n','')
            #hutch = expname[:3].upper()
            hutch = check_output('hostname').decode('utf-8').replace('\n','')[:3].upper()
            print(hutch)
        except:
            hutch = None

        kwargs = dict()
        
        try:
            if hutch=='RIX':
                kwargs['station'] = '2'
                self.elog = HutchELog.from_conf(hutch, **kwargs)
            else:
                self.elog = HutchELog.from_conf(hutch, **kwargs)
        except:
            print('unable to connect to experiment elog')
            self.elog = None

        if hutch=='RIX' or hutch=='TMO':
            fee_name = 'kfe'
        else:
            fee_name = 'lfe'

        try:
            user = '%sopr' % (hutch.lower())
            self.fee_elog = ELog(logbooks={"experiment": fee_name},user=user,pw='pcds')

        except:
            print('unable to connect to %s elog' % fee_name)
            self.fee_elog = None
   
    def stats_message(self, imager_name, controls, stats, energy):
        # get stats
        xcentroid = stats.xCentroidLineEdit.text()
        ycentroid = stats.yCentroidLineEdit.text()
        xwidth = stats.xWidthLineEdit.text()
        ywidth = stats.yWidthLineEdit.text()
        photon_energy = energy.text()
        xref = stats.xReferenceLabel.text()
        yref = stats.yReferenceLabel.text()

        # get imager state
        state = controls.yStateReadback.text()

        message = textwrap.dedent("""{imager} is in the {state} position. The photon energy is {energy}.
            Horizontal centroid: {xcentroid}\u03BCm
            Vertical centroid: {ycentroid}\u03BCm
            Horizontal width: {xwidth}\u03BCm
            Vertical width: {ywidth}\u03BCm
            Reference point: {xref}, {yref}""".format(imager=imager_name, 
                                               energy=photon_energy, state=state, 
                                               xcentroid=xcentroid, ycentroid=ycentroid,
                                               xwidth=xwidth, ywidth=ywidth, xref=xref, yref=yref))
        return message

    def window_grab(self):
        # get screenshot
        window_id = check_output('xdotool getactivewindow',shell=True).decode('utf-8').replace('\n','')
        check_output('import -window {} ~/trajectory/window_grab.jpg'.format(window_id), shell=True)

        file_path = check_output('cd ~/trajectory; pwd',shell=True).decode('utf-8').replace('\n','') + '/'
       
        full_name = file_path + 'window_grab.jpg'

        return full_name

    def post_stats(self, imager_name, controls, stats, energy):
        # get stats
        message = self.stats_message(imager_name, controls, stats, energy)


        if self.elog is not None:
            attachment_name = self.window_grab()
            self.elog.post(message, attachments=[attachment_name],tags=['GoldenTrajectory'],
                    experiment=False,facility=True)
        else:
            print('elog is not connected, not posted')
                    
    def post_trajectory(self, pointing, imager_name, controls, stats, energy, image_file, data_file):
        
        # get stats
        message = self.stats_message(imager_name, controls, stats, energy)

        file_message = textwrap.dedent("""10 raw images saved to {}.
                                    Calculated values and pv's saved to {}.""".format(
                                        image_file, data_file))

        if pointing:
            pointing_message = 'Beam trajectory is set.\n'
        else:
            pointing_message = 'Beam trajectory is NOT set.\n'

        full_message = pointing_message + message + '\n' + file_message


        if self.elog is not None:
            attachment_name = self.window_grab()
            self.elog.post(full_message, attachments=[attachment_name], 
                    tags=['GoldenTrajectory', imager_name], experiment=True, facility=True)
        else:
            print('experiment elog is not connected, not posted')

        if self.fee_elog is not None:
            self.fee_elog.post(full_message, attachments=[attachment_name], 
                    tags=['GoldenTrajectory', imager_name])
        else:
            print('FEE elog is not connected, not posted')



