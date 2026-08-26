import numpy as np
import time
from pyqtgraph.Qt import QtCore
from ophyd import EpicsSignalRO as SignalRO
from ophyd import EpicsSignal as Signal
from pcdsdevices.signal import AvgSignal
from undpoint import UndPointDelta2D
import os
import json

local_path = os.path.dirname(os.path.abspath(__file__))

class Alignment(QtCore.QObject):

    sig_finished = QtCore.pyqtSignal()

    def __init__(self, imager_name: str, curr_imager_dict: dict, calibrate=False, hutch=None):
        """
        Parameters:
            curr_imager_dict: dict loaded from json file
        """
        super(Alignment, self).__init__()

        self.imager_name = imager_name
        self.imager_prefix = curr_imager_dict['prefix']

        self.hutch = hutch
        self.mirror_prefix = curr_imager_dict['mirror']
        self.mirror = Mirror(self.mirror_prefix)
        self.undulator = None
        self.calibrate = calibrate
        # check if calibration exists in the file
        if 'calib_x' in curr_imager_dict.keys():
            self.calib_x = float(curr_imager_dict['calib_x'])
            # force calibration if calib_x=0
            if self.calib_x == 0:
                self.calibrate = True
        else:
            self.calib_x = 0
            self.calibrate = True
        # check for calib_y in file
        if 'calib_y' in curr_imager_dict.keys():
            self.calib_y = float(curr_imager_dict['calib_y'])
            # calibrate if missing for mfx
            if self.calib_y == 0 and self.hutch == 'mfx':
                self.calibrate = True
        else:
            self.calib_y = 0
            self.calibrate = True

        if 'tol' in curr_imager_dict.keys():
            self.tol = float(curr_imager_dict['tol'])
        else:
            self.tol = 100
        self.error_x= None
        self.new_error_x= None
        self.error_y = None
        self.new_error_y = None
        self.mirror_start = None
        self.undx_total = None
        self.undy_total = None

        if self.mirror_prefix == 'und' or self.hutch == 'mfx':
            # relative undulator pointing object
            self.undulator = UndPointDelta2D(prefix="MFX:USER:MCC:UND",name='undulator')

        # logic related to camera PV names
        if 'L2' in self.imager_prefix:
            self.cam_name = self.imager_prefix + 'CAM:01:'
        elif 'IM' in self.imager_prefix:
            self.cam_name = self.imager_prefix + 'CAM:'
        else:
            self.cam_name = self.imager_prefix

        # target positions for alignment
        self.x_target = SignalRO(self.cam_name+'X_RTCL_CTR').get()
        self.y_target = SignalRO(self.cam_name+'Y_RTCL_CTR').get()
        # PVs corresponding to calculated beam centroid
        self.x_centroid = SignalRO(self.cam_name+'X_BM_CTR')
        self.y_centroid = SignalRO(self.cam_name+'Y_BM_CTR')

        # AvgSignals for beam centroid
        self.avg_x_centroid = AvgSignal(self.x_centroid, 10, 2, name='avg_x_centroid')
        self.avg_y_centroid = AvgSignal(self.y_centroid, 10, 2, name='avg_y_centroid')

    def change_duration(self, duration=2):
        # AvgSignals for beam centroid
        self.avg_x_centroid = AvgSignal(self.x_centroid, duration*5, duration, name='avg_x_centroid')
        self.avg_y_centroid = AvgSignal(self.y_centroid, duration*5, duration, name='avg_y_centroid')


    def get_centroid(self):
        """
        Method to get updated beam centroids
        """
        status_x = self.avg_x_centroid.trigger()
        status_y = self.avg_y_centroid.trigger()
        all_status = [status_x, status_y]

        done_reading = False

        # wait until duration is finished
        while not done_reading:
            time.sleep(0.1)
            done_reading = all([status.done for status in all_status])
        out_x = self.avg_x_centroid.get()
        out_y = self.avg_y_centroid.get()

        return out_x, out_y

    def run(self):
        """
        Method to choose between undulator and mirror pointing
        """

        self.running = True
        if self.mirror_prefix == 'und':
            self._und_run()
        elif self.hutch=='mfx':
            self._combined_run()
        else:
            self._run()

    def _run(self):
        """
        Entry point for mirror adjustment
        """

        if self.running:

            # check centroid before moving anything
            cen_x, cen_y = self.get_centroid()
            print(cen_x - self.x_target)

            self.error_x = cen_x - self.x_target
            # move mirror slightly for calibration

            print(self.mirror.pitch.get())
            self.mirror_start = self.mirror.pitch.get()
            if self.calibrate:
                self.change_duration(duration=5)
                cen_x, cen_y = self.get_centroid()
                print(cen_x - self.x_target)

                self.error_x = cen_x - self.x_target

                print('moving mirror positive')
                self.mirror.pitch.mvr(1, wait=True)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                # calculate um/urad
                calib1 = (self.new_error_x - self.error_x) / 1

                # update old position error
                self.error_x = np.copy(self.new_error_x)

                print('moving mirror negative')
                self.mirror.pitch.mvr(-1, wait=True)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                # calculate um/urad
                calib2 = (self.new_error_x - self.error_x) / (-1)
                self.calib_x = (calib1+calib2)/2
                print('calibration: {} um/urad'.format(self.calib_x))
                # save the calibration to file
                self.save_calibration()
                self.change_duration(duration=2)
            else:
                self.new_error_x = np.copy(self.error_x)
            # start loop for mirror adjustment
            self._update()
        else:
            self.sig_finished.emit()

    def _update(self):
        """
        Loop method for adjusting mirror pointing
        """
        # only run if not cancelled
        if self.running:
            # check if beam centroid is valid or not. Cancel if not
            if np.isnan(self.new_error_x):
                print('Beam down? Canceling...')
                self.mirror.pitch.mv(self.mirror_start, wait=True)
                self.sig_finished.emit()
                return
            try:
                adj = -self.new_error_x/ self.calib_x* 0.9
            except ZeroDivisionError:
                print('problem with calibration')
                self.mirror.pitch.mv(self.mirror_start, wait=True)
                self.sig_finished.emit()
                return

            print('Adjusting {} by {}'.format(self.mirror.name, adj))
            # ensure adjustments aren't too large
            if np.abs(adj)>2:
                adj = np.sign(adj)*2
            self.mirror.pitch.mvr(adj, wait=True)
            cen_x, cen_y = self.get_centroid()
            self.new_error_x= cen_x - self.x_target
            print('Error from target: {}'.format(self.new_error_x))
            # make another adjustment if we are more than 20um from the target
            if np.abs(self.new_error_x)>self.tol:
                QtCore.QTimer.singleShot(200, self._update)
            else:
                print('alignment completed')

                self.sig_finished.emit()
        else:
            print('Alignment canceled, moving back to start')
            self.mirror.pitch.mv(self.mirror_start, wait=True)
            self.sig_finished.emit()

    def _und_run(self):
        """
        Method for undulator-based pointing
        """


        if self.running:

            # check centroid before moving anything
            cen_x, cen_y = self.get_centroid()
            print(cen_x - self.x_target)

            self.error_x= cen_x - self.x_target
            self.error_y = cen_y - self.y_target
            if self.calibrate:
                self.change_duration(duration=5)
                cen_x, cen_y = self.get_centroid()

                self.error_x = cen_x - self.x_target
                self.error_y = cen_y - self.y_target

                print('moving undulator positive')
                self.undulator.move(position=(50,50),wait=True)
                time.sleep(1)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                self.new_error_y = cen_y - self.y_target
                # calculate calibration for horizontal
                calib_x1 = (self.new_error_x - self.error_x) / 50
                # calculate calibration for vertical
                calib_y1 = (self.new_error_y - self.error_y) / 50

                # update old position error
                self.error_x = np.copy(self.new_error_x)
                self.error_y = np.copy(self.new_error_y)

                print('moving undulator negative')
                self.undulator.move(position=(-50, -50), wait=True)
                time.sleep(1)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                self.new_error_y = cen_y - self.y_target
                # calculate calibration for horizontal
                calib_x2 = (self.new_error_x - self.error_x) / (-50)
                # calculate calibration for vertical
                calib_y2 = (self.new_error_y - self.error_y) / (-50)

                self.calib_x = (calib_x1 + calib_x2) / 2
                self.calib_y = (calib_y1 + calib_y2) / 2
                print('calibration: {} um/um'.format(self.calib_x))
                print('calibration for y: {} um/um'.format(self.calib_y))
                # save the calibration to file
                self.save_calibration()
                self.change_duration(duration=2)
            else:
                self.new_error_x = np.copy(self.error_x)
                self.new_error_y = np.copy(self.error_y)
            self._und_update()
        else:
            self.sig_finished.emit()

    def _und_update(self):
        """
        Loop function for undulator pointing
        """
        if self.running:
            # cancel if centroids are not valid
            if np.isnan(self.new_error_x):
                print('Beam down? Canceling...')
                self.sig_finished.emit()
                return
            try:
                adj = -self.new_error_x/ self.calib_x* 0.9
                adj_y = -self.new_error_y / self.calib_y * 0.9
            except ZeroDivisionError:
                print('problem with calibration')
                self.sig_finished.emit()
                return


            print('Adjusting horizontal by {}um'.format(adj))
            print('Adjusting vertical by {}um'.format(adj_y))
            # Enforce moves to be less than 50um
            if np.abs(adj)>50:
                adj = np.sign(adj)*50
            if np.abs(adj_y)>50:
                adj_y = np.sign(adj_y)*50
            # make the adjustment and wait for move to finish
            self.undulator.move((adj,adj_y), wait=True)
            time.sleep(.5)
            cen_x, cen_y = self.get_centroid()
            self.new_error_x= cen_x - self.x_target
            self.new_error_y = cen_y - self.y_target
            print('Error from X target: {}um'.format(self.new_error_x))
            print('Error from Y target: {}um'.format(self.new_error_y))
            # make another adjustment if we are not within the tolerance
            if np.abs(self.new_error_x)>self.tol or np.abs(self.new_error_y)>self.tol:
                QtCore.QTimer.singleShot(200, self._und_update)
            else:
                print('alignment completed')

                self.sig_finished.emit()
        else:
            self.sig_finished.emit()

    def _combined_run(self):
        """
        Entry point for mirror adjustment
        """

        if self.running:

            # check centroid before moving anything
            cen_x, cen_y = self.get_centroid()
            print(cen_x - self.x_target)

            self.error_x = cen_x - self.x_target
            self.error_y = cen_y - self.y_target
            # move mirror slightly for calibration

            self.mirror_start = self.mirror.pitch.get()

            if self.calibrate:
                self.change_duration(duration=5)
                cen_x, cen_y = self.get_centroid()

                self.error_x = cen_x - self.x_target
                self.error_y = cen_y - self.y_target

                print('moving mirror positive')
                self.mirror.pitch.mvr(3, wait=True)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                # calculate um/urad
                calib1 = (self.new_error_x - self.error_x) / 3

                # update old position error
                self.error_x = np.copy(self.new_error_x)
                print(self.error_x)

                print('moving mirror negative')
                self.mirror.pitch.mvr(-3, wait=True)
                cen_x, cen_y = self.get_centroid()
                self.new_error_x = cen_x - self.x_target
                # calculate um/urad
                calib2 = (self.new_error_x - self.error_x) / (-3)
                self.calib_x = (calib1+calib2)/2
                print('calibration: {} um/urad'.format(self.calib_x))
                # save the calibration to file

                print('moving undulator positive')
                self.undulator.move(position=(0, 50), wait=True)
                time.sleep(1)
                cen_x, cen_y = self.get_centroid()
                self.new_error_y = cen_y - self.y_target
                # calculate calibration for vertical
                calib_y1 = (self.new_error_y - self.error_y) / 50

                # update old position error
                self.error_y = np.copy(self.new_error_y)
                print(self.error_y)

                print('moving undulator negative')
                self.undulator.move(position=(0, -50), wait=True)
                time.sleep(1)
                cen_x, cen_y = self.get_centroid()
                self.new_error_y = cen_y - self.y_target
                # calculate calibration for vertical
                calib_y2 = (self.new_error_y - self.error_y) / (-50)
                self.calib_y = (calib_y1 + calib_y2) / 2
                print('und calibration: {} um/um'.format(self.calib_y))

                self.save_calibration()
                self.change_duration(duration=2)
            else:
                self.new_error_x = np.copy(self.error_x)
                self.new_error_y = np.copy(self.error_y)
            # start loop for mirror adjustment
            self._combined_update()
        else:
            self.sig_finished.emit()

    def _combined_update(self):
        """
        Loop method for adjusting mirror pointing
        """
        # only run if not cancelled
        if self.running:
            # check if beam centroid is valid or not. Cancel if not
            if np.isnan(self.new_error_x):
                print('Beam down? Canceling...')
                self.mirror.pitch.mv(self.mirror_start, wait=True)
                self.sig_finished.emit()
                return
            try:
                adj = -self.new_error_x/ self.calib_x* 0.9
                adj_y = -self.new_error_y / self.calib_y * 0.9
            except ZeroDivisionError:
                print('problem with calibration')
                self.mirror.pitch.mv(self.mirror_start, wait=True)
                self.sig_finished.emit()
                return

            print('Adjusting {} by {}'.format(self.mirror.name, adj))
            print('Adjusting undulators vertically by {}um'.format(adj_y))
            # ensure adjustments aren't too large
            if np.abs(adj)>2:
                adj = np.sign(adj)*2
            if np.abs(adj_y)>50:
                adj_y = np.sign(adj_y)*50
            self.mirror.pitch.mvr(adj, wait=True)
            self.undulator.move((0,adj_y),wait=True)
            time.sleep(0.5)
            cen_x, cen_y = self.get_centroid()
            self.new_error_x = cen_x - self.x_target
            self.new_error_y = cen_y - self.y_target
            print('Error from X target: {}'.format(self.new_error_x))
            print('Error from Y target: {}um'.format(self.new_error_y))
            # make another adjustment if we are more than 20um from the target
            if np.abs(self.new_error_x)>self.tol or np.abs(self.new_error_y)>self.tol:
                QtCore.QTimer.singleShot(200, self._combined_update)
            else:
                print('alignment completed')

                self.sig_finished.emit()
        else:
            print('Alignment canceled, moving mirror back to start')
            self.mirror.pitch.mv(self.mirror_start, wait=True)
            self.sig_finished.emit()

    def cancel(self):
        self.running = False

    def save_calibration(self):
        """
                Method to save the current image orientation.
                """
        # get current file contents
        print(local_path)
        try:
            with open(local_path + '/imager_info.json') as json_file:
                data = json.load(json_file)

        except json.decoder.JSONDecodeError:
            # give up if there's no file for now...
            pass

        # list of beamlines
        line_list = [key for key in data]

        # find imager in imager_info dict
        curr_line = None
        for line in line_list:
            if self.imager_name in data[line].keys():
                curr_line = line
                break

        data[curr_line][self.imager_name]['calib_x'] = self.calib_x
        data[curr_line][self.imager_name]['calib_y'] = self.calib_y

        # write to the file under the corresponding imager field
        with open(local_path + '/imager_info.json', 'w') as outfile:
            json.dump(data, outfile, indent=4)


