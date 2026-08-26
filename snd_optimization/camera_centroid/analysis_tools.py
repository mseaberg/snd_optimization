import numpy as np
import imageio
import scipy.ndimage.interpolation as interpolate
import scipy.ndimage as ndimage
import matplotlib.pyplot as plt
import os

local_path = os.path.dirname(os.path.abspath(__file__))


class YagAlign:

    def __init__(self):

        # the TEMPLATE
        im0 = imageio.imread(local_path+"/pattern.png")[:, :, 3]
        Nt, Mt = np.shape(im0)
        im0 = np.pad(im0,
                     ((int((512 - Nt) / 2 + 1), int((512 - Nt) / 2)), (int((512 - Mt) / 2 + 1), int((512 - Mt) / 2))),
                     mode='constant')
        self.Nt, self.Mt = np.shape(im0)

        self.im0 = np.array(im0, dtype=float)
        # self.im0 = 255.0-im0

        x = np.linspace(-self.Mt / 2, self.Mt / 2 - 1, self.Mt)
        fx_max = 0.5
        fx = x * fx_max / np.max(x)

        y = np.linspace(-self.Nt / 2, self.Nt / 2 - 1, self.Nt)
        fy_max = 0.5
        fy = y * fy_max / np.max(y)

        self.fx, self.fy = np.meshgrid(fx, fy)

        self.fr = np.sqrt(self.fx ** 2 + self.fy ** 2)
        self.ftheta = np.arctan2(self.fy, self.fx)

        self.logbase = 1.1

    def check_alignment(self, data):

        # assume that the data coming in is already pretty well-centered
        ims = {}
        #data = np.fliplr(data)
        # crop out one corner
        ims[0] = data[0:200, 0:200]
        # get the average border value
        max0 = self.get_borderval(ims[0])
        # normalize image
        ims[0] = (ims[0] - np.min(ims[0])) / (max0 - np.min(ims[0])) * 255
        # pad image up to a 512x512 array
        ims[0] = np.pad(ims[0], ((0, 512 - 200), (0, 512 - 200)), 'constant',
                        constant_values=self.get_borderval(ims[0]))
        ims[1] = data[0:200, 1848:]
        max1 = self.get_borderval(ims[1])
        ims[1] = (ims[1] - np.min(ims[1])) / (max1 - np.min(ims[1])) * 255
        ims[1] = np.pad(ims[1], ((0, 512 - 200), (512 - 200, 0)), 'constant',
                        constant_values=self.get_borderval(ims[1]))
        ims[2] = data[1848:, 0:200]
        max2 = self.get_borderval(ims[2])
        ims[2] = (ims[2] - np.min(ims[2])) / (max2 - np.min(ims[2])) * 255
        ims[2] = np.pad(ims[2], ((512 - 200, 0), (0, 512 - 200)), 'constant',
                        constant_values=self.get_borderval(ims[2]))
        ims[3] = data[1848:, 1848:]
        max3 = self.get_borderval(ims[3])
        ims[3] = (ims[3] - np.min(ims[3])) / (max3 - np.min(ims[3])) * 255
        ims[3] = np.pad(ims[3], ((512 - 200, 0), (512 - 200, 0)), 'constant',
                        constant_values=self.get_borderval(ims[3]))

        shifts = {}
        transforms = {}
        for i in range(4):
            shifts[i], transforms[i] = self.get_transform(ims[i])

        contrast = np.zeros(4)
        for i in range(4):
            contrast[i] = self.get_contrast(shifts[i])['avg']

        translation = np.zeros((4, 2))
        rotation = np.zeros(4)
        scale = np.zeros(4)
        for i in range(4):
            scale[i] = transforms[i]['scale']
            rotation[i] = transforms[i]['theta']
            translation[i, :] = transforms[i]['translation']

        output = {}
        output['shifts'] = shifts
        output['scale'] = scale
        output['contrast'] = contrast
        output['rotation'] = rotation
        output['translation'] = translation

        return output

    @staticmethod
    def get_contrast(img):
        img[img < 0] = 0
        img = img - np.min(img)
        line1 = np.mean(img[220:250, 220:250], axis=1)
        line2 = np.mean(img[220:250, 259:290], axis=0)
        line3 = np.mean(img[260:290, 220:250], axis=0)
        line4 = np.mean(img[260:290, 260:290], axis=1)

        norm = np.mean(img[310:370, 220:295])

        # r1 = np.std(line1/norm)*np.sqrt(2)*2
        # r2 = np.std(line2/norm)*np.sqrt(2)*2
        # r3 = np.std(line3/norm)*np.sqrt(2)*2
        # r4 = np.std(line4/norm)*np.sqrt(2)*2
        # line1 = line1/norm
        # line2 = line2/norm
        # line3 = line3/norm
        # line4 = line4/norm
        r1 = np.std(line1 / np.max(line1)) * np.sqrt(2) * 2
        r2 = np.std(line2 / np.max(line2)) * np.sqrt(2) * 2
        r3 = np.std(line3 / np.max(line3)) * np.sqrt(2) * 2
        r4 = np.std(line4 / np.max(line4)) * np.sqrt(2) * 2

        # r1 = (np.max(line1)-np.min(line1))/(np.max(line1)+np.min(line1))
        # r2 = (np.max(line2)-np.min(line2))/(np.max(line2)+np.min(line2))
        # r3 = (np.max(line3)-np.min(line3))/(np.max(line3)+np.min(line3))
        # r4 = (np.max(line4)-np.min(line4))/(np.max(line4)+np.min(line4))
        r_avg = (r1 + r2 + r3 + r4) / 4.0

        contrast = {}
        contrast['1'] = r1
        contrast['2'] = r2
        contrast['3'] = r3
        contrast['4'] = r4
        contrast['avg'] = r_avg

        return contrast

    def get_transform(self, img):

        # log-polar coordinate system
        r1 = np.linspace(0, np.log(self.Nt / 8) / np.log(self.logbase), 128)
        r1p = np.linspace(0, np.log(self.Nt / 8) / np.log(self.logbase), 128)
        #theta1 = np.linspace(-np.pi / 2, np.pi / 2, 181)
        theta1 = np.linspace(-np.pi/36, np.pi/36, 11)
        #theta1 = np.linspace(-10*np.pi/180, 10*np.pi/180, 21)
        r1, theta1 = np.meshgrid(r1, theta1)

        r2 = np.exp(r1 * np.log(self.logbase))

        # coordinates to map to
        y = r2 * np.sin(theta1) + self.Nt / 2
        x = r2 * np.cos(theta1) + self.Mt / 2

        # FFT of each image
        F1 = self.FT(self.im0)
        F2 = self.FT(img)

        # map to log polar coordinates
        F1abs_out = np.empty_like(y)
        ndimage.map_coordinates(np.log(np.abs(F1) + 1), [y, x], output=F1abs_out, order=3)

        F2abs_out = np.empty_like(y)
        ndimage.map_coordinates(np.log(np.abs(F2) + 1), [y, x], output=F2abs_out, order=3)

        # Fourier transforms of log-polar FFTs
        M1 = np.fft.fft2(F1abs_out)
        M2 = np.fft.fft2(F2abs_out)

        # cross-correlation of M1 and M2
        cps = self.x_corr(M1, M2)
        cps_real = np.abs(np.fft.ifft2(cps))

        # set first column of x-corr to zero (by design we don't expect that zoom = 1)
        cps_real[:, 0] = 0
        # restrict zoom to be within a certain range
        cps_real[:, 32:] = 0

        # find correlation peak
        peak = np.unravel_index(np.argmax(cps_real), cps_real.shape)
        # determine rotation from peak location
        theta_offset = theta1[peak[0], 0] * 180 / np.pi + 5
        #theta_offset = theta1[peak[0], 0] * 180 / np.pi
        # determine zoom from peak location
        scale = self.logbase ** r1p[peak[1]]

        # get theta nearest to zero
        if theta_offset>45:
            theta_offset = 90-theta_offset
        #if theta_offset > 45:
        #    theta_offset = 90 - theta_offset
        #if theta_offset < 45:
        #    theta_offset = 90 - theta_offset

        # get background value of image
        bgval = self.get_borderval(img)

        # change scale and rotate based on above results
        zoom_out = interpolate.zoom(interpolate.rotate(img, -theta_offset, reshape=False,
                                                       mode='constant', cval=bgval), 1. / scale)
        # get new image size
        Nz, Mz = np.shape(zoom_out)

        # embed image in a size matching the template
        zoom_embed = np.zeros_like(self.im0) + bgval

        zoom_embed = self.embed_to(zoom_embed, zoom_out)

        ## figure out translation
        # we already have F1
        F2p = self.FT(zoom_embed)

        # cross-correlation for determining translation
        cps = self.x_corr(F1, F2p)
        cps_real = np.fft.fftshift(np.abs(np.fft.ifft2(np.fft.fftshift(cps))))

        # find peak (relative to center)
        peak = np.unravel_index(np.argmax(cps_real), cps_real.shape)
        peak = np.array(peak) - 256

        # line up with template based on translation
        shifted = np.roll(zoom_embed, peak, axis=(0, 1))

        transform = {}
        transform['scale'] = scale
        transform['theta'] = theta_offset
        transform['translation'] = peak

        return shifted, transform

    @staticmethod
    def FT(img):
        N, M = np.shape(img)
        F = np.fft.fftshift(np.fft.fft2(np.fft.fftshift(img - np.mean(img))))
        # remove discontinuity at zero
        F[int(N / 2), int(M / 2)] = F[int(N / 2), int(M / 2) - 1]
        return F

    @staticmethod
    def x_corr(F1, F2):
        cps = F1 * np.conj(F2) / (np.abs(F1) * np.abs(F2) + np.finfo(float).eps)

        return cps

    @staticmethod
    def get_borderval(img, radius=None):
        """
        Given an image and a radius, examine the average value of the image
        at most radius pixels from the edge
        """
        if radius is None:
            mindim = min(img.shape)
            radius = max(1, mindim // 20)
        mask = np.zeros_like(img, dtype=bool)
        mask[:, :radius] = True
        mask[:, -radius:] = True
        mask[:radius, :] = True
        mask[-radius:, :] = True

        mean = np.median(img[mask])
        return mean

    @classmethod
    def embed_to(cls, where, what):
        """
        Given a source and destination arrays, put the source into
        the destination so it is centered and perform all necessary operations
        (cropping or aligning)

        Args:
            where: The destination array (also modified inplace)
            what: The source array

        Returns:
            The destination array
        """
        slices_from, slices_to = cls._get_emslices(where.shape, what.shape)

        where[slices_to[0], slices_to[1]] = what[slices_from[0], slices_from[1]]
        return where

    @staticmethod
    def _get_emslices(shape1, shape2):
        """
        Common code used by :func:`embed_to` and :func:`undo_embed`
        """
        slices_from = []
        slices_to = []
        for dim1, dim2 in zip(shape1, shape2):
            diff = dim2 - dim1
            # In fact: if diff == 0:
            slice_from = slice(None)
            slice_to = slice(None)

            # dim2 is bigger => we will skip some of their pixels
            if diff > 0:
                # diff // 2 + rem == diff
                rem = diff - (diff // 2)
                # rem = diff % 2
                slice_from = slice(diff // 2, dim2 - rem)
            if diff < 0:
                diff *= -1
                rem = diff - (diff // 2)
                # rem = diff % 2
                slice_to = slice(diff // 2, dim1 - rem)
            slices_from.append(slice_from)
            slices_to.append(slice_to)
        return slices_from, slices_to

class XTESAlign:

    def __init__(self):

        # the TEMPLATE
        im0 = imageio.imread(local_path+"/XTES_pattern.png")[:, :, 3]
#         im0 = imageio.imread(local_path+"/XTES_pattern_zoom_out.png")[:, :, 3]

        Nt, Mt = np.shape(im0)
        Nd = 1024
        im0 = np.pad(im0,
                     ((int((Nd - Nt) / 2 + 1), int((Nd - Nt) / 2)), (int((Nd - Mt) / 2 + 1), int((Nd - Mt) / 2))),
                     mode='constant')

        self.Nt, self.Mt = np.shape(im0)

        self.im0 = np.array(im0, dtype=float)
        # self.im0 = 255.0-im0

        x = np.linspace(-self.Mt / 2, self.Mt / 2 - 1, self.Mt)
        fx_max = 0.5
        fx = x * fx_max / np.max(x)

        y = np.linspace(-self.Nt / 2, self.Nt / 2 - 1, self.Nt)
        fy_max = 0.5
        fy = y * fy_max / np.max(y)

        self.fx, self.fy = np.meshgrid(fx, fy)

        self.fr = np.sqrt(self.fx ** 2 + self.fy ** 2)
        self.ftheta = np.arctan2(self.fy, self.fx)

        self.logbase = 1.1

    def check_alignment(self, data):

        Nt, Mt = np.shape(data)
        Nd = 1024

        bgval = self.get_borderval(data)

        data = data - bgval
        dataEmbed = np.zeros((Nd, Nd))

        data = self.embed_to(dataEmbed, data)

        #data = np.pad(data,
        #             ((int((Nd - Nt) / 2 + 1), int((Nd - Nt) / 2)),
        #              (int((Nd - Mt) / 2 + 1), int((Nd - Mt) / 2))),
        #             mode='constant', constant_values=self.get_borderval(data))

        # assume that the data coming in is already pretty well-centered
        shifts, transforms = self.get_transform(data)

        scale = transforms['scale']
        rotation = transforms['theta']
        translation = transforms['translation']

        output = {}
        output['shifts'] = shifts
        output['scale'] = scale
        output['contrast'] = 0
        output['rotation'] = rotation
        output['translation'] = translation

        return output

    def get_transform(self, img):

        Ni, Mi = np.shape(img)

        Nr = 256

        # log-polar coordinate system
        r1 = np.linspace(0, np.log(self.Nt / 8) / np.log(self.logbase), Nr)
        r1p = np.linspace(0, np.log(self.Nt / 8) / np.log(self.logbase), Nr)

        # this works much better if a wide range is used...
        theta1 = np.linspace(-np.pi/2, np.pi / 2, 181)
        r1, theta1 = np.meshgrid(r1, theta1)

        r2 = np.exp(r1 * np.log(self.logbase))

        # coordinates to map to
        y = r2 * np.sin(theta1) + self.Nt / 2
        x = r2 * np.cos(theta1) + self.Mt / 2

        # FFT of each image
        F1 = self.FT(self.im0)
        F2 = self.FT(img)

        # map to log polar coordinates
        F1abs_out = np.empty_like(y)
        ndimage.map_coordinates(np.log(np.abs(F1) + 1), [y, x], output=F1abs_out, order=3)

        #plt.figure()
        #plt.imshow(F1abs_out)

        F2abs_out = np.empty_like(y)
        ndimage.map_coordinates(np.log(np.abs(F2) + 1), [y, x], output=F2abs_out, order=3)

        #plt.figure()
        #plt.imshow(F2abs_out)

        # Fourier transforms of log-polar FFTs
        M1 = np.fft.fft2(F1abs_out)
        M2 = np.fft.fft2(F2abs_out)

        # cross-correlation of M1 and M2
        cps = self.x_corr(M1, M2)
        cps_real = np.abs(np.fft.ifft2(cps))

        plt.figure()
        plt.imshow(cps_real)

        # set first column of x-corr to zero (by design we don't expect that zoom = 1)
        cps_real[:, 0] = 0
        # restrict zoom to be within a certain range
        # cps_real[:, 32:] = 0

#         plt.figure()
#         plt.imshow(cps_real)

        # find correlation peak
        peak = np.unravel_index(np.argmax(cps_real), cps_real.shape)

        # determine zoom from peak location
        if peak[1] > Nr/2:
            scale_peak = Nr-peak[1]
            scale = self.logbase**(-r1p[scale_peak])
        else:
            scale = self.logbase**r1p[peak[1]]

        # determine rotation from peak location
        print(peak[0])
        print(theta1[peak[0], 0] * 180 / np.pi)
        # theta_offset = theta1[peak[0], 0] * 180 / np.pi + 18
#         theta_offset = theta1[peak[0], 0] * 180 / np.pi + 90
        theta_offset = theta1[peak[0],0] * 180/np.pi + 90

        # get theta nearest to zero
        if theta_offset > 45:
            theta_offset = 90 - theta_offset
            #print(theta_offset)
        if theta_offset < -45:
            theta_offset = theta_offset + 90
            
        print(theta_offset)

        # get background value of image
        bgval = self.get_borderval(img)

        # change scale and rotate based on above results
        zoom_out = interpolate.zoom(interpolate.rotate(img, -theta_offset, reshape=False,
                                                       mode='constant', cval=bgval), 1. / scale)
        # get new image size
        Nz, Mz = np.shape(zoom_out)

        # embed image in a size matching the template
        zoom_embed = np.zeros_like(self.im0) + bgval

        zoom_embed = self.embed_to(zoom_embed, zoom_out)

        #plt.figure()
        #plt.imshow(zoom_embed)

        ## figure out translation
        # we already have F1
        F2p = self.FT(zoom_embed)

        # cross-correlation for determining translation
        cps = self.x_corr(F1, F2p)
        cps_real = np.fft.fftshift(np.abs(np.fft.ifft2(np.fft.fftshift(cps))))

        plt.figure()
        plt.imshow(cps_real)

        # find peak (relative to center)
        peak = np.unravel_index(np.argmax(cps_real), cps_real.shape)
        peak = np.array(peak) - int(Ni/2)

        # line up with template based on translation
        shifted = np.roll(zoom_embed, peak, axis=(0, 1))

        transform = {}
        transform['scale'] = scale
        transform['theta'] = theta_offset
        transform['translation'] = peak

        return shifted, transform

    @staticmethod
    def FT(img):
        N, M = np.shape(img)
        F = np.fft.fftshift(np.fft.fft2(np.fft.fftshift(img - np.mean(img))))
        # remove discontinuity at zero
        F[int(N / 2), int(M / 2)] = F[int(N / 2), int(M / 2) - 1]
        return F

    @staticmethod
    def x_corr(F1, F2):
        cps = F1 * np.conj(F2) / (np.abs(F1) * np.abs(F2) + np.finfo(float).eps)

        return cps

    @staticmethod
    def get_borderval(img, radius=None):
        """
        Given an image and a radius, examine the average value of the image
        at most radius pixels from the edge
        """
        if radius is None:
            mindim = min(img.shape)
            radius = max(1, mindim // 20)
        mask = np.zeros_like(img, dtype=bool)
        mask[:, :radius] = True
        mask[:, -radius:] = True
        mask[:radius, :] = True
        mask[-radius:, :] = True

        mean = np.median(img[mask])
        return mean

    @classmethod
    def embed_to(cls, where, what):
        """
        Given a source and destination arrays, put the source into
        the destination so it is centered and perform all necessary operations
        (cropping or aligning)

        Args:
            where: The destination array (also modified inplace)
            what: The source array

        Returns:
            The destination array
        """
        slices_from, slices_to = cls._get_emslices(where.shape, what.shape)

        where[slices_to[0], slices_to[1]] = what[slices_from[0], slices_from[1]]
        return where

    @staticmethod
    def _get_emslices(shape1, shape2):
        """
        Common code used by :func:`embed_to` and :func:`undo_embed`
        """
        slices_from = []
        slices_to = []
        for dim1, dim2 in zip(shape1, shape2):
            diff = dim2 - dim1
            # In fact: if diff == 0:
            slice_from = slice(None)
            slice_to = slice(None)

            # dim2 is bigger => we will skip some of their pixels
            if diff > 0:
                # diff // 2 + rem == diff
                rem = diff - (diff // 2)
                # rem = diff % 2
                slice_from = slice(diff // 2, dim2 - rem)
            if diff < 0:
                diff *= -1
                rem = diff - (diff // 2)
                # rem = diff % 2
                slice_to = slice(diff // 2, dim1 - rem)
            slices_from.append(slice_from)
            slices_to.append(slice_to)
        return slices_from, slices_to
