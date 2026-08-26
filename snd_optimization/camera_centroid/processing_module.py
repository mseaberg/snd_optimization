from epics import PV, caget
import numpy as np
import scipy.ndimage.interpolation as interpolate
import scipy.ndimage as ndimage
import time
#from pyqtgraph.Qt import QtCore
from PyQt5 import QtCore

#from pcdsdevices.areadetector.detectors import PCDSAreaDetector
from PPM_screen import optics
import pandas as pd
from analysis_tools import YagAlign
from datetime import datetime
from ophyd import EpicsSignalRO as SignalRO


class RunProcessing(QtCore.QObject):
    sig = QtCore.pyqtSignal()
    sig_initialized = QtCore.pyqtSignal()
    sig_finished = QtCore.pyqtSignal()

    def __init__(self, imager_dict, data_handler, averageWidget, wfs_name=None, threshold=0.1, focusFOV=10, fraction=1, focus_z=0, displayWidget=None, thread=None, hutch=None, crossWidget=None):
        super(RunProcessing, self).__init__()
        #QtCore.QThread.__init__(self)

        #self.thread = thread
        self.hutch = hutch
        imager_prefix = imager_dict['prefix']

        if crossWidget is not None:
            try:
                x1 = float(crossWidget.red_x.text())
                y1 = float(crossWidget.red_y.text())
                x2 = float(crossWidget.blue_x.text())
                y2 = float(crossWidget.blue_y.text())
                roi = [x1,y1,x2,y2]
            except:
                roi = None

        else:
            roi = None

        self.hutch_path = '/cds/home/opr/{}opr'.format(self.hutch.lower())
        if 'L2' in imager_prefix:
            self.hutch_path = '/sdf/home/x/xppopr'

        # get wavefront sensor (may be None)
        self.wfs_name = wfs_name
        self.focusFOV = focusFOV
        self.focus_z = focus_z

        # set wavefront display widget as attribute
        self.displayWidget = displayWidget

        # set threshold attribute (defaults to 0.1)
        self.threshold = threshold

        if wfs_name is not None:
            # need to make fraction more accessible...
            self.WFS_object = optics.WFS_Device(wfs_name, fraction=fraction)
        else:
            self.WFS_object = None

        # PPM object for image acquisition and processing
        self.PPM_object = optics.PPM_Device(imager_dict, average=averageWidget, threshold=self.threshold, roi=crossWidget)

        # frame rate initialization
        self.fps = 0.
        self.lastupdate = time.time()

        # initialize data handler
        self.data_handler = data_handler

        self.timer = None

        #### Start  #####################
        # self._update()

    def run(self):
       
        # check if data handler is initialized
        if self.data_handler.initialized:
            # just update PPM object
            self.data_handler.update_imager(self.PPM_object)
        else:
            self.data_handler.initialize(self.PPM_object)


        self.running = True
        self.sig_initialized.emit()

        self.timer = QtCore.QTimer()
        if self.hutch=='lfe':
            self.timer.setInterval(2000)
        else:
            self.timer.setInterval(200)
        self.timer.timeout.connect(self._update)

        #self._update()
        self.timer.start()

    def save_data(self, filename):
        self.data_handler.save_data(filename)

    def reset_plots(self):
        self.data_handler.reset_data()

    def set_orientation(self, orientation):
        self.PPM_object.set_orientation(orientation)

    def get_FOV(self):
        width = self.PPM_object.FOV
        height = np.copy(width)
        return width, height

    def _update(self):
        #time1 = time.time()
        if self.running:

            if self.displayWidget is not None:
                angle = self.displayWidget.rotation
                focusFOV = self.displayWidget.FOV
                focus_z = self.displayWidget.focus_z
            else:
                angle = 0.0
                focusFOV = 10.0
                focus_z = 0.0

            # get latest image
            self.PPM_object.get_image(angle=angle)
            # wavefront sensing
            if self.WFS_object is not None:
                wfs_data, wfs_param = self.PPM_object.retrieve_wavefront(self.WFS_object, focusFOV=focusFOV, focus_z=focus_z)
            else:
                wfs_data = None
            self.data_handler.update_data(wfs_data=wfs_data)
            # send data
            self.sig.emit()
            # keep running unless the stop button is pressed
            #if self.running:
            #    #QtCore.QTimer.singleShot(500, self._update)
            #    pass
            #else:
            #    self.PPM_object.reset_camera()
            #    self.timer.stop()
            #    self.sig_finished.emit()
            #    #self.timer.stop()
        else:
            self.PPM_object.stop()
            self.timer.stop()
            self.sig_finished.emit()
            #self.timer.stop()
        #time2 = time.time()
        #print('calculation: {}'.format(time2-time1))

    def stop(self):
        self.running = False
        #self.PPM_object.stop()