class Motor():
    """
    Generic class for epics motor
    """
    def __init__(self, pv_name):
        self.setpoint = Signal(pv_name)
        self.rbv = SignalRO(pv_name+'.RBV')
        self.moving = SignalRO(pv_name + '.MOVN')

    def mv(self, target, wait=True):
        self.set(target)
        if wait:
            # while np.abs(self.get() - target) > tol:
            #    time.sleep(0.2)
            moving_status = True
            while moving_status:
                moving_status = self.moving.get()
                time.sleep(0.1)
        print('move completed')

    def mvr(self, adjustment, wait=True):
        target = self.get() + adjustment
        self.mv(target, wait=wait)

    def get(self):
        return self.rbv.get()

    def set(self, target):
        self.setpoint.set(target)

class Attenuate(QtCore.QObject):
    """
    Simple class for controlling AT2L0 in a separate thread
    """
    sig_finished = QtCore.pyqtSignal()

    def __init__(self):
        super(Attenuate, self).__init__()
        self.calculate = Signal('AT2L0:CALC:SYS:Run')
        self.apply = Signal('AT2L0:CALC:SYS:ApplyConfiguration')
        self.status = None

    def run(self):
        # run calculation
        self.status = self.calculate.set(1)
        self.status.wait()

        # apply configuration
        self.status = self.apply.set(1)
        self.status.wait()

        self.sig_finished.emit()


class Mirror():
    """
    Stripped-down class for HOMS mirror
    """

    def __init__(self, mirror_base, name=None):
        # initialize attributes
        self.name = name
        self.mirror_base = mirror_base
        self.motor_base = self.mirror_base + ':MMS'
        # initialize epics signals
        self.pitch = Motor(self.motor_base+':PITCH')
