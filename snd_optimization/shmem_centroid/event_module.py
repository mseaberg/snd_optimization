import numpy as np
from util import Util
from config_util import parse_config


class ProcessEvent:

    def __init__(self,config):

        pars = parse_config(config)
        self.detnames = pars['detnames']
        roi = pars['roi']

        self.roi = np.s_[roi[2]:roi[3],roi[0]:roi[1]]        

    def per_event(self, det_dict, evt):

        # aliases
        zyla = det_dict['zyla']
        ipm4 = det_dict['XCS-SB1-BMMON']

        if zyla.image(evt) is None: continue
        if ipm4.get(evt) is None: continue

        # select image ROI
        #img0 = np.copy(det0.image(evt)[ymin:ymax,xmin:xmax])
        print('getting image')
        img0 = zyla.image(evt)
        norm = ipm4.get(evt).TotalIntensity()

        img1 = np.copy(img0[self.roi])
        img1 -= thresh
        img1[img1<0] = 0

        #if np.sum(img1)<1e5:continue

        N,M = np.shape(img1)

        lineout_x = Util.get_horizontal_lineout(img1)
        lineout_y = Util.get_vertical_lineout(img1)

        thresh2 = 100
        # disregard the centroid calculation if intensity is below the threshold
        if np.sum(img1)>thresh2:
            cx, wx = gaussian_stats(x, lineout_x)
            cy, wy = gaussian_stats(y, lineout_y)
        else:
            cx = np.array(np.nan)
            cy = np.array(np.nan)
            wx = np.array(np.nan)
            wy = np.array(np.nan)

        intensity = np.sum(img1)/norm
        #intensity = np.mean(img1)
        # require ipm to be larger than some number (default 50)
        if norm<ipm_threshold:
            #pass
            intensity = np.array(np.nan)




