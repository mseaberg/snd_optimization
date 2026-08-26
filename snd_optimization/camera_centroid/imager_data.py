import numpy as np
import pandas as pd
from ophyd import EpicsSignalRO as SignalRO
from ophyd.signal import ReadTimeoutError
from copy import copy
import os
import h5py
import time

class DataHandler:
    """
    Class to manage the data being passed between objects, functions
    """
    def __init__(self, hutch):
        """
        Method to initialize the data handler class
        """

        self.local_path = os.path.dirname(os.path.abspath(__file__))


        # timestamp key
        self.timestamp_key = 'timestamps'

        # keys for data that is calculated on every shot
        self.stripchart_imager_keys = ['cx', 'cy', 'wx', 'wy', 'intensity', 'centroid_is_valid', 'wavefront_is_valid']

        # keys for wfs data that is calculated on every shot
        self.stripchart_wfs_keys = ['z_x', 'z_y', 'rms_x', 'rms_y', 'coma_x', 'coma_y',
                'focus_fwhm_horizontal', 'focus_fwhm_vertical']

        # keys for all stripchart data
        self.stripchart_all_keys = self.stripchart_imager_keys + self.stripchart_wfs_keys

        # keys for smoothed data
        self.stripchart_smooth_keys = [key+'_smooth' for key in self.stripchart_all_keys]

        # keys for constants
        self.constant_keys = ['counter', 'pixSize', 'cx_ref', 'cy_ref', 'tx']

        # self.valid_keys = ['centroid_is_valid', 'wavefront_is_valid']

        # keys for 1-D coordinates
        self.coord_keys = ['x', 'y']

        # keys for wfs 1-D coordinates
        self.wfs_coord_keys = ['x_prime', 'y_prime', 'xf']

        # keys for 1-D arrays updated every shot
        self.image_array_keys = ['lineout_x', 'lineout_y', 'projection_x',
                           'projection_y', 'fit_x', 'fit_y']

        # keys for 1-D wfs arrays updated every shot
        self.wfs_array_keys = ['x_res', 'y_res', 'focus_horizontal', 'focus_vertical']

        # keys for images updated every shot
        self.image_keys = ['profile']

        # keys for wfs images updated every shot
        self.wfs_image_keys = ['focus', 'F0', 'wave']

        # read file with PV names
        self.filename = self.local_path+'/pv_lists/{}_pvs.txt'.format(hutch.lower())

        # initialize data dictionary
        self.data_dict = {}

        # initialize epics signals
        self.epics_signals = {}

        # update keys that are allowed for plotting
        self.initial_keys = ['timestamps', 'cx', 'cy', 'wx', 'wy', 'z_x', 'z_y', 'rms_x',
                         'rms_y', 'intensity', 'coma_x', 'coma_y', 'centroid_is_valid', 'wavefront_is_valid',
                         'focus_fwhm_horizontal', 'focus_fwhm_vertical']

        self.key_list = copy(self.initial_keys)

        # set initialized to False until we get an imager
        self.initialized = False

        self.pv_keys = []
        self.pv_names = []

        # initialize PPM_object to None
        self.imager = None

    def plot_keys(self):
        return self.key_list

    def initialize(self, PPM_object, N=5000):

        self.imager = PPM_object

        self.N = N
        self.im_N = self.imager.N
        self.im_M = self.imager.M

        # read pv keys
        #self.pv_keys, self.pv_names = self.read_pv_names()

        # initialize data dictionary entries
        self.reset_data()

        # update target position
        self.update_target()

        self.initialized = True

    def uninitialize(self):
        self.initialized = False

    def update_imager(self, PPM_object):
        self.imager = PPM_object
        self.update_target()

    def update_target(self):
        self.data_dict['cx_ref'] = self.imager.cx_target
        self.data_dict['cy_ref'] = self.imager.cy_target

    def reset_data(self):
        """
        Method to reset the data. This is called when a new imager is selected for instance.
        This should really be cleaned up so that it's easier to add new items to the data dictionary. Basically
        just need to categorize different types of data based on array size in terms of how to initialize them. This
        could be defined in a file.
        """

        # reset data dict
        self.data_dict = {}
       
        # destroy old epics signals
        for key in self.epics_signals:
            self.epics_signals[key].destroy()

        # reinitialize epics signals
        self.epics_signals = {}

        # initialize timestamps
        self.data_dict[self.timestamp_key] = np.full(self.N, np.nan, dtype=float)

        # initialize stripchart data to nan's
        for key in self.stripchart_all_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # initialize stripchart smoothed data to nan's
        for key in self.stripchart_smooth_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # initialize constants to zero
        for key in self.constant_keys:
            self.data_dict[key] = 0.0

        # initialize coordinates
        for key in self.coord_keys:
            self.data_dict[key] = np.linspace(-1024, 1023, 100)

        for key in self.wfs_coord_keys:
            self.data_dict[key] = np.linspace(-1024, 1023, 100)

        # initialize 1D array data
        for key in self.image_array_keys:
            self.data_dict[key] = np.zeros(100)

        for key in self.wfs_array_keys:
            self.data_dict[key] = np.zeros(100)

        # initialize image data
        for key in self.image_keys:
            self.data_dict[key] = np.zeros((self.im_N, self.im_M))

        for key in self.wfs_image_keys:
            self.data_dict[key] = np.zeros((self.im_N, self.im_M))

        # initialize pv data
        for key in self.pv_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # update keys that are allowed for plotting
        self.key_list = copy(self.initial_keys)
        #self.key_list = ['timestamps','cx', 'cy', 'wx', 'wy', 'z_x', 'z_y', 'rms_x',
        #        'rms_y', 'intensity', 'coma_x', 'coma_y', 'centroid_is_valid', 'wavefront_is_valid']
        
        # connect to epics signals and add to data_dict
        self.connect_epics_pvs()

    def save_data(self, filename):
        """
        Method to dump the current data buffer into a file
        """
        #data_frame = pd.DataFrame(self.data_dict)
        #data_frame.to_hdf(filename, 'df')
        mask = np.logical_not(np.isnan(self.data_dict['timestamps']))
        with h5py.File(filename,'a') as f:
            for key in self.key_list:
                data = self.data_dict[key][mask]
                f.create_dataset(key, data=data, dtype='float')
        print('saved data to %s' % filename)


    def update_data(self, wfs_data=None):
        """
        Produce new data from current image
        :return:
        """

        #time1 = time.time() 
        # update timestamps
        self.update_1d_data(self.timestamp_key, self.imager.time_stamp)

        # standalone keys
        standalone_keys = self.image_array_keys + self.image_keys + self.coord_keys

        # standalone wfs keys
        wfs_array_keys = self.wfs_coord_keys + self.wfs_array_keys + self.wfs_image_keys

        # update dictionary
        for key in self.stripchart_imager_keys:
            self.update_1d_data(key, getattr(self.imager, key))

        # update pv's
        for key in self.pv_keys:
            try:
                new_data = self.epics_signals[key].value
                self.update_1d_data(key, new_data)
            except ReadTimeoutError:
                self.update_1d_data(key, np.nan)

        # get non-stripchart data
        for key in standalone_keys:
            self.data_dict[key] = getattr(self.imager, key)

        # get wfs data
        if wfs_data is not None:
            for key in self.stripchart_wfs_keys:
                self.update_1d_data(key, wfs_data[key])

            for key in wfs_array_keys:
                self.data_dict[key] = wfs_data[key]

        else:
            for key in self.stripchart_wfs_keys:
                self.update_1d_data(key, np.nan)

        # update validity data
        # for key in self.valid_keys:
        #     self.data_dict[key] = getattr(self.imager, key)

        # update running averages
        for key in self.stripchart_smooth_keys:
            self.running_average(key, key+'_smooth')

        self.data_dict['counter'] += 1

        # calculate frame rate
        # check if we have less than 10 frames so far
        num = int(np.min([self.data_dict['counter'], 10]))

        # calculate frame rate based on past 10 frames
        if num > 1:
            fps = 1.0/(np.mean(np.diff(self.data_dict['timestamps'][-num:])))
        else:
            fps = 1.0
        tx = 'Mean Frame Rate:  {fps:.3f} FPS'.format(fps=fps)
        self.data_dict['tx'] = tx
        #time2 = time.time()
        #print(time2-time1)

    def update_wfs_data(self, wfs_data):
        for key in wfs_data.keys():
            if key in self.image_keys:
                self.data_dict[key] = wfs_data[key]

    def read_pv_names(self):
        # read pv names from the file
        with open(self.filename) as f:
            file_lines = f.readlines()

        # strip the whitespace
        file_lines = [line.strip() for line in file_lines]

        # set up keys and pv's
        pv_keys = []
        pv_names = []
        for num, line in enumerate(file_lines):
            if '*' in line:
                try:
                    pv_keys.append(line.replace('*',''))
                    pv_names.append(file_lines[num+1])
                except:
                    pass
            else:
                if line not in pv_names:
                    pv_keys.append(line)
                    pv_names.append(line)

        return pv_keys, pv_names

    def update_1d_data(self, dict_key, new_value):
        self.data_dict[dict_key] = np.roll(self.data_dict[dict_key], -1)
        self.data_dict[dict_key][-1] = new_value

    def running_average(self, source_key, dest_key):
        self.data_dict[dest_key] = pd.Series(self.data_dict[source_key]).rolling(10, min_periods=1).mean().values

    def connect_epics_pvs(self):
        # add pv's to data_dict
        for key, name in zip(self.pv_keys,self.pv_names):
            tempSignal = SignalRO(name, auto_monitor=True)
            try:
                tempSignal.wait_for_connection()
                print('connected to %s' % key)
                self.epics_signals[key] = tempSignal
                self.data_dict[key] = np.full(self.N, np.nan, dtype=float)
                self.key_list.append(key)
            except TimeoutError:
                print('could not connect to %s' % key)
                self.pv_keys.remove(key)

