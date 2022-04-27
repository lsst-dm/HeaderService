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
import logging
LOGGER = logging.getLogger(__name__)

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
SCAN_GEOM['ITL'] = {'dimv': 2000,
                    'dimh': 509,
                    'preh': 3,
                    'overh': 32,
                    'overv': 48,
                    'ccdax': 4000,
                    'ccday': 4072}

SCAN_GEOM['E2V'] = {'dimv': 2002,
                    'dimh': 512,
                    'preh': 10,
                    'overh': 54,
                    'overv': 46,
                    'ccdax': 4004,
                    'ccday': 4096}

# --- This is a copy of E2V to make it work for GC -----
SCAN_GEOM['DUMMY'] = {'dimv': 2002,
                      'dimh': 512,
                      'preh': 10,
                      'overh': 54,
                      'overv': 46,
                      'ccdax': 4004,
                      'ccday': 4096}

# Mapping for the CHANNEL (Output number or HDU) keyword to the segments
CHANNEL = {}
CHANNEL['E2V'] = {'00': 16,
                  '01': 15,
                  '02': 14,
                  '03': 13,
                  '04': 12,
                  '05': 11,
                  '06': 10,
                  '07': 9,
                  '10': 1,
                  '11': 2,
                  '12': 3,
                  '13': 4,
                  '14': 5,
                  '15': 6,
                  '16': 7,
                  '17': 8}

