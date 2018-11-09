# This file is part of HeaderService
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import HeaderService
import math

"""This module describe the CCD/Camera coordinate systems as described in
LCA-13501
"""

#
# From Table 8 and Table 11 of LCA-13501
#
# (vertical x horizontal) dimensions
# ------------------------------------------------------------------------
# | Quantity          |  e2V CCD     | ITL CCD     | Designator
# ------------------------------------------------------------------------
# | Segment pixels    | 2002 x 512  | 2000 x 509  | dimv  x dimh
# | Active area(x,y)  | 4004 x 4096 | 4000 x 4072 | ccdax x ccday
# | CCD physical size | 4197 x 4200 | 4198 x 4198 | ccdpx x ccdpy
# | Inter-CCD gaps    |   28 x 25   |   27 x 27   | gap_inx x gap_iny
# | Pitch of rafts    |12700 x 12700|12700 x 12700| raftx x rafty
# | Gaps at edges     |             |             |
# | o frafts          | 26.5 x 25   |  26 x 26    | gap_outx x gap_outy
# | -----------------------------------------------------------------------
#
# CCD-related parameters for defining NOAO Mosaic keywords for
# assembling single-CCD images
# ------------------------------------------------------------------------
# | Quantity          |  e2V CCD     | ITL CCD    | Designator
# ------------------------------------------------------------------------
# | Pre-scan pixels   |  10         |     3       | preh
# | Over-scan pixels  |  22         |    32       | overh
# | Vert-overscan pix |  46         |    48       | overv
#

SCAN_GEOM = {}
SCAN_GEOM['ITL'] = {'dimv':  2000,
                    'dimh':  509,
                    'preh':  3,
                    'overh': 32,
                    'overv': 48}

SCAN_GEOM['E2V'] = {'dimv': 2002,
                    'dimh': 512,
                    'preh':  10,
                    'overh': 54,
                    'overv': 46}

# Mapping for the CHANNEL (Output number or HDU) keyword to the segments
CHANNEL = {}
CHANNEL['E2V'] = {'00': 16,
                  '01': 15,
                  '02': 14,
                  '03': 13,
                  '04': 12,
                  '05': 11,
                  '06': 10,
                  '07':  9,
                  '10':  1,
                  '11':  2,
                  '12':  3,
                  '13':  4,
                  '14':  5,
                  '15':  6,
                  '16':  7,
                  '17':  8}

CHANNEL['ITL'] = {'00':  8,
                  '01':  7,
                  '02':  6,
                  '03':  5,
                  '04':  4,
                  '05':  3,
                  '06':  2,
                  '07':  1,
                  '10':  9,
                  '11': 10,
                  '12': 11,
                  '13': 12,
                  '14': 13,
                  '15': 14,
                  '16': 15,
                  '17': 16}

# And now the inverse, the segment for each Output number or HDU
# SEGNAME['E2V'] =  {v:k for k, v in CHANNEL['E2V'].items()}
# SEGNAME['ITL'] =  {v:k for k, v in CHANNEL['ITL'].items()}


# It turns out that the HDU (aka SEGNAME) is unrelated to the CHANNEL
# definition of Figure 1 of LCA-13501 and it is the same for E2V and
# ITL sensors
SEGNAME = {}
SEGNAME['E2V'] = {1: '10',
                  2: '11',
                  3: '12',
                  4: '13',
                  5: '14',
                  6: '15',
                  7: '16',
                  8: '17',
                  9: '07',
                  10: '06',
                  11: '05',
                  12: '04',
                  13: '03',
                  14: '02',
                  15: '01',
                  16: '00'}
SEGNAME['ITL'] = SEGNAME['E2V']


