"""
optics module

Part of the xraybeamline2d package.

Currently implements the following optical elements:
Mirror: parent mirror class
FlatMirror: flat transport mirror
CurvedMirror: elliptical KB mirror
Mono: implementation of the NEH2.2 monochromator
Grating: VLS grating up to 3rd order
Collimator: photon collimator (circular aperture)
Slit: rectangular aperture
Drift: path length between adjacent optical elements
CRL: compound refractive lens (parabolic)
PPM: power profile monitor, for viewing beam intensity
"""
import numpy as np
from time import sleep
import scipy.interpolate as interpolation
import scipy.ndimage as ndimage
import scipy.optimize as optimize
from skimage.restoration import unwrap_phase
from datetime import datetime
from .util import Util
try:
    from epics import PV
    from pcdsdevices.areadetector.detectors import PCDSAreaDetector
    from ophyd import EpicsSignal
    from ophyd import EpicsSignalRO
    from ophyd import Component as Cpt
except ImportError:
    print("Can't find epics package. PPM_Imager class will not be supported")




class PPM:
    """
    Class to represent profile monitor output from PPMs.

    Attributes
    ----------
    name: str
        device name (e.g. IM1K4)
    FOV: float
        width of the (restricted to be square) field of view
    n: int
        number of pixels across the image. Image is NxN.
    dx: float
        PPM pixel size
    z: float
        z location along beamline
    blur: bool
        Blur beam intensity prior to interpolation if True, simulating blurring due to finite resolution of
        microscope. Mainly important for wavefront sensor profile monitors.
    view_angle_x: float
        Set viewing angle (in degrees) relative to beam propagation axis. Defined as angle from glancing incidence,
        normal incidence is 90 degrees.
    view_angle_y: float
        Set viewing angle (in degrees) relative to beam propagation axis. Defined as angle from glancing incidence,
        normal incidence is 90 degrees.
    x: (N,) ndarray
        profile monitor x coordinates
    y: (N,) ndarray
        profile monitor y coordinates
    profile: (N,N) ndarray
        Calculated beam profile (normalized intensity) at profile monitor.
    x_lineout: (N,) ndarray
        Calculated horizontal lineout (normalized).
    y_lineout: (N,) ndarray
        Calculated vertical lineout (normalized).
    cx: float
        Horizontal beam centroid on PPM.
    cy: float
        Vertical beam centroid on PPM.
    wx: float
        Horizontal beam FWHM on PPM. Based on Gaussian fit (or calculated from second moment if fit fails).
    wy: float
        Vertical beam FWHM on PPM. Based on Gaussian fit (or calculated from second moment if fit fails).
    resolution: float
        PPM optical resolution. Used if blur is True.
    """

    def __init__(self, name, **kwargs):
        """
        Method to initialize a PPM.
        :param name: str
            device name (e.g. IM1K4)
        :param FOV: float
            width of the (restricted to be square) field of view (m)
        :param z: float
            z location along beamline
        :param N: int
            number of pixels across the image. Image is nxn.
        :param blur: bool
            Blur beam intensity prior to interpolation if True, simulating blurring due to finite resolution of
            microscope. Mainly important for wavefront sensor profile monitors.
        :param view_angle_x: float
            Set horizontal viewing angle (in degrees) relative to beam propagation axis.
            Defined as angle from glancing incidence, normal incidence is 90 degrees.
        :param view_angle_y: float
            Set vertical viewing angle (in degrees) relative to beam propagation axis.
            Defined as angle from glancing incidence, normal incidence is 90 degrees.
        :param resolution: float
            PPM optical resolution. Used if blur is True.
        :param calc_phase: bool
            whether to calculate/interpolate the phase profile at the PPM. Used with Pulse class.
        """

        # set defaults
        self.FOV = 10e-3
        self.z = None
        self.N = 2048
        self.blur = False
        self.view_angle_x = 90
        self.view_angle_y = 90
        self.resolution = 5e-6
        self.calc_phase = False
        self.threshold = 0.0

        # set allowed kwargs
        allowed_arguments = ['N', 'dx', 'FOV', 'z', 'blur', 'view_angle_x',
                             'view_angle_y', 'resolution', 'calc_phase', 'threshold']
        # update attributes based on kwargs
        for key, value in kwargs.items():
            if key in allowed_arguments:
                setattr(self, key, value)

        # set some attributes
        # self.N = N
        self.M = np.copy(self.N)
        self.dx = self.FOV / self.N
        # self.FOV = FOV
        # self.z = z
        self.name = name
        # self.blur = blur
        # self.view_angle_x = view_angle_x
        # self.view_angle_y = view_angle_y
        # self.resolution = resolution
        # self.calc_phase = calc_phase

        # calculate PPM coordinates
        self.x = np.linspace(-self.N / 2, self.N / 2 - 1, self.N) * self.dx
        self.y = np.copy(self.x)

        # get 2D coordinate arrays
        self.xx, self.yy = np.meshgrid(self.x, self.y)

        # initialize some attributes
        self.profile = np.zeros((self.N, self.N))
        self.phase = np.zeros((self.N, self.N), dtype=complex)
        self.zx = 0
        self.zy = 0
        self.cx_beam = 0
        self.cy_beam = 0
        self.x_lineout = np.zeros(self.M)
        self.y_lineout = np.zeros(self.N)
        self.fit_x = np.zeros(self.M)
        self.fit_y = np.zeros(self.N)
        self.amp_x = 0
        self.amp_y = 0
        self.cx = 0
        self.cy = 0
        self.wx = 0
        self.wy = 0
        self.xbin = 1
        self.lambda0 = 0.0
        self.centroid_is_valid = 0
        self.wavefront_is_valid = 0

    def beam_analysis(self, line_x, line_y, xwidth, ywidth):
        """
        Method for analyzing image of the beam.
        :param line_x: (N,) ndarray
            Horizontal lineout. Could be summed across full image or from an ROI.
        :param line_y: (N,) ndarray
            Vertical lineout. Could be summed across full image or from an ROI.
        :return cx: float
            Calculated horizontal centroid (m)
        :return cy: float
            Calculated vertical centroid (m)
        :return fwhm_x: float
            Calculated horizontal FWHM (m). Based on Gaussian fit (or calculated from second moment if fit fails).
        :return fwhm_y: float
            Calculated vertical FWHM (m). Based on Gaussian fit (or calculated from second moment if fit fails).
        :return fwx_guess: float
            Calculated horizontal FWHM (m) based on calculation of second moment.
        :return fwy_guess: float
            Calculated vertical FWHM (m) based on calculation of second moment.
        """

        self.amp_x = np.max(line_x)-np.min(line_x)
        self.amp_y = np.max(line_y)-np.min(line_y)
        
        #xwidth = np.sum(line_x>0)*self.dx
        #ywidth = np.sum(line_y>0)*self.dx

        # normalize lineouts
        if np.max(line_x) > 0:
            line_x -= np.min(line_x)
            line_x = line_x / np.max(line_x)
            
        if np.max(line_y) > 0:
            line_y -= np.min(line_y)
            line_y = line_y / np.max(line_y)

        # set 20% threshold
        thresh_x = np.max(line_x) * self.threshold
        thresh_y = np.max(line_y) * self.threshold
        # subtract threshold and set everything below to zero
        norm_x = line_x - thresh_x
        norm_x[norm_x < 0] = 0
        # re-normalize

        if np.max(norm_x) > 0:
            norm_x = norm_x / np.max(norm_x)

        # subtract threshold and set everything below to zero
        norm_y = line_y - thresh_y
        norm_y[norm_y < 0] = 0
        # re-normalize
        if np.max(norm_y) > 0:
            norm_y = norm_y / np.max(norm_y)

        # calculate centroids

        if np.sum(norm_x) > 0:
            cx = np.sum(norm_x * self.x) / np.sum(norm_x)
            # calculate second moments. Converted to microns to help with fitting
            sx = np.sqrt(np.sum(norm_x * (self.x - cx) ** 2) / np.sum(norm_x)) * 1e6

        else:
            cx = 0
            sx = 0
        if np.sum(norm_y) > 0:
            cy = np.sum(norm_y * self.y) / np.sum(norm_y)
            # calculate second moments. Converted to microns to help with fitting
            sy = np.sqrt(np.sum(norm_y * (self.y - cy) ** 2) / np.sum(norm_y)) * 1e6

        else:
            cy = 0
            sy = 0

        # conversion factor from sigma to fwhm
        fwx_guess = sx * 2.355
        fwy_guess = sy * 2.355

        # initial guess for Gaussian fit
        guessx = [cx * 1e6, sx]
        guessy = [cy * 1e6, sy]

        fit_validity = 1

        # Gaussian fitting. Using try/except to deal with any fitting errors
        try:
            # only fit in the region where we have signal
            mask = line_x > .1
            # Gaussian fit using Scipy curve_fit. Using only data that has >10% of the max
            px, pcovx = optimize.curve_fit(Util.fit_gaussian, self.x[mask] * 1e6, line_x[mask], p0=guessx)
            # set sx to sigma from the fit if successful.
            sx = px[1]
        except ValueError:
            fit_validity = 0
            print('Some of the data contained NaNs or options were incompatible. Using second moment for width.')
        except RuntimeError:
            fit_validity = 0
            print('Least squares minimization failed. Using second moment for width.')

        except TypeError:
            fit_validity = 0
            print('Not enough points to fit. Using second moment for width.')

        try:
            # only fit in the region where we have signal
            mask = line_y > .1
            # Gaussian fit using Scipy curve_fit. Using only data that has >10% of the max
            py, pcovy = optimize.curve_fit(Util.fit_gaussian, self.y[mask] * 1e6, line_y[mask], p0=guessy)
            # set sy to sigma from the fit if successful.
            sy = py[1]
        except ValueError:
            fit_validity = 0
            print('Some of the data contained NaNs or options were incompatible. Using second moment for width.')
        except RuntimeError:
            fit_validity = 0
            print('Least squares minimization failed. Using second moment for width.')

        except TypeError:
            fit_validity = 0
            print('Not enough points to fit. Using second moment for width.')

        # conversion factor from sigma to FWHM. Also convert back to meters.
        fwhm_x = sx * 2.355 / 1e6
        fwhm_y = sy * 2.355 / 1e6

        # check validity
        validity = ((self.amp_x > 0.) and (self.amp_y > 0.)  and
                    (fwhm_x < 2*xwidth) and (fwhm_y < 2*ywidth))
                    #and fwhm_x > self.dx*5 and fwhm_y > self.dx*5)

        self.centroid_is_valid = validity

        return cx, cy, fwhm_x, fwhm_y, fwx_guess, fwy_guess

    def calc_profile(self, beam):
        """
        Method to calculate the beam profile at the PPM screen.
        :param beam: Beam
            Beam object for viewing at PPM location. The Beam object is not modified by this method.
        :return: None
        """

        # Calculate intensity from complex beam
        profile = np.abs(beam.wave) ** 2

        # coordinate scaling due to off-axis viewing angle
        scaling_x = 1 / np.sin(self.view_angle_x * np.pi / 180)
        scaling_y = 1 / np.sin(self.view_angle_y * np.pi / 180)

        # if blurring is used, apply a gaussian filter
        if self.blur:
            # calculate blur widths in pixels, based on beam's pixel size
            x_width = self.resolution / beam.dx
            y_width = self.resolution / beam.dy
            # apply blurring using ndimage gaussian_filter
            profile = ndimage.filters.gaussian_filter(profile, sigma=(y_width, x_width))

        # get beam coordinates for interpolation
        x = beam.x[0, :]
        y = beam.y[:, 0]

        x_sign = 1
        y_sign = 1
        if x[1]-x[0] < 0:
            x_sign = -1
        if y[1]-y[0] < 0:
            y_sign = -1

        # interpolating function from Scipy's interp2d. Extrapolation value is set to zero.
        #f = interpolation.interp2d(x * scaling_x, y * scaling_y, profile, fill_value=0)
        f = interpolation.RectBivariateSpline(x_sign * x * scaling_x, y_sign * y * scaling_y, profile)
        # do the interpolation to get the profile we'll see on the PPM
        self.profile = f(x_sign*self.xx, y_sign*self.yy,grid=False)

        if self.calc_phase:
            phase = unwrap_phase(np.angle(beam.wave))
            #f_phase = interpolation.interp2d(x * scaling_x, y * scaling_y, phase, fill_value=0)
            f_phase = interpolation.RectBivariateSpline(x_sign*x * scaling_x, y_sign*y * scaling_y, phase)

            self.phase = f_phase(x_sign*self.xx, y_sign*self.yy,grid=False)

            if not beam.focused_x:
                # self.phase += np.pi / beam.lambda0 / beam.zx * (self.xx - beam.cx)**2
                self.zx = beam.zx
                self.cx_beam = beam.cx
            if not beam.focused_y:
                # self.phase += np.pi / beam.lambda0 / beam.zy * (self.yy - beam.cy)**2
                self.zy = beam.zy
                self.cy_beam = beam.cy
            self.phase += 2 * np.pi / beam.lambda0 * beam.ax * (self.xx - beam.cx)
            self.phase += 2 * np.pi / beam.lambda0 * beam.ay * (self.yy - beam.cy)

        # calculate horizontal lineout
        self.x_lineout = np.sum(self.profile, axis=0)
        # calculate vertical lineout
        self.y_lineout = np.sum(self.profile, axis=1)

        # get beam wavelength
        self.lambda0 = beam.lambda0

        # calculate centroids and beam widths
        self.cx, self.cy, self.wx, self.wy, wx2, xy2 = self.beam_analysis(self.x_lineout, self.y_lineout)

    def propagate(self, beam):
        """
        Method to propagate beam through PPM. Calls calc_profile.
        :param beam: Beam
            Beam object for viewing at PPM location. The Beam object is not modified by this method.
        :return: None
        """
        self.calc_profile(beam)


