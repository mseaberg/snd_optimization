import numpy as np
from epics import PV
import json

with open('imager_info.json') as json_file:
    imager_info = json.load(json_file)

with open('imagers.db') as json_file:
    imagers_db = json.load(json_file)

line_list = [key for key in imager_info]

for line in line_list:
    imager_list = [key for key in imager_info[line]]
    print(imager_list)

    for imager in imager_list:
        prefix = imager_info[line][imager]['prefix']
        print(prefix)
       
        if imager in imagers_db.keys() and 'L0' in imager:
            cx = imagers_db[imager]['cx']
            cy = imagers_db[imager]['cy']
            resolution = imagers_db[imager]['pixel']
            print(cx)
            PV(prefix + 'CAM:X_RTCL_CTR').put(cx)
            PV(prefix + 'CAM:Y_RTCL_CTR').put(cy)
            PV(prefix + 'CAM:RESOLUTION').put(resolution)
