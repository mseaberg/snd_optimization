import sys
from util import Util
import psana
import numpy as np
from mpidata import mpidata 
import h5py
import scipy.ndimage.interpolation as interpolate
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import pandas
import h5py
import epics
from psmon import publish
from psmon.plots import Image,XYPlot
from crosscor import crosscor
import scipy
from scipy.optimize import curve_fit

def three_gaussian_2d(x,y,amp1,cenx1,ceny1,wid1,amp2,cenx2,ceny2,wid2,amp3,cenx3,ceny3,wid3,bg):
    g1 = amp1*np.exp(-((x-cenx1)**2+(y-ceny1)**2)/(2*wid1**2))
    g2 = amp2*np.exp(-((x-cenx2)**2+(y-ceny2)**2)/(2*wid2**2))
    g3 = amp3*np.exp(-((x-cenx3)**2+(y-ceny3)**2)/(2*wid3**2))

    return g1 + g2 + g3 + bg

def one_gaussian_2d(x,y,amp1,cenx1,ceny1,wid1,bg):
    g1 = amp1*np.exp(-((x-cenx1)**2+(y-ceny1)**2)/(2*wid1**2))
    return g1 + bg

def _gaussian(M, *args):
    x,y = M
    return three_gaussian_2d(x,y,*args)
    #return one_gaussian_2d(x,y,*args)

def fit_gaussian(X,Y,a,mask):
    xdata = np.vstack((X[mask].ravel(),Y[mask].ravel()))
    #p0 = (1,0,0,3,1)
    p0 = (1,0,0,3,
            1,0,-15,3,
            1,0,15,3,
            1)
    bounds = ([0,-1,-1,0,
        0,-15,-20,0,
        0,-15,-20,0,
        0],
        [1,1,1,5,
            1,15,20,5,
            1,15,20,5,
            2])
    px,covx = curve_fit(_gaussian,xdata,a[mask].ravel(),p0,bounds=bounds)


    return px, covx

def runclient(args,pars,comm,rank,size):

    sh_mem = args.live
    expName = args.experiment
    #expName = pars['exp_name']
    #hutchName = args.hutch.lower()
    hutchName = expName[0:3]
    runNum = args.run
    pars['run'] = runNum
    detName = pars['detName']
    thresh = pars['thresh']
    ipm_threshold = pars['ipm_threshold']
    ipmName = pars['ipmName']


    expName = expName
    update_events = pars['update_events']
    runString = 'exp=%s:run=%s:smd' % (expName, runNum)
    #runString = runNum
    #runString += ':dir=/reg/d/ffb/%s/%s/xtc:live' % (hutchName,expName)
    #print(runString)

    roi = pars['roi']
    xmin = roi[0]
    xmax = roi[1]
    ymin = roi[2]
    ymax = roi[3]


    # miscellaneous parameters
    dx = pars['pixel']

    N = ymax-ymin
    M = xmax-xmin

    x = np.linspace(xmin, xmax, M)*dx
    y = np.linspace(ymin, ymax, N)*dx

    calibDir = '/sdf/data/lcls/ds/%s/%s/calib' % (hutchName, expName)

    ds = []
    if sh_mem:
        
        psana.setOption('psana.calib-dir', calibDir)
        ds = psana.DataSource('shmem=psana.0:stop=no')
        
    else:
        ds = psana.DataSource(runString)

    det0 = psana.Detector(detName)
    ipm = psana.Detector(ipmName)

    nevents = np.empty(0)

    # initialize instance of the mpidata class for communication with the master process