class PPM_Device(PPM):
    """
    Child class of PPM that is used for a physical PPM, rather than simulated.
    """
    def __init__(self, imager_dict, **kwargs):
        self.imager_prefix = imager_dict['prefix']
        super().__init__(self.imager_prefix, **kwargs)

        #self.imager_prefix = name
        self.threshold = 0.0001
        self.roi = None 

        # set allowed kwargs
        allowed_arguments = ['average','threshold','fit_object','roi']

        # update attributes based on kwargs
        for key, value in kwargs.items():
            if key in allowed_arguments:
                setattr(self, key, value)

        # get Y motor state
        if 'IM' in self.imager_prefix:
            self.state = EpicsSignalRO(self.imager_prefix+'MMS:STATE:GET_RBV')
        elif 'XCS' in self.imager_prefix:
            self.state = None
        else:
            self.state = EpicsSignalRO(imager_dict['motor']+'PIM.VAL',string=True)
        # define possible states depending on imager type
        if 'XTES' in self.imager_prefix:
            self.states_list = ['Unknown', 'OUT', 'YAG', 'DIAMOND', 'RETICLE']
        elif 'PPM' in self.imager_prefix:
            self.states_list = ['Unknown', 'OUT', 'POWERMETER', 'YAG1', 'YAG2']
        elif 'MFX' in self.imager_prefix:
            self.states_list = ['Unknown', 'YAG', 'OUT']
        elif 'XCS' in self.imager_prefix:
            self.states_list = []
        else:
            self.states_list = ['Unknown','DIODE','YAG','OUT']

        if 'L2' in self.imager_prefix:
            self.cam_name = self.imager_prefix + 'CAM:01:'
        elif 'IM' in self.imager_prefix:
            self.cam_name = self.imager_prefix + 'CAM:'
        else:
            self.cam_name = self.imager_prefix
        
        if 'MONO' in self.imager_prefix:
            self.cam_name = self.imager_prefix
        self.epics_name = self.cam_name + 'IMAGE1:'
        # get acquisition info (this is in seconds)
        self.acquisition_period = PV(self.epics_name[:-7] + 'AcquirePeriod_RBV').get()

        # check if Image3 is available
        port = PV(self.epics_name + 'PortName_RBV').get()
        array_rate = PV(self.epics_name + 'ROI:EnableCallbacks').get()

        if port is None or array_rate==0:
            self.epics_name = self.cam_name + 'IMAGE1:'
            self.acquisition_period = PV(self.cam_name + 'AcquirePeriod_RBV').get()

        port = PV(self.epics_name + 'PortName_RBV').get()

        array_rate = PV(self.epics_name + 'EnableCallbacks').get()


        if port is None or array_rate==0:
            self.epics_name = self.cam_name + 'IMAGE2:'
            self.acquisition_period = PV(self.cam_name + 'AcquirePeriod_RBV').get()

        port = PV(self.epics_name + 'PortName_RBV').get()

        if port is None:
            self.epics_name = self.imager_prefix + 'IMAGE1:'
            self.acquisition_period = PV(self.imager_prefix + 'AcquirePeriod_RBV').get()
       
        if 'IM' in self.cam_name: 
            self.x_bm_ctr = PV(self.cam_name + 'X_BM_CTR')
            self.y_bm_ctr = PV(self.cam_name + 'Y_BM_CTR')
        else:
            self.x_bm_ctr = PV(self.imager_prefix + 'X_BM_CTR')
            self.y_bm_ctr = PV(self.imager_prefix + 'Y_BM_CTR')

        self.orientation = 'action0'

        print(self.epics_name)

        array_port = PV(self.epics_name + 'NDArrayPort_RBV').get()


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
            'IM1L2': 2.0,
            'IM2L2': 5.0,
            'IM1K3': 8.5,
            'IM2K3': 8.5,
            'IM3K3': 8.5,
            'IM3L0': 5.0
        }

        z_dict = {
            'IM1L0': 699.5576832,
            'IM2L0': 736.50848,
            'IM3L0': 746.0000167,
            'IM4L0': 753.5587416,
            'IM1K0': 699.4677942,
            'IM2K0': 732.3403281,
            'IM1K1': 738.0279162,
            'IM2K1': 742.15,
            'IM1K2': 777.93,
            'IM2K2': 780.425,
            'IM3K2': 781.9,
            'IM4K2': 783.455,
            'IM5K2': 787.417,
            'IM6K2': 792.8188-.03,
            'IM7K2': 798.5,
            'IM1L1': 745.4046250,
            'IM2L1': 759.02,
            'IM3L1': 778.96,
            'IM4L1': 778.96,
            'IM1L2': 787.73,
            'IM2L2': 799.642,
            'IM1K3': 740.804,
            'IM2K3': 750,
            'IM3K3': 778.66,
            'IM2K4': 755.32096,
            'IM3K4': 758.889,
            'IM4K4': 761.101,
            'IM5K4': 764.313
            #'IM5K4': 764.45591 - 0.03
        }

        try:
            self.distance = FOV_dict[self.epics_name[0:5]] * 1e3
            self.z = z_dict[self.epics_name[0:5]]
        except:
            self.distance = 8500.0
            self.z = z_dict['IM1L0']


        try:
            self.gige = PCDSAreaDetector(self.cam_name, name='gige')
            self.reset_camera()
        except Exception:
            print('\nSomething wrong with camera server')
            self.gige = None

        ## load in pixel size
        #try:
        #    with open('/cds/home/s/seaberg/Commissioning_Tools/PPM_centroid/imagers.db') as json_file:
        #        data = json.load(json_file)
        #   
        #    key_name = self.epics_name[0:5]
        #    if 'MONO' in self.epics_name:
        #        if '3' in self.epics_name:
        #            key_name = 'MONO_03'
        #        elif '4' in self.epics_name:
        #            key_name = 'MONO_04'

        #    imager_data = data[key_name]
        #    #imager_data = data[self.epics_name[0:5]]
        #    self.dx = float(imager_data['pixel'])
        #    self.z = float(imager_data['z'])

        #    try:
        #        self.cx_target = float(imager_data['cx'])
        #        self.cy_target = float(imager_data['cy'])
        #    except KeyError:
        #        self.cx_target = 0
        #        self.cy_target = 0

        self.dx = 1.0
        self.cx_target = 0.0
        self.cy_target = 0.0

        dx = PV(self.cam_name + 'RESOLUTION').get()
        if dx is not None:
            self.dx = dx
        else:
            print('pixel size is not calibrated')
        cx_target = PV(self.cam_name + 'X_RTCL_CTR')
        if cx_target.get() is not None:
            self.cx_target = cx_target
        cy_target = PV(self.cam_name + 'Y_RTCL_CTR')
        if cy_target.get() is not None:
            self.cy_target = cy_target

        print('{} um pixel'.format(self.dx))

        # if len(sys.argv)>1:
        #     self.cam_name = sys.argv[1]
        #     self.epics_name = sys.argv[1] + 'IMAGE2:'

        #if 'XTES' in self.imager_prefix or 'PPM' in self.imager_prefix:
        #    PV(self.epics_name + 'ROI:Scale').put(1)
        #    PV(self.epics_name + 'ROI:BinX').put(1)
        #    PV(self.epics_name + 'ROI:BinY').put(1)
        #    PV(self.cam_name + 'DataType').put('UInt16')

        self.image_pv = PV(self.epics_name + 'ArrayData')

        # get ROI info
        #xmin = PV(self.epics_name + 'ROI:MinX_RBV').get()
        xmin = 0
        xmax = xmin + PV(self.epics_name + 'ROI:SizeX_RBV').get() - 1
        #ymin = PV(self.epics_name + 'ROI:MinY_RBV').get()
        ymin = 0
        ymax = ymin + PV(self.epics_name + 'ROI:SizeY_RBV').get() - 1
        # get binning
        self.xbin = PV(self.epics_name + 'ROI:BinX_RBV').get()
        self.ybin = PV(self.epics_name + 'ROI:BinY_RBV').get()

        # get array size
        self.xsize = PV(self.epics_name + 'ROI:ArraySizeX_RBV').get()
        self.ysize = PV(self.epics_name + 'ROI:ArraySizeY_RBV').get()

        # pixel size in meters, per pixel so need to take binning into account
        self.dxm = self.dx * 1e-6 * self.xbin

        print(self.xsize)
        if self.xsize == 0 or array_port=='CAM':
            self.xsize = PV(self.epics_name + 'ArraySize0_RBV').get()
            self.ysize = PV(self.epics_name + 'ArraySize1_RBV').get()
            xmin = 0
            ymin = 0
            xmax = self.xsize - 1
            ymax = self.ysize - 1

        #self.x = np.linspace(0, self.xsize - 1, self.xsize, dtype=float)
        #self.x -= self.xsize/2
        #self.y = np.linspace(0, self.ysize - 1, self.ysize, dtype=float)
        #self.y -= self.ysize/2

        self.x = np.linspace(xmin, xmax - (self.xbin - 1), self.xsize, dtype=float)
        self.x -= (xmax + 1) / 2
        self.y = np.linspace(ymin, ymax - (self.ybin - 1), self.ysize, dtype=float)
        self.y -= (ymax + 1) / 2

        self.x *= self.dx
        self.y *= self.dx
        self.xx, self.yy = np.meshgrid(self.x, self.y)

        self.x0 = np.copy(self.x)
        self.y0 = np.copy(self.y)

        print(self.epics_name)
        print(self.xsize)
        print(self.ysize)

        self.FOV = np.max(self.x) - np.min(self.x)

        self.N, self.M = np.shape(self.xx)

        self.profile = np.zeros_like(self.xx)
        self.x_lineout = np.zeros(self.M)
        self.y_lineout = np.zeros(self.N)
        self.projection_x = np.zeros(self.M)
        self.projection_y = np.zeros(self.N)
        if 'K' in self.epics_name:
            self.photon_energy = PV('PMPS:KFE:PE:UND:CurrentPhotonEnergy_RBV').get()
        else:
            self.photon_energy = PV('PMPS:LFE:PE:UND:CurrentPhotonEnergy_RBV').get()

        print('photon energy: %.2f' % self.photon_energy)
        try:
            self.lambda0 = 1239.8/self.photon_energy*1e-9
        except ZeroDivisionError:
            self.lambda0 = 0
        self.time_stamp = 0.0
        self.cx = 0
        self.cy = 0
        self.wx = 0
        self.wy = 0
        self.intensity = 0

        f_x = np.linspace(-self.M / 2., self.M / 2. - 1., self.M) / self.M / self.dxm
        f_y = np.linspace(-self.N / 2., self.N / 2. - 1., self.N) / self.N / self.dxm

        self.f_x, self.f_y = np.meshgrid(f_x, f_y)

        self.downsample = 3

        self.Nd = int(self.N / (2 ** self.downsample))
        self.Md = int(self.M / (2 ** self.downsample))

        self.fit_object = None

        # load in dummy image
        #self.dummy_image = np.load('/cds/home/s/seaberg/Commissioning_Tools/PPM_centroid/im2l0_sim.npy')
        img_data = np.load('/cds/home/s/seaberg/im5k4_run123.npz')
        self.dummy_image = img_data['image']

    def set_orientation(self, orientation):
        self.orientation = orientation

    def add_fit_object(self, fit_object):
        self.fit_object = fit_object

    def stop(self):
        self.running = False
        try:
            self.x_bm_ctr.put(np.nan)
            self.y_bm_ctr.put(np.nan)
        except:
            pass
            #print('Write access denied')
        try:
            pass
            #self.gige.cam.acquire.put(0, wait=True)
        except AttributeError:
            pass

    def check_rate(self):
        rate = PV(self.cam_name+'ArrayRate_RBV').get()

        return rate

    def reset_camera(self):
        
        try:
            if self.check_rate()>0:
                print('camera is acquiring')
            else:
                print('resetting camera')
                self.gige.cam.acquire.put(0, wait=True)
                self.gige.cam.acquire.put(1)
        except:
            print('no camera')

    def get_dummy_image(self):
        return self.dummy_image

    def get_image(self, angle=0, demo=False):
        #try:
    # do averaging
        if hasattr(self, 'average'):
            numImages = getattr(self, 'average').get_numImages()
        else:
            numImages = 1
       
        if demo:
            img = self.get_dummy_image()
            print('shape: {}'.format(img.shape[0]))
            time_stamp = datetime.timestamp(datetime.now())
        else:
            try:
                image_data = self.image_pv.get_with_metadata()
            except:
                image_data = np.zeros((self.ysize, self.xsize))
            #if 'value' in image_data.keys():
            img = np.reshape(image_data['value'], (self.ysize, self.xsize)).astype(float)
            if numImages > 1:
                for i in range(numImages-1):
                    # wait for the next image
                    sleep(self.acquisition_period)
                    image_data = self.image_pv.get_with_metadata()
                    imgTemp = np.reshape(image_data['value'], (self.ysize, self.xsize)).astype(float)
                    img += imgTemp


            img = img/numImages

            time_stamp = image_data['timestamp']

        # time_stamp = image_data.time_stamp
        # img = np.array(image_data.shaped_image,dtype='float')
        # img = np.array(self.gige.image2.image,dtype='float')
        #img = Util.threshold_array(img, self.threshold)
        if self.orientation == 'action0':
            self.profile = img
            self.x = self.x0
            self.y = self.y0
        elif self.orientation == 'action90':
            self.profile = np.rot90(img)
            self.x = self.y0
            self.y = self.x0
        elif self.orientation == 'action180':
            self.profile = np.rot90(img,2)
            self.x = self.x0
            self.y = self.y0
        elif self.orientation == 'action270':
            self.profile = np.rot90(img,3)
            self.x = self.y0
            self.y = self.x0
        elif self.orientation == 'action0_flip':
            self.profile = np.fliplr(img)
            self.x = self.x0
            self.y = self.y0
        elif self.orientation == 'action90_flip':
            self.profile = np.rot90(np.fliplr(img))
            self.x = self.y0
            self.y = self.x0
        elif self.orientation == 'action180_flip':
            self.profile = np.rot90(np.fliplr(img),2)
            self.x = self.x0
            self.y = self.y0
        elif self.orientation == 'action270_flip':
            self.profile = np.rot90(np.fliplr(img),3)
            self.x = self.y0
            self.y = self.x0

        self.N = np.size(self.y)
        self.M = np.size(self.x)

        #print(self.M)
        #print(self.N)

        #angle = -0.2
        #self.profile = ndimage.rotate(self.profile, angle, reshape=False)
        #self.profile = sktransform.rotate(self.profile, angle)

        temp_profile = Util.threshold_array(self.profile, self.threshold)

        self.intensity = np.mean(temp_profile)
        self.projection_x = np.mean(temp_profile, axis=0)
        self.projection_y = np.mean(temp_profile, axis=1)

        if self.roi is not None:
            xs = np.array([float(self.roi.red_x.text()),float(self.roi.blue_x.text())])
            ys = np.array([float(self.roi.red_y.text()),float(self.roi.blue_y.text())])
            #xs = np.array([self.roi[0],self.roi[2]])
            #ys = np.array([self.roi[1],self.roi[3]])
            x1 = np.min(xs)
            x2 = np.max(xs)
            y1 = np.min(ys)
            y2 = np.max(ys)

            roi_mask_x = np.logical_and(self.xx>x1,self.xx<x2)
            roi_mask_y = np.logical_and(self.yy>y1,self.yy<y2)
            roi_mask = np.logical_and(roi_mask_x,roi_mask_y)
            masked_profile = temp_profile*roi_mask
            masked_profile -= np.min(masked_profile[roi_mask])
            self.projection_x = np.mean(masked_profile,axis=0)
            self.projection_y = np.mean(masked_profile,axis=1)

            xwidth = np.sum(roi_mask_x>0)*self.dx
            ywidth = np.sum(roi_mask_y>0)*self.dx
        else:
            xwidth = self.FOV
            ywidth = self.FOV

        # get beam statistics
        self.cx, self.cy, self.wx, self.wy, wx2, wy2 = self.beam_analysis(self.projection_x, self.projection_y, xwidth, ywidth)
        # add imager state to validity
        if 'MONO' in self.imager_prefix or 'SL' in self.imager_prefix:
            imager_state = 'YAG'
        elif 'IM' in self.imager_prefix:
            imager_state = self.states_list[self.state.get()]
        elif 'MEC' in self.imager_prefix or 'XCS' in self.imager_prefix:
            imager_state = 'YAG'
        else:
            #imager_state = self.states_list[self.state.get()]
            imager_state = self.state.get()
        imager_in = 'YAG' in imager_state or 'DIAMOND' in imager_state

        self.centroid_is_valid = self.centroid_is_valid
        #self.centroid_is_valid = True

        x_center = Util.coordinate_to_pixel(self.cx, self.dx*self.xbin, self.M)
        y_center = Util.coordinate_to_pixel(self.cy, self.dx*self.ybin, self.N)

        #print(self.cx)
        #print(self.cy)

        try:
            if self.centroid_is_valid:
                self.x_bm_ctr.put(self.cx)
                self.y_bm_ctr.put(self.cy)
            else:
                self.x_bm_ctr.put(np.nan)
                self.y_bm_ctr.put(np.nan)
        except:
            pass
            #print('Write access not allowed')
        #print(x_center)
        #print(y_center)

        try:
            self.lineout_x = temp_profile[int(y_center), :]
            self.lineout_y = temp_profile[:, int(x_center)]
        except:
            self.lineout_x = self.projection_x
            self.lineout_y = self.projection_y


        # gaussian fits
        try:
            fit_x = self.amp_x * np.exp(
                -(self.x - self.cx) ** 2 / 2 / (self.wx / 2.355) ** 2)
        except RuntimeWarning:
            fit_x = np.zeros_like(self.lineout_x)
        try:
            fit_y = self.amp_y * np.exp(
                -(self.y - self.cy) ** 2 / 2 / (self.wy / 2.355) ** 2)
        except RuntimeWarning:
            fit_y = np.zeros_like(self.lineout_y)


        self.fit_x = fit_x
        self.fit_y = fit_y

        self.time_stamp = time_stamp

        return img, time_stamp
        #except:
        #    self.lineout_x = np.zeros_like(self.x_lineout)
        #    self.lineout_y = np.zeros_like(self.y_lineout)
        #    print('no image')
        #    return np.zeros((2048, 2048))