class CCDGeom:

    def __init__(self, vendor,
                 segname='Segment',
                 preh=None,
                 overh=None,
                 overv=None,
                 xpixelscale=0.105,
                 ypixelscale=0.105,
                 ):
        self.vendor = vendor
        self.segname = segname
        self.xpixelscale = xpixelscale
        self.ypixelscale = ypixelscale

        # Load default unless defined
        if preh:
            self.preh = preh
        else:
            self.preh = SCAN_GEOM[vendor]['preh']

        if overh:
            self.overh = overh
        else:
            self.overh = SCAN_GEOM[vendor]['overh']

        if overv:
            self.overv = overv
        else:
            self.overv = SCAN_GEOM[vendor]['overv']

        self.dimh = SCAN_GEOM[vendor]['dimh']
        self.dimv = SCAN_GEOM[vendor]['dimv']

        # Make this info available as part of the class
        self.CHANNEL = CHANNEL[vendor]
        self.SEGNAME = SEGNAME[vendor]

        # Update the primary, we do this only once at __init__ unless we change
        # overh/overv/dimh/dimv

        self.primary()

    def get_extension(self, extname):

        """ A common function to get the extension key/value dicti"""

        if extname == 'PRIMARY':
            self.primary()
            return self.PRIMARY
        else:
            return self.extension(extname)

    def primary(self):

        """Update primary hdu"""

        self.CCD_MANU = self.vendor
        # DETSIZE and DATASEC are the same for all segments
        self.DETSIZE = '[1:{:d},1:{:d}]'.format(8*self.dimh, 2*self.dimv)
        self.DATASEC = '[{:d}:{:d},1:{:d}]'.format(self.preh+1,
                                                   self.preh+self.dimh,
                                                   self.dimv)
        self.PRIMARY = {}
        self.PRIMARY['DETSIZE'] = self.DETSIZE
        self.PRIMARY['CCD_MANU'] = self.CCD_MANU
        self.PRIMARY['HEADVER'] = HeaderService.version

    def extension(self, Segment):

        Sx = int(Segment[0])
        Sy = int(Segment[1])

        if self.vendor == 'ITL':
            EXTENSION_DATA = self.mosaic_ITL(Sx, Sy)
        elif self.vendor == 'E2V':
            EXTENSION_DATA = self.mosaic_E2V(Sx, Sy)
        else:
            raise ValueError('Vendor: {} not in list '.format(self.vendor))

        EXTENSION_DATA['CHANNEL'] = CHANNEL[self.vendor][Segment]
        EXTENSION_DATA['DETSIZE'] = self.DETSIZE
        EXTENSION_DATA['DATASEC'] = self.DATASEC
        EXTENSION_DATA['EXTNAME'] = '{}{}'.format(self.segname, Segment)
        return EXTENSION_DATA

    def mosaic_E2V(self, Sx, Sy):

        dsx1 = (Sy*self.dimh + 1)*(1 - Sx) + (Sy + 1)*self.dimh*Sx
        dsx2 = (Sy + 1)*self.dimh*(1 - Sx) + (Sy*self.dimh + 1)*Sx
        dsy1 = 2*self.dimv*(1 - Sx) + Sx
        dsy2 = (self.dimv + 1)*(1 - Sx) + self.dimv*Sx

        # EXTENSION_DATA = collections.OrderedDict()
        EXTENSION_DATA = {}
        EXTENSION_DATA['DTM1_1'] = 1. - 2.0*Sx
        EXTENSION_DATA['DTM1_2'] = 0
        EXTENSION_DATA['DTM2_1'] = 0
        EXTENSION_DATA['DTM2_2'] = 2.0*Sx - 1.
        EXTENSION_DATA['DTV1'] = (self.dimh + 1 + 2*self.preh)*Sx + Sy*self.dimh - self.preh
        EXTENSION_DATA['DTV2'] = (2*self.dimv + 1)*(1 - Sx)
        EXTENSION_DATA['DETSEC'] = "[{:d}:{:d},{:d}:{:d}]".format(dsx1, dsx2, dsy1, dsy2)
        return EXTENSION_DATA

    def mosaic_ITL(self, Sx, Sy):

        dsx1 = (Sy + 1)*self.dimh
        dsx2 = Sy*self.dimh + 1
        dsy1 = 2*self.dimv*(1 - Sx) + Sx
        dsy2 = (self.dimv + 1)*(1 - Sx) + self.dimv*Sx

        # EXTENSION_DATA = collections.OrderedDict()
        EXTENSION_DATA = {}
        EXTENSION_DATA['DTM1_1'] = -1.0
        EXTENSION_DATA['DTM1_2'] = 0
        EXTENSION_DATA['DTM2_1'] = 0
        EXTENSION_DATA['DTM2_2'] = 2.0*Sx - 1
        EXTENSION_DATA['DTV1'] = self.dimh + 1 + Sy*self.dimh + self.preh
        EXTENSION_DATA['DTV2'] = (2*self.dimv + 1)*(1 - Sx)
        EXTENSION_DATA['DETSEC'] = "[{:d}:{:d},{:d}:{:d}]".format(dsx1, dsx2, dsy1, dsy2)
        return EXTENSION_DATA

    def get_channel(self, Segment):
        return CHANNEL[self.vendor][Segment]

    def wcs_tan_matrix(self, ra, dec, rot_angle=0):

        '''
        Compute the common section of the WCS Tangential projection matrix
        See for a definition http://danmoser.github.io/notes/gai_fits-imgs.html
        '''

        CDELT1 = self.xpixelscale
        CDELT2 = self.ypixelscale,
        CROTA2 = rot_angle
        wcs = {'CTYPE1': 'RA---TAN',
               'CTYPE2': 'DEC--TAN',
               'CUNIT1': 'deg',
               'CUNIT2': 'deg',
               'CRVAL1': ra,
               'CRVAL2': dec,
               # ------------------------------------------
               # We will use a function for these later on
               # 'CRPIX1' : 5,
               # 'CRPIX2' : 10,
               # ------------------------------------------
               'CROTA2': rot_angle,
               'CDELT1': self.xpixelscale,
               'CDELT2': self.ypixelscale,
               'CD1_1': CDELT1*math.cos(CROTA2),
               'CD1_2': -CDELT2*math.sin(CROTA2),
               'CD2_1': CDELT1*math.sin(CROTA2),
               'CD2_2': CDELT2*math.cos(CROTA2),
               }
        return wcs

    def wcs_CCD(self, Sx, Sy):

        if self.vendor == 'E2V':
            PC1_1 = 0
            PC1_2 = 1 - 2*Sx
            PC2_1 = 1 - 2*Sx
            PC2_2 = 0
            CDELT1 = 1
            CDELT2 = 1
            CRPIX1 = 0
            CRPIX2 = 0
            CRVAL1 = Sx*(2*self.dimv + 1)
            CRVAL2 = Sx*(self.dimh + 1) + Sy*self.dimh+(2*Sx - 1)*self.preh
        elif self.vendor == 'ITL':
            PC1_1 = 0
            PC1_2 = 1 - 2*Sx
            PC2_1 = -1
            PC2_2 = 0
            CDELT1 = 1
            CDELT2 = 1
            CRPIX1 = 0
            CRPIX2 = 0
            CRVAL1 = Sx*(2*self.dimv+1)
            CRVAL2 = self.dimh + 1 + Sy*self.dimh - self.preh
        return PC1_1, PC1_2, PC2_1, PC2_2, CDELT1, CDELT2, CRPIX1, CRPIX2, CRVAL1, CRVAL2