#    md = mpidata()

    # initialize i1 (which resets after each update) depending on the rank of the process
    #i1 = int((rank-1)*update_events/(size-1))
    i1 = 0

    md = mpidata()

    
    i0 = -1

    avImage = None

    nevents = np.empty(0)

    # event loop
    for nevent,evt in enumerate(ds.events()):

        
        # check if we've reached the event limit        
        #if nevent == args.noe : break
        #if nevent%(size-1)!=rank-1: continue # different ranks look at different events

        if det0.calib(evt) is None: continue
        if ipm.get(evt) is None: continue

        norm = ipm.get(evt).TotalIntensity()
        if norm < ipm_threshold: continue

        # increment counter
        i1 += 1

        if avImage is None:
            avImage = det0.calib(evt)
        else:
            avImage += det0.calib(evt)
        

        i0 += 1

        #print(i1)

        #print(evt.keys())

        # send mpi data object to master when desired
        if i1 == update_events:

            md=mpidata()

            #print(i1)
            i1 = 0
            #print(i1)
            #if det0.image(evt) is None: continue
            #if ipm.get(evt) is None: continue



            # select image ROI
            #img0 = np.copy(det0.image(evt)[ymin:ymax,xmin:xmax])
            #img0 = det0.image(evt)
            #norm = ipm.get(evt).TotalIntensity()
            #img0[img0<20] = 0
            #img0 -= 20
            #img0[img0<20] = 0
            # check if the image needs to be rotated

            #img1 = np.copy(img0[ymin:ymax,xmin:xmax])
            #img1[img1<20] = 0
            #img1 -= thresh
            #img1[img1<0] = 0

            #if np.sum(img1)<1e5:continue

            #N,M = np.shape(img1)
            #print(N)
            #print(M)
            # get scan pv

            #### find peaks ####
            #print(np.shape(scan))

            #lineout_x = Util.get_horizontal_lineout(img1)
            #lineout_y = Util.get_vertical_lineout(img1)

            #thresh2 = 100
            # disregard the centroid calculation if intensity is below the threshold
            #if np.sum(img1)>thresh2:
            #    cx, wx = gaussian_stats(x, lineout_x)
            #    cy, wy = gaussian_stats(y, lineout_y)
            #else:
            #    cx = np.array(np.nan)
            #    cy = np.array(np.nan)
            #    wx = np.array(np.nan)
            #    wy = np.array(np.nan)

            #intensity = np.sum(img1)/norm
            #intensity = np.mean(img1)
            # require ipm to be larger than some number (default 50)
            #if norm<ipm_threshold:
               # #pass
            #    intensity = np.array(np.nan)


            #img0 = img0/np.max(img0)
            #md.addarray('cx',cx)
            #md.addarray('cy',cy)
            #md.addarray('wx',wx)
            #md.addarray('wy',wy)
            # normalize by ipm
            #md.addarray('intensity',intensity)
            #md.addarray('nevents',nevents[-1])
            #if rank==1:
            #    md.addarray('img',img0[ymin:ymax,xmin:xmax])
            md.small.event = nevent
            md.addarray('avImage',avImage)
           
            md.send()
            print('sent image')
            avImage = None
           # 
    md.endrun()


def runmaster(nClients,args,pars,comm,rank,size):

    print('running')

    update_events = pars['update_events']

    # get ROI info
    roi = pars['roi']
    xmin = roi[0]
    xmax = roi[1]
    ymin = roi[2]
    ymax = roi[3]
