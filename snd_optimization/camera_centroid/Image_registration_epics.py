#!/usr/bin/env python
# coding: utf-8

import numpy as np
import imageio
import json
import scipy.ndimage.interpolation as interpolate
import sys
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QPen
from PyQt5.QtCore import Qt
import pyqtgraph as pg
from pcdsdevices.areadetector.detectors import PCDSAreaDetector
from PyQt5.uic import loadUiType
import warnings
from processing_module import RunRegistration
from analysis_tools import YagAlign
from analysis_tools import XTESAlign
import PPM_widgets
import os


local_path = os.path.dirname(os.path.abspath(__file__))


Ui_MainWindow, QMainWindow = loadUiType(local_path+'/image_register.ui')


class App(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, imager=None, parent=None):
        super(App, self).__init__(parent)
        self.setupUi(self)

        # set imager
        self.imager = imager

        self.runButton.clicked.connect(self.change_state)
        self.pixelWriteButton.clicked.connect(self.write_pixel_size)

        self.actionSave.triggered.connect(self.save_image)
        self.demoCheckBox.stateChanged.connect(self.toggle_demo)
        
        # initialize demo state
        self.run_demo = True
        # check current state
        self.toggle_demo() 

        self.main_image = PPM_widgets.ImageRegister(self.canvas)

        self.main_image.connect_levels(self.levelsWidget)


        # Top left image
        self.top_left = PPM_widgets.ImageZoom(self.upperLeftCanvas, 'r')
        self.top_left.connect_levels(self.levelsWidget)

        # Top right image
        self.top_right = PPM_widgets.ImageZoom(self.upperRightCanvas, 'g')
        self.top_right.connect_levels(self.levelsWidget)

        # Bottom left image
        self.bottom_left = PPM_widgets.ImageZoom(self.lowerLeftCanvas, 'c')
        self.bottom_left.connect_levels(self.levelsWidget) 
        # Bottom right image
        self.bottom_right = PPM_widgets.ImageZoom(self.lowerRightCanvas, 'm')
        self.bottom_right.connect_levels(self.levelsWidget)

        #  contrast plot
        self.contrast_plot = PPM_widgets.StripChart(self.contrastCanvas, 'Contrast')

        keys = ['tl', 'tr', 'bl', 'br']
        labels = ['Top Left', 'Top Right', 'Bottom Left', 'Bottom Right']

        self.contrast_plot.addSeries(keys, labels)
        
        
        #  rotation plot
        self.rotation_plot = PPM_widgets.StripChart(self.rotationCanvas, 'Rotation (degrees)')
        self.rotation_plot.addSeries(['average'],[''])

        self.imager_type = 'PPM'

        self.imager_name = self.imager[:5]

        if self.imager[-5:] == 'XTES:':
            self.yag1 = XTESAlign()
            self.imager_type = 'XTES'
        else:
            self.yag1 = YagAlign()

        # the image to be transformed
        #im1 = np.array(imageio.imread("test_pattern.png")[32:2650, 32:2650, 3],dtype='float')
        if self.imager_type == 'PPM':
            im1 = np.array(imageio.imread(local_path+"/PPM_alignment/IM3L0.png"),dtype='float')
            im1 = 255 - im1
            N, M = np.shape(im1)
            scale = 2048.0 / N

            im0 = interpolate.zoom(im1, scale)


        else:
            im1 = np.array(imageio.imread(local_path+"/PPM_alignment/im4l0_001.tiff"))
            #im1 = im1 - np.min(im1)

            N, M = np.shape(im1)
            scale = 1024.0 / N

            im0 = interpolate.zoom(im1, scale)

        self.data_dict = {}
        self.data_dict['im0'] = im0
        self.data_dict['contrast'] = np.zeros((4, 100))
        self.data_dict['rotation'] = np.zeros(100)
        self.data_dict['iteration'] = np.tile(np.linspace(-99, 0, 100), (4, 1))
        self.data_dict['counter'] = 0.
        self.data_dict['center'] = np.zeros((4,2))
        self.data_dict['scale'] = np.zeros(4)
        self.data_dict['pixSize'] = 0.0
        self.data_dict['timestamps'] = np.zeros(100)
        #self.data_dict['centering'] = np.zeros(2)

        self.pixSize = 0

    def toggle_demo(self):
        if self.demoCheckBox.isChecked():
            self.run_demo = True
        else:
            self.run_demo = False

    def write_pixel_size(self):
        # grab current pixel size
        pixSize = np.copy(self.pixSize)

        # get current file contents
        try:
            with open(local_path+'/imagers.db') as json_file:
                data = json.load(json_file)

        except json.decoder.JSONDecodeError:
            data = {}

        if self.imager_name in data:

            data[self.imager_name]['pixel'] = float(pixSize)
        else:
            data[self.imager_name] = {}
            data[self.imager_name]['pixel'] = float(pixSize)

        # write to the file under the corresponding imager field
        with open(local_path+'/imagers.db', 'w') as outfile:
            json.dump(data, outfile, indent=4)

    def change_state(self):
        if self.runButton.text() == 'Run':

            self.registration = RunRegistration(self.yag1, self.data_dict, self.averageWidget, self.run_demo, imager=self.imager)

            width, height = self.registration.get_FOV()
            self.main_image.update_viewbox(width, height)

            self.thread = QtCore.QThread()
            self.thread.start()

            self.registration.moveToThread(self.thread)
            self.runButton.setText('Stop')

            self.registration.sig.connect(self.update_plots)

        elif self.runButton.text() == 'Stop':

            self.registration.stop()
            self.thread.quit()
            self.thread.wait()
            self.runButton.setText('Run')


    @staticmethod
    def normalize_image(image):
        image -= np.min(image)
        image *= 255./float(np.max(image))
        image = np.array(image,dtype='uint8')
        return image

    def save_image(self):
        formats = 'Portable Network Graphic (*.png)'
        filename = QtGui.QFileDialog.getSaveFileName(self, 
                'Save Image','untitled.png',formats)
        #name = str(name).strip()
        if not filename[0] == '':
            im = App.normalize_image(self.data_dict['im1'])
            filename = App.get_filename(filename)
            #imageio.imwrite(filename,self.data_dict['im1'])
            imageio.imwrite(filename,im)
        print(filename)
        #im = Image.fromarray(self.data_dict['im1'])
        #im.save(name)
     

    @staticmethod
    def get_filename(name):
        path = name[0]
        extension = name[1].split('*')[1][0:4]
        if path[-4:] != extension:
            path = path + extension
        return path


    def closeEvent(self, event):
        if self.runButton.text() == 'Stop':
            self.registration.stop()
            self.thread.quit()
            self.thread.wait()

    def update_plots(self,data_dict):

            
        self.pixSize = data_dict['pixSize']

        full_center = np.mean(data_dict['center'],axis=0)

        self.label_pixSize.setText('Pixel size: %.2f \u03BCm'
                % data_dict['pixSize'])
        centerText = ('YAG center (x,y): %.2f \u03BCm, %.2f \u03BCm'
                % ((full_center[1]-1024)*self.pixSize, (full_center[0]-1024)*self.pixSize))
        self.label_center.setText(centerText)
        self.data_dict = data_dict


        center = data_dict['center']
        scale = data_dict['scale']
        #self.circ0.setRect(full_center[1]-25,full_center[0]-25,50,50)


        if self.imager_type == 'PPM':

            self.main_image.update_image(data_dict['im1'], self.pixSize, center=center, scale=scale)
            self.top_left.update_image(data_dict['shifts'][3][210:300, 210:300])
            self.top_right.update_image(data_dict['shifts'][2][210:300, 210:300])
            self.bottom_left.update_image(data_dict['shifts'][1][210:300, 210:300])
            self.bottom_right.update_image(data_dict['shifts'][0][210:300, 210:300])

        else:
            self.main_image.update_image(data_dict['im1'], self.pixSize)

        iteration = data_dict['iteration']
        contrast = data_dict['contrast']
        rotation = data_dict['rotation']
        time_stamps = data_dict['timestamps']


        self.contrast_plot.update_plots(time_stamps, tl=contrast[3,:], tr=contrast[2,:], bl=contrast[1,:], br=contrast[0,:])

        self.rotation_plot.update_plots(time_stamps, average=rotation)


        self.label.setText(data_dict['tx'])


if __name__ == '__main__':

    warnings.filterwarnings('ignore', '.*output shape of zoom.*')
    app = QtGui.QApplication(sys.argv)
    thisapp = App()
    thisapp.show()
    sys.exit(app.exec_())