CHANNEL['ITL'] = {'00': 8,
                  '01': 7,
                  '02': 6,
                  '03': 5,
                  '04': 4,
                  '05': 3,
                  '06': 2,
                  '07': 1,
                  '10': 9,
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
SLAC_SEGNAME = {1: '10',
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

SEGNAME = {}
SEGNAME['LATISS'] = SLAC_SEGNAME
SEGNAME['ComCam'] = SLAC_SEGNAME
SEGNAME['LSSTCam'] = SLAC_SEGNAME
SEGNAME['GenericCamera'] = {1: '1'}


"""
Useful to mock up the message with the sensor list
to make the arrays with rafts, remove 40,04,00 and 44
rs = []
    for i in range(5):
        for j in reversed(range(5)):
            s = f"{j}{i}"
            rs.append(s)
    print(rs)
"""
RAFTS = {}
RAFTS['LATISS'] = ['22']
RAFTS['GenericCamera'] = ['']  # Making this up for now
RAFTS['ComCam'] = ['22']
RAFTS['LSSTCam'] = ['34', '24', '14',
                    '43', '33', '23', '13', '03',
                    '42', '32', '22', '12', '02',
                    '41', '31', '21', '11', '01',
                    '30', '20', '10']


def setup_primary():
    """
    Set the initial metadata for the PRIMARY HDU that it is independent
    of SAL Telemetry, only depends on vendor (ITL or E2V). For now we only
    setup the HeaderService version, but it's better to keep them separated
    """
    PRIMARY = {}
    PRIMARY['HEADVER'] = HeaderService.version
    return PRIMARY


# ----- Function for multiple sensors/CCDs
class CCDInfo:

    def __init__(self,
                 vendor,
                 segname='Segment',
                 logger=None,
                 xpixelscale=0.105,
                 ypixelscale=0.105,
                 crpix1=None,
                 crpix2=None,
                 ):
        self.vendor = vendor
        self.segname = segname

        # Figure out logging
        if logger:
            self.log = logger
            self.log.info(f"Will recycle logger object for {self.__class__.__name__}")
        else:
            self.log = LOGGER
            self.log.info("Logger created")

        # self.log = logger
        self.dimh = SCAN_GEOM[vendor]['dimh']
        self.dimv = SCAN_GEOM[vendor]['dimv']
        self.ccdax = SCAN_GEOM[vendor]['ccdax']
        self.ccday = SCAN_GEOM[vendor]['ccday']

        # values needed for WCS
        self.CDELT1 = xpixelscale
        self.CDELT2 = ypixelscale
        # if undefined, we assume reference position is in the center
        # of the sensor.
        if crpix1 is None:
            self.CRPIX1 = self.ccdax/2.
        if crpix2 is None:
            self.CRPIX2 = self.ccday/2.

        # Get DETSIZE
        self.get_DETSIZE()

    def load_vendor_defaults(self):
        self.overh = SCAN_GEOM[self.vendor]['overh']
        self.overv = SCAN_GEOM[self.vendor]['overv']
        self.preh = SCAN_GEOM[self.vendor]['dimh']

    def update_geom_params(self, geom):
        """Update the geom keys with new values in dictionaty geom"""
        for key, value in geom.items():
            self.log.debug(f"Updating {self.__class__.__name__} for {key} to: {value}")
            setattr(self, key, value)

    def get_DETSIZE(self):
        """ Common function to get DETSIZE"""
        self.DETSIZE = '[1:{:d},1:{:d}]'.format(8*self.dimh, 2*self.dimv)

    def get_DATASEC(self):
        """Common function to get DATASEC"""
        self.DATASEC = '[{:d}:{:d},1:{:d}]'.format(self.preh+1,
                                                   self.preh+self.dimh,
                                                   self.dimv)

    def setup_primary_sensor(self):
        """
        Set the initial metadata for the PRIMARY HDU per sensor
        """
        # DETSIZE also appears on segments, so we make it visible
        PRIMARY = {}
        PRIMARY['DETSIZE'] = self.DETSIZE
        return PRIMARY

    def setup_segment(self, Segment):
        """ Set initial informatpron for Segment (nn) """
        # Populate DETSIZE and EXTNAME
        SEGMENT = {}
        SEGMENT['DETSIZE'] = self.DETSIZE
        SEGMENT['EXTNAME'] = '{}{}'.format(self.segname, Segment)
        return SEGMENT

    def setup_primary_geom(self):

        """Update primary hdu"""
        # DETSIZE and DATASEC are the same for all segments
        PRIMARY = {}
        self.get_DETSIZE()
        self.get_DATASEC()
        PRIMARY['DETSIZE'] = self.DETSIZE
        return PRIMARY

    def setup_segment_geom(self, Segment):

        """Setup the geometry for a given segment"""
        Sx = int(Segment[0])
        Sy = int(Segment[1])

        # Get the mosaic/iraf wcs
        if self.vendor == 'ITL':
            EXTENSION_DATA = self.mosaic_ITL(Sx, Sy)
        elif self.vendor == 'E2V':
            EXTENSION_DATA = self.mosaic_E2V(Sx, Sy)
        else:
            raise ValueError('Vendor: {} not in list '.format(self.vendor))

        # Populate DETSIZE and DATASEC
        EXTENSION_DATA['DETSIZE'] = self.DETSIZE
        EXTENSION_DATA['DATASEC'] = self.DATASEC
        EXTENSION_DATA['EXTNAME'] = '{}{}'.format(self.segname, Segment)

        return EXTENSION_DATA

    def mosaic_E2V(self, Sx, Sy):

        """Setup the IRAF/Mosaic header section for E2V sensors"""

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

        """Setup the IRAF/Mosaic header section for ITL sensors"""

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

    def wcs_TAN(self, ra, dec, rot_angle, radesys):

        """
        Compute the common section of the WCS Tangential projection matrix
        See for a definition http://danmoser.github.io/notes/gai_fits-imgs.html
        """

        wcs = {'CTYPE1': 'RA---TAN',
               'CTYPE2': 'DEC--TAN',
               'CUNIT1': 'deg',
               'CUNIT2': 'deg',
               'CRVAL1': ra,
               'CRVAL2': dec,
               'CRPIX1': self.CRPIX1,
               'CRPIX2': self.CRPIX2,
               'CD1_1': self.CDELT1*math.cos(rot_angle),
               'CD1_2': -self.CDELT2*math.sin(rot_angle),
               'CD2_1': self.CDELT1*math.sin(rot_angle),
               'CD2_2': self.CDELT2*math.cos(rot_angle),
               'RADESYS': radesys,
               }
        return wcs