if __name__ == "__main__":

    ccd_ITL = CCDGeom('ITL')
    ccd_E2V = CCDGeom('E2V')

    ext01 = ccd_ITL.extension('01')
    ext02 = ccd_ITL.extension('02')
    print(ext01)
    print(ext02)

    ext01 = ccd_E2V.extension('01')
    ext02 = ccd_E2V.extension('02')
    print(ext01)
    print(ext02)


# Adding WCS TAN proojection
'''
# http://danmoser.github.io/notes/gai_fits-imgs.html

WCSAXES =                    2 / WCS Dimensionality
CTYPE1  = 'RA---TAN'           / Coordinate type
CTYPE2  = 'DEC--TAN'           / Coordinate type
CUNIT1  = 'deg     '
CUNIT2  = 'deg     '
CRVAL1  =              202.473 / [deg] WCS Reference Coordinate (RA)
CRVAL2  =              47.1967 / [deg] WCS Reference Coordinate (DEC)
CRPIX1  =              150.500 / Reference pixel axis 1
CRPIX2  =              150.500 / Reference pixel axis 2
CD1_1   =        4.2365384E-01 / DL/DX World coordinate transformation matrix
CD1_2   =       -9.0582417E-01 / DL/DY World coordinate transformation matrix
CD2_1   =        9.0582417E-01 / DM/DX World coordinate transformation matrix
CD2_2   =        4.2365384E-01 / DM/DY World coordinate transformation matrix
EQUINOX =              2000.00 / Equinox of coordinates
RADESYS = 'FK5     '           / Telescope coordinate system

#
# In addition we could add  CDELT1/CDEL2 and
# CROTA2  =              0.00000 / Rotation in degrees.
# CDELT1  =           0.00166667 /Coordinate increment per pixel in DEGREES/PIXEL
# CDELT2  =          -0.00166667 /Coordinate increment per pixel in DEGREES/PIXEL
#
# CD1_1 = CDELT1*cos(CROTA2)
# CD1_2 = -CDELT2*sin(CROTA2)
# CD2_1 = CDELT1*sin(CROTA2)
# CD2_2 = CDELT2*cos(CROTA2)

header  = { 'NAXIS'  : 2,
            'NAXIS1' : 5,
            'CTYPE1' : 'RA---TAN',
            'CRVAL1' : 45,
            'CRPIX1' : 5,
            'CUNIT1' : 'deg',
            'CDELT1' : -0.01,
            'NAXIS2' : 10,
            'CTYPE2' : 'DEC--TAN',
            'CRVAL2' : 30,
            'CRPIX2' : 10,
            'CUNIT2' : 'deg',
            'CDELT2' : +0.01,
         }

'''