#
    # initialize arrays

    n = 30
    x = np.arange(2*n)-n
    
    X,Y = np.meshgrid(x,x)
    mask1 = np.abs(X)**2 + np.abs(Y)**2 > 1**2

    #dataDict = {}
    #dataDict['nevents'] = np.ones(N_event)*-1
    #dataDict['intensity'] = np.zeros(N_event)
    #dataDict['cx'] = np.zeros(N_event)
    #dataDict['cy'] = np.zeros(N_event)
    #dataDict['wx'] = np.zeros(N_event)
    #dataDict['wy'] = np.zeros(N_event)

    nevent = -1

    cx_PV = epics.PV('XCS:USER:SND:X_CENTROID')
    cy_PV = epics.PV('XCS:USER:SND:Y_CENTROID')
    wx_PV = epics.PV('XCS:USER:SND:X_WIDTH')
    wy_PV = epics.PV('XCS:USER:SND:Y_WIDTH')
    intensity_PV = epics.PV('XCS:USER:SND:INTENSITY')

    numEvents = 0

    i1 = 0

    updateEvents = 15
    avImage = None

    while nClients > 0:
        # Remove client if the run ended
        md = mpidata()
        rank1 = md.recv()
        #print(rank1)
        if md.small.endrun:
            nClients -= 1
        else:
            i1 += 1
            #nevents = np.append(nevents,md.nevents)
            #dataDict['nevents'] = update(md.nevents,dataDict['nevents']) 
            #dataDict['intensity'] = update(md.intensity,dataDict['intensity'])
            #dataDict['cx'] = update(md.cx,dataDict['cx'])
            #dataDict['cy'] = update(md.cy,dataDict['cy'])
            #dataDict['wx'] = update(md.wx,dataDict['wx'])
            #dataDict['wy'] = update(md.wy,dataDict['wy'])
            if avImage is None:
                avImage = md.avImage
            else:
                avImage += md.avImage





            #if rank1==1:
            #    numEvents += 1
            #    #if np.mod(numEvents,4)==0:
            #    circle = np.abs(x-
            #    imPlot = Image(numEvents,"image",md.img)
            #    publish.send("test_image",imPlot)
            #    print('sending image')

            if i1==updateEvents:
                numEvents += 15*update_events
                mask0 = np.zeros_like(avImage)
                mask0[400:575,25:125] = 1
                simg = scipy.ndimage.gaussian_filter(avImage,sigma=15)
                cc = crosscor(mask0.shape, mask0, 'symavg')
                a = cc(avImage/simg)
                ashape = a.shape
                center = [ashape[0]//2,ashape[1]//2]
                a_roi = a[center[0]-30:center[0]+30,center[1]-30:center[1]+30]
                try:
                    fy, covy = fit_gaussian(X,Y,a_roi,mask1)

                    fitPlot = three_gaussian_2d(X,Y,*fy)
                    
                    print(np.sum(np.diag(covy)))

                    fitUncertainty = np.sum(np.diag(covy))

                    if fitUncertainty>0.5:
                        cx_PV.put(np.nan)
                        cy_PV.put(np.nan)
                        intensity_PV.put(np.nan)

                    else:
                        cx_PV.put((np.abs(fy[5])+np.abs(fy[9]))/2)
                        cy_PV.put((np.abs(fy[6])+np.abs(fy[10]))/2)
                        intensity_PV.put((fy[4]+fy[8])/2)

                    #fitPlot = one_gaussian_2d(X,Y,*fy)
                    imFit = Image(numEvents,"fit",fitPlot,aspect_ratio=1)
                    publish.send("gaussian_fit",imFit)
                    print('fit succeeded')
                except:
                    print('fit failed')
                    cx_PV.put(np.nan)
                    cy_PV.put(np.nan)
                    intensity_PV.put(np.nan)
                #imFit = Image(numEvents,"fit",np.zeros((100,100)))
                #publish.send("gaussian_fit",imFit)

                #print(intensity)
                #cx_PV.put(cx*1e6)
                #cy_PV.put(cy*1e6)
                #wx_PV.put(wx*1e6)
                #wy_PV.put(wy*1e6)
                #intensity_PV.put(intensity)
                imAC = Image(numEvents,"auto_corr",a_roi*mask1,aspect_ratio=1)
                publish.send("auto_corr",imAC)

                i1 = 0
                imPlot = Image(numEvents,"average_image",avImage,aspect_ratio=1)
                #imPlot = Image(numEvents,"image",fitPlot)
                publish.send("average_image",imPlot)

                avImage = None

                #if True:
                #    numEvents += 1
                #    if np.mod(numEvents,4)==0:

                #        w_eff = np.sqrt(wx*wy)*1e6
                #        outer_rad = (x-cx*1e6)**2 + (y-cy*1e6)**2<(2*w_eff)**2
                #        inner_rad = (x-cx*1e6)**2 + (y-cy*1e6)**2>(2*w_eff-3)**2
                #        circle = np.logical_and(inner_rad,outer_rad).astype(float)*500
                #        #circle *= 500
                #        imPlot = Image(numEvents,"image",md.img+(circle),aspect_ratio=1)
                #        #imPlot = Image(numEvents,"image",md.img)
                #        publish.send("centroid_image",imPlot)
                #        print('sending image')



def gaussian_stats(x_data, y_data, thresh=0.1):

    # normalize input (and subtract any offset)
    y_norm = Util.normalize_trace(y_data)
    # threshold input
    y_data_thresh = Util.threshold_array(y_norm, thresh)

    # calculate centroid
    cx = np.sum(y_data_thresh * x_data) / np.sum(y_data_thresh)

    # calculate second moment
    sx = np.sqrt(np.sum(y_data_thresh * (x_data - cx) ** 2) / np.sum(y_data_thresh))
    fwx_guess = sx * 2.355

    guess = [cx, sx]

    try:
        mask = y_data_thresh > 0
        px, pcovx = optimize.curve_fit(Util.fit_gaussian, x_data[mask], y_norm[mask],p0=guess)
        sx = px[1]
        cx = px[0]
    except:
        print('Fit failed. Using second moment for width.')

    return cx, sx

               

def update(newValue,currentArray):

    if len(np.shape(currentArray))>1:
        currentArray = np.roll(currentArray,-1,axis=0)
        currentArray[-1,:] = newValue
    else:
        currentArray = np.roll(currentArray,-1)
        currentArray[-1] = newValue
    return currentArray


def running_average(arr, window):
    out = pandas.Series(arr).rolling(window, min_periods=1).mean().values
    return out



