#!/usr/bin/env python
# coding: utf-8

from datetime import datetime
from epics import PV
import numpy as np
import imageio
import json
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
from PyQt5.uic import loadUiType
from processing_module import RunProcessing
from Image_registration_epics import App
import PPM_widgets
from imager_data import DataHandler
from motion_module import Alignment, Attenuate
from io_module import ImagerHdf5, ElogHandler
from subprocess import check_output
import subprocess
import shlex
import os
import time


local_path = os.path.dirname(os.path.abspath(__file__))


Ui_MainWindow, QMainWindow = loadUiType(local_path+'/PPM_screen.ui')

class PPM_Interface(QtWidgets.QMainWindow, Ui_MainWindow):
    kill_sig = QtCore.pyqtSignal()
    reset_sig = QtCore.pyqtSignal()
    save_sig = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, args=None):
        super(PPM_Interface, self).__init__()
        self.setupUi(self)

        if args is not None:
            print(args.camera)
            cam = args.camera
        else:
            cam = 'IM3L0'

        self.local_path = os.path.dirname(os.path.abspath(__file__))

        path1 = os.path.dirname(os.path.abspath(__file__))
        path2 = os.path.abspath(os.getcwd())
        print(path1)
        print(path2)

        # button for auto-alignment
        self.alignmentButton.clicked.connect(self.run_align)
        # button to update target position
        self.referenceButton.clicked.connect(self.update_reference)
        # menu item to open confluence page
        self.actionOpen_Confluence_Help.triggered.connect(self.open_help)
        # button to apply AT2L0 transmission
        self.applyTransmissionButton.clicked.connect(self.apply_transmission)
        # button to make a new plot
        self.plotButton.clicked.connect(self.make_new_plot)
        # method to save an image. Maybe replace and/or supplement this with image "recording" in the future
        self.actionSave.triggered.connect(self.save_image)
        # menu item to save images with hdf5 plugin and post to elog
        self.actionSave_with_hdf5_plugin.triggered.connect(self.capture_trajectory)
        # menu item to post to elog
        self.actionPost_to_elog.triggered.connect(self.elog_post)

        # list of QAction objects for controlling the image orientation
        self.orientation_actions = [self.action0, self.action90, self.action180, self.action270, 
                self.action0_flip, self.action90_flip, self.action180_flip, self.action270_flip]

        # not sure why this was necessary...
        self.groupBox_3.setObjectName("CentroidStatsGroupBox")

        # dictionary of QAction objects. Probably this could replace the above list eventually, but it works so won't
        # break it for now...
        self.orientation_dict = {
                'action0': self.action0,
                'action90': self.action90,
                'action180': self.action180,
                'action270': self.action270,
                'action0_flip': self.action0_flip,
                'action90_flip': self.action90_flip,
                'action180_flip': self.action180_flip,
                'action270_flip': self.action270_flip
                }

        # connect orientation actions
        for action in self.orientation_actions:
            action.triggered.connect(self.change_orientation)

        # connect method to save the current orientation
        self.actionSave_orientation.triggered.connect(self.save_orientation)

        # set orientation
        self.orientation = 'action0'

        # initialize tab to basic tab
        #self.tabWidget.setCurrentIndex(0)

        # connect levels to image
        self.imageWidget.connect_levels(self.levelsWidget)
        # connect crosshairs to image
        self.imageWidget.connect_crosshairs(self.crosshairsWidget)

        # connect stats to image. This is for displaying the circle on the image centered on the
        # beam with diameter of 2*FWHM
        self.imagerStats.connect_image(self.imageWidget)

        # get hutch. Looks like previously was trying to get based on experiment name, hence the try/except
        try:
            self.hutch = check_output('hostname').decode('utf-8').replace('\n','')[:3]

        except:
            self.hutch = check_output('hostname').decode('utf-8').replace('\n','')[:3]

        print('hutch: %s' % self.hutch)

        # initialize data handler
        self.data_handler = DataHandler(self.hutch)

        # load in imager information
        with open(self.local_path+'/imager_info.json') as json_file:
            self.imager_info = json.load(json_file)

        with open(self.local_path + '/imagers.db') as json_file:
            self.imager_metadata = json.load(json_file)

        # list of beamlines
        self.line_list = [key for key in self.imager_info]

        # dictionary of imagers
        self.imager_dict = {}
        for line in self.line_list:
            self.imager_dict[line] = [key for key in self.imager_info[line]]

        # initialize line combo box
        self.lineComboBox.addItems(self.line_list)

        self.line = None
        valid_cam = False
        # figure out which line
        for key in self.imager_dict.keys():
            if cam in self.imager_dict[key]:
                self.line = key
                valid_cam = True

        line_index = self.line_list.index(self.line)

        # initialize imager list and imager
        self.imager_list = self.imager_dict[self.line]
        if valid_cam:
            self.imager = cam
        cam_index = self.imager_list.index(cam)
        print(cam_index)

        self.curr_imager_dict = self.imager_info[self.line][self.imager]

        self.imagerpv = self.curr_imager_dict['prefix']

        self.imagerComboBox.clear()
        self.imagerComboBox.addItems(self.imager_list)
       
        # hdf5 object
        self.imager_h5 = ImagerHdf5(prefix=self.imagerpv, name=self.imager)

        # disable by default, then enable when imager gets changed
        self.alignmentButton.setEnabled(False)

        # more initialization...
        self.lineComboBox.setCurrentIndex(line_index)
        self.imagerComboBox.setCurrentIndex(cam_index)

        # try to initialize elog
        self.elog_handler = ElogHandler()

        # initialize registration object
        self.processing = None
        self.alignment_message = None
        self.align = None
        self.alignment_thread = None
        self.attenuate_thread = None
        self.attenuate = None

        self.plots = []

        # attribute describing if trajectory is set
        self.trajectory_is_set = False

        # connect line combo box
        self.lineComboBox.currentIndexChanged.connect(self.change_line)
        # connect imager combo box
        self.imagerComboBox.currentIndexChanged.connect(self.change_imager)
        self.running = False
        self.thread_quit = True
        self.change_imager(cam_index)

    def open_help(self):
        """
        Method to open trajectory procedure confluence page
        """
        url = "https://confluence.slac.stanford.edu/x/DqxiKg"
        cmd = f"/cds/home/opr/{self.hutch}opr/bin/google-chrome-workstation {url}"

        cmd_parts = shlex.split(cmd)
        # run browser in a separate thread
        try:
            subprocess.Popen(cmd_parts)
        except:
            print('no browser command available')


    def apply_transmission(self):
        """
        Method to apply transmission to AT2L0
        """
        # Disable button while requests are made
        self.applyTransmissionButton.setEnabled(False)

        # Object for doing this in a separate thread
        self.attenuate = Attenuate()
        self.attenuate.sig_finished.connect(self.attenuate_finished)
        self.attenuate_thread = QtCore.QThread()
        self.attenuate.moveToThread(self.attenuate_thread)
        self.attenuate_thread.started.connect(self.attenuate.run)
        self.attenuate_thread.start()


    def attenuate_finished(self):
        """
        Method to clean up after thread is executed, and re-enable button
        """
        self.attenuate_thread.quit()
        self.attenuate_thread.wait()
        self.applyTransmissionButton.setEnabled(True)

    def run_align(self):
        """
        Method to run alignment routine upon button click
        """
        # disable alignment button
        self.alignmentButton.setEnabled(False)

        # open message box to allow for cancellation
        self.alignment_message = QtWidgets.QMessageBox()
        # Object to run alignment in a separate thread
        self.align = Alignment(self.imager, self.curr_imager_dict, calibrate=self.calibrateCheckBox.isChecked(),
                               hutch=self.hutch)
        # connect to alignment finished signal
        self.align.sig_finished.connect(self.alignment_finished)

        # initialize a new thread
        self.alignment_thread = QtCore.QThread()
        self.alignment_thread.finished.connect(self.enable_align)
        # move to new thread and connect to thread signals
        self.align.moveToThread(self.alignment_thread)
        self.alignment_thread.started.connect(self.align.run)
        self.alignment_thread.finished.connect(self.align.cancel)

        # make a dialog box to allow killing the thread
        self.alignment_message.setIcon(QtWidgets.QMessageBox.Information)
        self.alignment_message.setText("Attempting alignment")
        self.alignment_message.setWindowTitle("Alignment")
        self.alignment_message.setStandardButtons(QtWidgets.QMessageBox.Cancel)
        self.alignment_message.buttonClicked.connect(self.alignment_canceled)

        # close message box when alignment is finished
        self.alignment_thread.finished.connect(self.alignment_message.close)
        # start alignment
        self.alignment_thread.start()
        # open message box
        self.alignment_message.exec()

    def alignment_finished(self):
        """
        Method to cleanly quit the thread
        """
        self.alignment_thread.quit()
        self.alignment_thread.wait()
        try:
            self.alignment_message.close()
        except:
            print('message already closed')
        self.enable_align()

    def alignment_canceled(self):
        """
        Method to cancel alignment
        """
        if self.alignment_thread is not None:
            self.alignment_thread.quit()
            self.alignment_thread.wait()
            self.enable_align()

    def enable_align(self):
        """
        Method to check if there is a control associated with this imager,
        otherwise disable the button
        """
        has_mirror = False
        try:
            # check for mirror entry in json file
            if 'mirror' in self.curr_imager_dict.keys():
                # only allow undulator control from mfx for now
                if self.curr_imager_dict['mirror']!='und':
                    has_mirror = True
                elif self.hutch=='mfx':
                    has_mirror = True
            else:
                has_mirror = False
            # enable alignment button, or not
            if has_mirror:
                self.alignmentButton.setEnabled(True)
            else:
                self.alignmentButton.setEnabled(False)
        except:
            print('image_info.json file is incomplete')
            self.alignmentButton.setEnabled(False)

    def make_new_plot(self):
        """
        'AMI-style' plot for various characteristics
        """
        plot_window = PPM_widgets.NewPlot(self, self.data_handler.plot_keys())
        plot_window.show()
        self.plots.append(plot_window)

    def uncheck_all(self):
        """
        Method to uncheck all orientation options.
        """
        for action in self.orientation_actions:
            action.setChecked(False)

    def change_orientation(self):
        """
        Method that is called when an orientation menu item is selected. This causes a change to the orientation
        of the displayed image.
        """
        menu_item = self.sender()

        self.uncheck_all()
        menu_item.setChecked(True)

        self.orientation = menu_item.objectName()

        # check if running, if so send orientation information
        if self.processing is not None:
            self.processing.set_orientation(self.orientation)

    def load_orientation(self):
        """
        Method to load the previously saved orientation. Defaults to no rotation if there hasn't been anything saved.
        """
        try:
            # get orientation from metadata loaded from json file
            self.orientation = self.imager_metadata[self.imager]['orientation']
        except KeyError:
            # catch the exception that the orientation hasn't been saved for this imager
            print('orientation not set, using 0.')
            self.orientation = 'action0'

        # set appropriate checkbox and uncheck any other boxes
        self.uncheck_all()
        self.orientation_dict[self.orientation].setChecked(True)

    def save_orientation(self):
        """
        Method to save the current image orientation.
        """
        # get current file contents
        try:
            with open(local_path+'/imagers.db') as json_file:
                data = json.load(json_file)

        except json.decoder.JSONDecodeError:
            # give up if there's no file for now...
            pass

        # check if there is already information about this imager
        if self.imager in data:
            # if so, add orientation information
            data[self.imager]['orientation'] = self.orientation
        else:
            # if not, initialize information about this imager
            data[self.imager] = {}
            data[self.imager]['orientation'] = self.orientation

        # write to the file under the corresponding imager field
        with open('imagers.db', 'w') as outfile:
            json.dump(data, outfile, indent=4)

    def capture_trajectory(self):
        """
        Method to take various actions to document the trajectory
        """
        basename = self.get_basename()

        # save images
        try:
            image_name = self.save_hdf5(basename=basename)
        except:
            image_name = 'error saving images'
        # save data

        if self.hutch=='lfe':
            home_path = '/cds/home/opr/xppopr'
        elif self.hutch=='kfe':
            home_path = '/cds/home/opr/tmoopr'
        else:
            home_path = check_output('cd ~; pwd',shell=True).decode('utf-8').replace('\n','')

        data_path = home_path+'/trajectory/data/'
        data_name = data_path+self.imager+'_'+basename + '_data.h5'
        self.save_sig.emit(data_name)
       
        # post to elog
        self.elog_handler.post_trajectory(self.trajectory_is_set, self.imager, 
                self.imagerControls, self.imagerStats, self.photonEnergyLabel, 
                image_name, data_name)

    def elog_post(self):
        """
        Method to make an elog post of the window, as well as print the beam stats
        """
        self.elog_handler.post_stats(self.imager, self.imagerControls, self.imagerStats,
            self.photonEnergyLabel)

    def get_basename(self):
        # get state
        state = self.imagerControls.yStateReadback.text()

        # get pointing information
        if self.trajectory_is_set:
            pointing = 'pointed'
        else:
            pointing = 'unpointed'
        
        # get timestamp
        timestamp = datetime.now()
        date_str = str(timestamp.date())
        time_str = timestamp.time().isoformat(timespec='seconds')
        time_string = '%s_%s' % (date_str, time_str)
        basename = '%s_%s_%s' % (state, time_string, pointing)
        
        return basename

    def save_hdf5(self, basename=None):
        """
        Use hdf5 plugin to save images
        """
        #if basename is None:
        if not isinstance(basename,str):
            basename = self.get_basename()
        self.imager_h5.prepare(baseName=basename+'_images', nImages=10)
        self.imager_h5.write()
        path = self.imager_h5.imagerh5.file_path.get()
        name = self.imager_h5.imagerh5.file_name.get()
        full_name = path+name+'_1.h5'
        return full_name


    def set_time_range(self, time_range=10.0):
        """
        Method to set the time range of the centroid, etc plots.
        :param time_range: float
            time for x-axis in seconds
        """
        # check if this is called as a callback
        if self.sender():
            rangeLineEdit = self.sender()
            try:
                time_range = float(rangeLineEdit.text())
            except ValueError:
                time_range = 10.0
                rangeLineEdit.setText('10.0')

        # set time range for all stripchart-type plots
        for plot in self.all_plots:
            plot.set_time_range(time_range)

    def setup_legend(self, legend):
        """
        Method to set up a legend for a plot. This should probably belong in the PPM_widgets module.
        Parameters
        ----------
        legend: string
            pyqtgraph Legend object
        """

        # set style: white text, 10pt
        legendLabelStyle = {'color': '#FFF', 'size': '10pt'}
        # the following was just taken from the web...
        for item in legend.items:
           for single_item in item:
               if isinstance(single_item, pg.graphicsItems.LabelItem.LabelItem):
                   single_item.setText(single_item.text, **legendLabelStyle)

    def change_line(self, index):
        """
        Method to change which beamline from which to select an imager.

        Parameters
        ----------
        index: int
            index corresponding to which beamline as defined in self.line_list
        """
        # update line
        self.line = self.line_list[index]
        self.imager_list = self.imager_dict[self.line]
        #self.imagerpv_list = self.imagerpv_dict[self.line]
        self.imagerComboBox.clear()
        self.imagerComboBox.addItems(self.imager_list)
        self.change_imager(0)

        if 'L' in self.line:
            self.photonEnergyLabel.channel = 'ca://PMPS:LFE:PE:UND:CurrentPhotonEnergy_RBV'
        else:
            self.photonEnergyLabel.channel = 'ca://PMPS:KFE:PE:UND:CurrentPhotonEnergy_RBV' 

    def change_imager(self, index):
        """
        Method to change settings based on selection of a new imager

        Parameters
        ----------
        index: int
            index corresponding to which imager as defined in self.imager_list
        """
        self.change_state(run=False)
        # update imager
        self.imager = self.imager_list[index]
        self.imageGroupBox.setTitle(self.imager)
        self.curr_imager_dict = self.imager_info[self.line][self.imager]
        if 'slit' in self.curr_imager_dict.keys():
            self.slitGroupBox.setTitle(self.curr_imager_dict['slit'])
        else:
            self.slitGroupBox.setTitle('No associated slits')
        if 'mirror' in self.curr_imager_dict.keys():
            if self.curr_imager_dict['mirror']!='und':
                self.alignmentButton.setEnabled(True)
            elif self.hutch=='mfx':
                self.alignmentButton.setEnabled(True)
            else:
                self.alignmentButton.setEnabled(False)
        else:
            self.alignmentButton.setEnabled(False)

        self.imagerpv = self.curr_imager_dict['prefix']
        self.imagerControls.change_imager(self.curr_imager_dict)
        self.slitControls.change_imager(self.curr_imager_dict)
        self.imagerStats.change_imager(self.imagerpv)

        # hdf5 object
        self.imager_h5 = ImagerHdf5(prefix=self.imagerpv, name=self.imager)

        # uninitialize data handler
        self.data_handler.uninitialize()
        self.load_orientation()

        self.change_state()

    def enable_run_button(self):
        #self.runButton.setEnabled(True)
        self.statusbar.clearMessage()
        #if self.runButton.text() == 'Stop':
            #self.alignmentButton.setEnabled(True)
        self.enable_align()

    def quit_thread(self):
        self.thread.quit()
        self.thread_quit = True

    def reset_plots(self):
        self.reset_sig.emit()

    def start_thread(self):

        # initialize processing object. This really needs a dictionary as input...

        # ROI checkbox probably needs some work here
        #if self.imagerStats.roiCheckBox.isChecked():
        if True:
            self.processing = RunProcessing(self.curr_imager_dict, self.data_handler, self.averageWidget,
                                        threshold=self.imagerStats.get_threshold(), hutch=self.hutch,crossWidget=self.crosshairsWidget)
        else:
            self.processing = RunProcessing(self.curr_imager_dict, self.data_handler, self.averageWidget,
                                        threshold=self.imagerStats.get_threshold(), hutch=self.hutch)

        # connect processing object to plotting function
        self.processing.sig.connect(self.update_plots)
        
        # connect to initialized signal
        self.processing.sig_initialized.connect(self.enable_run_button)

        # find out what the FOV of the screen is
        width, height = self.processing.get_FOV()
        # set the orientation for processing
        self.processing.set_orientation(self.orientation)

        # update viewboxes based on FOV
        self.imageWidget.update_viewbox(width, height)

        # update crosshair sizes
        self.crosshairsWidget.update_crosshair_width()
        self.crosshairsWidget.blue_x.setText(str(-width/2))
        self.crosshairsWidget.blue_y.setText(str(-height/2))
        self.crosshairsWidget.red_x.setText(str(width/2))
        self.crosshairsWidget.red_y.setText(str(height/2))
        self.crosshairsWidget.update_red_crosshair()
        self.crosshairsWidget.update_blue_crosshair()


        # update width for circle displayed on beam
        self.imagerStats.update_width()

        #initialize a new thread
        self.thread = QtCore.QThread()

        # move to new thread and connect to thread signals
        self.processing.moveToThread(self.thread)
        self.thread.started.connect(self.processing.run)
        self.thread.finished.connect(self.enable_run_button)
        self.thread.finished.connect(self.start_thread)
        self.kill_sig.connect(self.processing.stop)
        self.reset_sig.connect(self.processing.reset_plots)
        self.processing.sig_finished.connect(self.quit_thread)
        self.save_sig.connect(self.processing.save_data)
        
        print('starting thread')
        # start processing
        self.thread.start()
        self.thread_quit = False

        self.imagerStats.roiCheckBox.setEnabled(False)
        self.imagerStats.thresholdLineEdit.setEnabled(False)

        self.statusbar.showMessage('Starting acquisition...')


    def change_state(self, run=True):
        """
        Method to start the calculation running, or stop it.
        """

        # check if "Run" was selected
        if run:
            print('starting')
            if not self.running:
                self.start_thread()
                self.running = True
            else:
                self.running = True

        # check if "Stop" was selected
        else:
            print('stopping')
            self.kill_sig.emit()
            self.statusbar.showMessage('Stopping acquisition...')

            self.alignmentButton.setEnabled(False)

            # re-enable imager selection
            self.imagerStats.roiCheckBox.setEnabled(True)
            self.imagerStats.thresholdLineEdit.setEnabled(True)

    @staticmethod
    def normalize_image(image):
        """
        This probably belongs somewhere else... The idea is to normalize an image to 8-bit dynamic range
        for saving to a png file

        Parameters
        ----------
        image: ndarray (N,M)
            input image
        Returns
        -------
        ndarray (N,M)
            output image
        """
        image -= np.min(image)
        image *= 255./float(np.max(image))
        image = np.array(image,dtype='uint8')
        return image

    def save_data(self):
        """
        Method to get a filename for saving data, and send a signal
        to save the data
        """
        formats = 'HDF5 file (*.h5)'
        filename = QtGui.QFileDialog.getSaveFileName(self,
                'Save Data', 'untitled.h5', formats)

        if not filename[0] == '':
            filename = PPM_Interface.get_filename(filename, fmt='.h5')
            self.save_sig.emit(filename)

    def save_image(self):
        """
        Method to save a png image based on the latest image grabbed
        """
        formats = 'Portable Network Graphic (*.png)'
        filename = QtGui.QFileDialog.getSaveFileName(self, 
                'Save Image','untitled.png',formats)
        # make sure a file name was chosen
        if not filename[0] == '':
            # normalize the image and write to file
            im = App.normalize_image(self.data_handler.data_dict['profile'])
            filename = PPM_Interface.get_filename(filename, fmt='.png')
            imageio.imwrite(filename,im)
        print(filename)

    @staticmethod
    def get_filename(name, fmt='png'):
        """
        Method to get the filename from QFileDialog
        Parameters
        ----------
        name: list of strings
            first entry is the full path including file name, second entry is the extension

        Returns
        -------
        string
            full path including file name and extension
        """
        path = name[0]
        extension = name[1].split('*')[1][0:len(fmt)]
        if path[-len(fmt):] != extension:
            path = path + extension
        return path

    def closeEvent(self, event):
        """
        Method to control what happens if the window is closed.

        Parameters
        ----------
        event: signal
        """
        # check if anything is running, otherwise do nothing else
        #if self.runButton.text() == 'Stop':
        event.ignore()
        self.thread.finished.disconnect(self.start_thread)
        self.kill_sig.emit()
        #self.processing.stop()
        #self.thread.quit()
        #self.thread.wait()
        print('exiting')
        time.sleep(1)
        #timer = threading.Timer(0.1) 
        event.accept()
        #QtCore.QTimer.singleShot(1000, event.accept)
        #event.accept()

    def update_reference(self):
        
        reply = QtWidgets.QMessageBox.question(self,
                'Update Reference Position',
                'Are you sure you wish to update the reference position?',
                QtWidgets.QMessageBox.Yes | 
                QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            data_dict = self.data_handler.data_dict
            try:
                data_dict['cx_ref'].put(float(self.imagerStats.xCentroidLineEdit.text()))
                data_dict['cy_ref'].put(float(self.imagerStats.yCentroidLineEdit.text()))
            except:
                print('unable to update reference')
        else:
            print('Reference not updated')

    def update_plots(self):
        """
        Method to update all the plots. Would be nice to find a way to make this less explicit. One idea would be
        to pass the dictionary keys into the plots when they are first initialized. Seems like passing the dictionary
        around to all the plot functions probably only passes by reference or something.

        Parameters
        ----------
        data_dict: dict
            This is where all the data to display is stored
        """

        data_dict = self.data_handler.data_dict

        # get validity
        centroid_validity = data_dict['centroid_is_valid']

        # check if the most recent measurement was valid
        if centroid_validity[-1]:
            self.groupBox_3.setStyleSheet("QGroupBox#CentroidStatsGroupBox { border: 2px solid green;}")
        else:
            self.groupBox_3.setStyleSheet("QGroupBox#CentroidStatsGroupBox { border: 2px solid red;}")

        x = data_dict['x']
        y = data_dict['y']
        image_data = data_dict['profile']
        xlineout = data_dict['lineout_x']
        ylineout = data_dict['lineout_y']
        xprojection = data_dict['projection_x']
        yprojection = data_dict['projection_y']
        fit_x = data_dict['fit_x']
        fit_y = data_dict['fit_y']

        # update main image and lineouts
        self.imageWidget.update_plots(image_data, x, y, xprojection, yprojection, fit_x, fit_y, 
                xlineout_data=xlineout, ylineout_data=ylineout)

        # print refresh rate
        self.label.setText(data_dict['tx'])

        # update stats values
        self.imagerStats.update_stats(data_dict)

        for plot in self.plots:
            plot.update_plot(data_dict, self.data_handler.plot_keys())