class RunRegistration(QtCore.QObject):
    sig = QtCore.pyqtSignal(dict)

    def __init__(self, yag, data_dict, averageWidget, demo, imager=None):
        super(RunRegistration, self).__init__()

        # self.my_signal = QtCore.Signal()

        # self.gui = gui

        # demo state
        self.demo = demo

        self.yag1 = yag
        self.epics_name = ''
        #if len(sys.argv) > 1:
        if imager is not None:
            self.epics_name = imager
        
        if isinstance(self.yag1, YagAlign):
            self.imager_type = 'PPM'
        else:
            self.imager_type = 'XTES'

        imager_prefix = imager

        # PPM object for image acquisition and processing
        self.PPM_object = optics.PPM_Device(imager_prefix, average=averageWidget, threshold=0.1)


        FOV_dict = {
            'IM2K4': 8.5,
            'IM3K4': 8.5,
            'IM4K4': 5.0,
            'IM5K4': 8.5,
            'IM6K4': 8.5,
            'IM1K1': 8.5,
            'IM2K1': 8.5,
            'IM1K2': 8.5,
            'IM2K2': 18.5,
            'IM3K2': 18.5,
            'IM4K2': 8.5,
            'IM5K2': 8.5,
            'IM6K2': 5.0,
            'IM7K2': 5.0,
            'IM1L1': 8.5,
            'IM2L1': 8.5,
            'IM3L1': 8.5,
            'IM4L1': 8.5,
            'IM1K3': 8.5,
            'IM2K3': 8.5,
            'IM3K3': 8.5,
            'IM3L0': 5.0
        }

        try:
            self.distance = FOV_dict[self.epics_name[0:5]] * 1e3
        except:
            self.distance = 8500.0


        self.running = True

        self.im0 = data_dict['im0']

        self.im1 = np.copy(self.im0)

        # gui.img0.setImage(im1)

        # self.counter = 0
        self.fps = 0.
        self.lastupdate = time.time()

        # self.contrast = np.zeros((4,100))
        # self.iteration = np.tile(np.linspace(-99, 0, 100),(4,1))

        self.data_dict = data_dict

        self.counter = self.data_dict['counter']

        #### Start  #####################
        self._update()

    def get_FOV(self):
        #width = self.PPM_object.FOV
        #height = np.copy(width)
        height, width = np.shape(self.im0)
        return width, height

    def stop(self):
        self.running = False

    def reset_camera(self):
        try:
            self.gige.cam.acquire.put(0, wait=True)
            self.gige.cam.acquire.put(1)
        except:
            print('no camera')

    def get_image(self):
        try:
            img = np.array(self.gige.image2.image, dtype='float')
            print(np.max(img))
            return img
        except:
            print('no image')
            return np.zeros((2048, 2048))
    def update_1d_data(self, dict_key, new_value):
        self.data_dict[dict_key] = np.roll(self.data_dict[dict_key], -1)
        self.data_dict[dict_key][-1] = new_value


    def _update(self):

        if self.running:

            # set up for testing at the moment
            if not self.demo:
            #if self.epics_name != '':

                # self.im1 = np.ones((2048,2048))*255
                self.PPM_object.get_image()
                self.im1 = self.PPM_object.profile
                self.update_1d_data('timestamps', self.PPM_object.time_stamp)

            else:
                if self.counter <= 10:
                    self.im1 = interpolate.rotate(self.im0, .1 * self.counter, reshape=False, mode='nearest')
                    self.im1 = ndimage.filters.gaussian_filter(self.im1, 3 - self.counter * .3)
                else:
                    self.im1 = self.im0

                now = datetime.now()
                now_stamp = datetime.timestamp(now)

                self.update_1d_data('timestamps', now_stamp)

            # self.gui.img0.setImage(np.flipud(self.im1).T,levels=(0,300))

            self.data_dict['contrast'] = np.roll(self.data_dict['contrast'], -1, axis=1)
            self.data_dict['rotation'] = np.roll(self.data_dict['rotation'], -1)
            self.data_dict['iteration'] = np.roll(self.data_dict['iteration'], -1, axis=1)
            self.data_dict['iteration'][:, -1] = self.counter

            alignment_output = self.yag1.check_alignment(self.im1)

            self.data_dict['contrast'][:, -1] = alignment_output['contrast']

            translation = alignment_output['translation']

            # centering_x = 1024 + np.sum(translation[:,1])/4
            # centering_y = 1024 + np.sum(translation[:,0])/4
            # self.data_dict['centering'] = np.array([centering_x,centering_y])

            if isinstance(self.yag1, YagAlign):

                rotation1 = (translation[1, 1] - translation[3, 1]) / (translation[3, 0] - translation[1, 0])
                rotation2 = (translation[3, 0] - translation[2, 0]) / (translation[3, 1] - translation[2, 1])
                self.data_dict['rotation'][-1] = (rotation1 + rotation2) * 180 / np.pi / 2
            else:
                self.data_dict['rotation'][-1] = 0.0
            # scale
            scale = alignment_output['scale']
            # centering
            center = np.zeros((4, 2))

            if isinstance(self.yag1, YagAlign):
                # center[0,:] = translation[0,:]*scale[0] + np.array([1792,256])
                #center[0, 0] = translation[0, 0] * scale[0] + 1592
                #center[0, 1] = -translation[0, 1] * scale[0] + 256
                ## center[1,:] = translation[1,:]*scale[1] + np.array([1792,1792])
                #center[1, 0] = translation[1, 0] * scale[1] + 1792
                #center[1, 1] = -translation[1, 1] * scale[1] + 1792
                ## center[2,:] = translation[2,:]*scale[2] + np.array([256,256])
                #center[2, 0] = translation[2, 0] * scale[2] + 256
                #center[2, 1] = -translation[2, 1] * scale[2] + 256
                ## center[3,:] = translation[3,:]*scale[3] + np.array([256,1792])
                #center[3, 0] = translation[3, 0] * scale[3] + 256
                #center[3, 1] = -translation[3, 1] * scale[3] + 1792

                center[0, 0] = translation[0, 1] * scale[0] + 1792
                center[0, 1] = -translation[0, 0] * scale[0] + 256
                # center[1,:] = translation[1,:]*scale[1] + np.array([1792,1792])
                center[1, 0] = translation[2, 1] * scale[2] + 1792
                center[1, 1] = -translation[2, 0] * scale[2] + 1792
                # center[2,:] = translation[2,:]*scale[2] + np.array([256,256])
                center[2, 0] = translation[1, 1] * scale[1] + 256
                center[2, 1] = -translation[1, 0] * scale[1] + 256
                # center[3,:] = translation[3,:]*scale[3] + np.array([256,1792])
                center[3, 0] = translation[3, 1] * scale[3] + 256
                center[3, 1] = -translation[3, 0] * scale[3] + 1792

            self.data_dict['center'] = center
            self.data_dict['scale'] = scale

            pix_dist = np.zeros(4)
            pix_dist[0] = np.sqrt(np.sum(np.abs(center[0, :] - center[1, :]) ** 2))
            pix_dist[1] = np.sqrt(np.sum(np.abs(center[0, :] - center[2, :]) ** 2))
            pix_dist[2] = np.sqrt(np.sum(np.abs(center[1, :] - center[3, :]) ** 2))
            pix_dist[3] = np.sqrt(np.sum(np.abs(center[2, :] - center[3, :]) ** 2))

            if self.imager_type == 'PPM':

                self.data_dict['pixSize'] = self.distance / np.mean(pix_dist) / self.PPM_object.xbin
            else:
                self.data_dict['pixSize'] = 2e-3/400/scale*1e6 / self.PPM_object.xbin

            # self.data_dict['rotation'][:,-1] = alignment_output['rotation']

            # data_dict = {}
            self.data_dict['im1'] = self.im1
            self.data_dict['shifts'] = alignment_output['shifts']
            self.data_dict['counter'] = self.counter

            now = time.time()
            dt = (now - self.lastupdate)
            if dt <= 0:
                dt = 0.000000000001
            fps2 = 1.0 / dt
            self.lastupdate = now
            self.fps = self.fps * 0.9 + fps2 * 0.1
            tx = 'Mean Frame Rate:  {fps:.3f} FPS'.format(fps=self.fps)
            self.data_dict['tx'] = tx

            self.sig.emit(self.data_dict)

            if self.running:
                QtCore.QTimer.singleShot(100, self._update)
                self.counter += 1
            else:
                self.reset_camera()
