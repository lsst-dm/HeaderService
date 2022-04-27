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

""" Collection of simple functions to handle header mock library """

import os
import sys
import time
import fitsio
import yaml
import numpy
import logging
from logging.handlers import RotatingFileHandler
import hashlib
import itertools
import copy
from .camera_coords import CCDInfo
from . import camera_coords
import datetime
import re
# import HeaderService.camera_coords as camera_coords

spinner = itertools.cycle(['-', '/', '|', '\\'])

try:
    HEADERSERVICE_DIR = os.environ['HEADERSERVICE_DIR']
except KeyError:
    HEADERSERVICE_DIR = __file__.split('python')[0]


def configure_logger(logger, logfile=None, level=logging.NOTSET, log_format=None, log_format_date=None):
    """
    Configure an existing logger
    """
    # Define formats
    if log_format:
        FORMAT = log_format
    else:
        FORMAT = '[%(asctime)s.%(msecs)03d][%(levelname)s][%(name)s][%(funcName)s] %(message)s'
    if log_format_date:
        FORMAT_DATE = log_format_date
    else:
        FORMAT_DATE = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(FORMAT, FORMAT_DATE)

    # Need to set the root logging level as setting the level for each of the
    # handlers won't be recognized unless the root level is set at the desired
    # appropriate logging level. For example, if we set the root logger to
    # INFO, and all handlers to DEBUG, we won't receive DEBUG messages on
    # handlers.
    logger.setLevel(level)

    handlers = []
    # Set the logfile handle if required
    if logfile:
        fh = RotatingFileHandler(logfile, maxBytes=2000000, backupCount=10)
        fh.setFormatter(formatter)
        fh.setLevel(level)
        handlers.append(fh)
        logger.addHandler(fh)

    # Set the screen handle
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    sh.setLevel(level)
    handlers.append(sh)
    logger.addHandler(sh)
    return


def create_logger(logfile=None, level=logging.NOTSET, log_format=None, log_format_date=None):
    """
    Simple logger that uses configure_logger()
    """
    logger = logging.getLogger(__name__)
    configure_logger(logger, logfile=logfile, level=level,
                     log_format=log_format, log_format_date=log_format_date)
    logging.basicConfig(handlers=logger.handlers, level=level)
    return logger


def read_head_template(fname, header=None):
    """
    Function to read in the templates used for the HeaderService.
    This function is based on fitsio.read_scamp_head() and has been
    modified to treat comments (when the KEYWORD field is blank) according
    to the definition of Pence et al. 2010 (section 4.4.2.4)

    read a template header file as a fits header FITSHDR object
    parameters
    ----------
    fname: string
        The path to the header file
    header: FITSHDR, optional
        Optionally combine the header with the input one. The input can
        be any object convertable to a FITSHDR object
    returns
    -------
    header: FITSHDR
        A fits header object of type FITSHDR
    """
    with open(fname) as fobj:
        lines = fobj.readlines()

    lines = [line.rstrip() for line in lines if line[0:3] != 'END']

    # if header is None an empty FITSHDR is created
    hdr = fitsio.FITSHDR(header)

    for line in lines:
        hdr.add_record(line)

    # Nedd to fix the keyword for HIERARCH, as fitsio removes the
    # HIERARCH string from the keyword. Here we put it back
    index_map = copy.deepcopy(hdr._index_map)
    for keyword in index_map:
        rec = get_record(hdr, keyword)
        try:
            is_hierarch = check_hierarch(rec)
        except Exception:
            is_hierarch = False
        if is_hierarch:
            name_old = rec['name']
            name_new = f"HIERARCH {rec['name']}"
            rec['name'] = name_new
            hdr._index_map[name_new] = hdr._index_map.pop(name_old)

    return hdr


def check_hierarch(record):
    """Check if record is HIERARCH"""
    card_string = record['card_string']
    return card_string[0:8].upper() == 'HIERARCH'


def get_record(header, keyword):
    """ Utility option to gets the record form a FITSHDR header"""
    index = header._index_map[keyword]
    return header._record_list[index]


def get_values(header):
    """ Returns a list with all of the values in a FITSHDR header """
    return [header[key] for key in header]


def elapsed_time(t1, verb=False):
    """
    Returns the time between t1 and the current time now
    I can can also print the formatted elapsed time.
    ----------
    t1: float
        The initial time (in seconds)
    verb: bool, optional
        Optionally print the formatted elapsed time
    returns
    -------
    stime: float
        The elapsed time in seconds since t1

    """
    t2 = time.time()
    stime = "%dm %2.2fs" % (int((t2-t1)/60.), (t2-t1) - 60*int((t2-t1)/60.))
    if verb:
        print("Elapsed time: {}".format(stime))
    return stime


def md5Checksum(filePath, blocksize=1024*512):
    with open(filePath, 'rb') as fh:
        m = hashlib.md5()
        while True:
            data = fh.read(blocksize)
            if not data:
                break
            m.update(data)
    return m.hexdigest()


def get_obsnite(date=None, thresh_hour=14, format='{year}{month:02d}{day:02d}'):
    """
    Get the obs-nite from a 'datetime.datetime.now()' kind of data object, but
    it will not work 'datetime.date.today()' has it has no hour
    """
    if date is None:
        date = datetime.datetime.now()
    # If hour < 14 we are still in the previous night date
    if date.hour < thresh_hour:
        date = date - datetime.timedelta(days=1)
    obsnite = format.format(year=date.year, month=date.month, day=date.day)
    return obsnite


def repack_dict_list(mydict, masterkey):
    # Repack dictionary with list, keys to a give key
    newdict = dict()
    for newkey in mydict[masterkey]:
        newdict[newkey] = dict()
        indx = mydict[masterkey].index(newkey)
        for key in mydict.keys():
            newdict[newkey][key] = mydict[key][indx]
    return newdict


def split_esc(s, sep=':', esc='\\'):

    '''
    Split a string using separator (sep) and escape (esc) character
    '''

    # We want to replicate the spliting of string:
    #
    # s = "OBJECT:2020-06-16T18\:43\:55.039:OBJECT"
    # print([re.sub(r'\\(.)','\\1',k) for k in re.split(r'(?<!\\):', s)])
    # ['OBJECT', '2020-06-16T18:43:55.039', 'OBJECT']
    #
    # and:
    #
    # s = 'OBJECT:2020-06-16T18\\:43\\:55.039:OBJ\\\\ECT'
    # print([re.sub(r'\\(.)','\\1',k) for k in re.split(r'(?<!\\):', s)])
    # ['OBJECT', '2020-06-16T18:43:55.039', 'OBJ\\ECT']

    # The regular expresions we'll use
    r1 = r"(?<!\{esc}){sep}".format(esc=esc, sep=sep)
    r2 = r'\{esc}(.)'.format(esc=esc)
    r3 = '{esc}1'.format(esc=esc)
    arr = [re.sub(r2, r3, k) for k in re.split(r1, s)]

    return arr


def get_image_size_from_imageReadoutParameters(myData, array_key='ccdLocation', sep=":"):

    ''' The stucture of the myData object for the imageReadoutParameters is:
     imageName    # string
     ccdLocation     # string
     ccdType      # short
     overRows     # int
     overCols     # int
     readRows     # int
     readCols     # int
     readCols2    # int
     preCols      # int
     preRows      # int
     postCols     # int
     '''

    geom = {
        'dimh': myData.readCols,
        'dimv': myData.readRows,
        'NAXIS1': myData.readCols + myData.readCols2 + myData.overCols + myData.preCols,
        'NAXIS2': myData.readRows + myData.overRows,
        'overv': myData.overRows,
        'overh': myData.overCols,
        'preh': myData.preCols}

    geom['naxis1'] = geom['NAXIS1']
    geom['naxis2'] = geom['NAXIS2']
    # Split and store array keys
    payload = getattr(myData, array_key)
    geom[array_key] = payload.split(sep)
    # ONLY REPACK as as dictionary keyed to sensors,
    # if more than one sensor is present in the ccdLocation payload.
    # This is the case for ComCam and LSSTCam
    if len(geom[array_key]) > 1:
        geom_sensor = repack_dict_list(geom, array_key)
    # If just one element (i.e. LATIIS), return a dictionary
    # with one key/sensor
    else:
        geom_sensor = {geom[array_key][0]: geom}
    return geom_sensor


def build_sensor_list(instrument, sep=""):
    """
    For testing in the absense of a message from camera
    utility function to create the names and keys for sensors.
    It takes an optional 'sep' depending on how Camera sends the
    information for the telemetry.
    """
    raft_names = camera_coords.RAFTS[instrument]
    sensor_names = []
    if instrument == 'LATISS':
        raft = raft_names[0]
        i = 0
        j = 0
        sensor_names = [f"R{raft}{sep}SW{j}"]
        return sensor_names

    if instrument == 'GenericCamera':
        sensor_names = ['dummy']
        return sensor_names

    for raft in raft_names:
        for i in range(3):
            for j in range(3):
                sensor_name = f"R{raft}{sep}S{i}{j}"
                sensor_names.append(sensor_name)
    return sensor_names


# Generic class for LATISS/ComCam/LSSTCam
class HDRTEMPL:

    def __init__(self,
                 sensor_names,
                 vendor_names,
                 logger=None,
                 section=None,
                 instrument=None,
                 segname='Segment',
                 write_mode='yaml',
                 templ_path=None,
                 templ_primary_name='primary_hdu.header',
                 templ_primary_sensor_name='primary_sensor_hdu.header',
                 templ_segment_name='segment_hdu.header'):

        self.sensor_names = sensor_names
        self.vendor_names = vendor_names
        self.section = section
        self.instrument = instrument
        self.templ_path = templ_path
        self.templ_primary_name = templ_primary_name
        self.templ_primary_sensor_name = templ_primary_sensor_name
        self.templ_segment_name = templ_segment_name
        self.write_mode = write_mode
        self.segname = segname

        # Figure out logging
        if logger:
            self.log = logger
            self.log.info("Will recycle logger object")
        else:
            self.log = create_logger()
            self.log.info("Logger created")

        # Set template file names
        self.set_template_filenames()

        # The number of segments
        if self.instrument == 'GenericCamera':
            nsegments = 1
        else:
            nsegments = 16
        # Build the HDRLIST (PRIMARY, PRIMARY_COMMON, Segment01,...,Segment17)
        self.build_hdrlist(n=nsegments)

        # Load/Create CCDGEOM object per sensor
        self.load_CCDInfo()

        # Set the mimeType
        self.set_mimeType()

    def set_template_filenames(self):
        """Set the filenames of the primary and segment header templates"""
        # The path for the templates
        if not self.templ_path:
            self.templ_path = os.path.join(HEADERSERVICE_DIR, 'etc', self.section)

        # Templates present in LATIIS and ComCam/LSSTCam
        self.templ_file = {}
        self.templ_file['PRIMARY'] = os.path.join(self.templ_path, self.templ_primary_name)
        self.templ_file['SEGMENT'] = os.path.join(self.templ_path, self.templ_segment_name)
        # Sensor is optional
        sensor_file = os.path.join(self.templ_path, self.templ_primary_sensor_name)
        if os.path.exists(sensor_file):
            self.templ_file['SENSOR'] = sensor_file
        else:
            self.log.warning(f"No SENSOR template for {self.instrument}")

    def build_hdrlist(self, n=16):
        """
        Function to build the list of HDUs into the headers. For LATISS each of
        the Segments is simply called SegmentNN, while for ComCam and LSSTCam
        these have the preffix of the sensor name (i.e.: R22S02_Segment01)
        """

        self.log.info(f"Building HDRlist for {self.instrument}")
        self.HDRLIST = ['PRIMARY']
        # Loop over list of sensors
        # Here we need to add the PRIMARY_SENSOR_NAME
        self.segment_names = {}
        # Put the vendor names in a dictionary keyed to sensor names
        self.vendor = {}
        for sensor, vendor in zip(self.sensor_names, self.vendor_names):
            self.segment_names[sensor] = []
            self.vendor[sensor] = vendor
            if 'SENSOR' in self.templ_file:
                self.HDRLIST.append(f"{sensor}_PRIMARY")
            for hdu in range(1, n+1):
                segment_name = camera_coords.SEGNAME[self.instrument][hdu]
                self.segment_names[sensor].append(segment_name)
                extname = self.get_segment_extname(sensor, segment_name)
                self.HDRLIST.append(extname)

        self.log.debug("Build HDRLIST:")
        self.log.debug('\n\t'.join(self.HDRLIST))

    def load_CCDInfo(self):
        """ Load the CCDGEOM object for each sensor"""
        self.CCDInfo = {}
        for sensor in self.sensor_names:
            self.CCDInfo[sensor] = CCDInfo(self.vendor[sensor],
                                           segname=self.segname,
                                           logger=self.log)

    def get_primary_extname(self, sensor):
        """Get the PRIMARY extension name used for a sensor/CCD"""
        extname = f"{sensor}_PRIMARY"
        return extname

    def get_segment_extname(self, sensor, seg):
        """Get the right SEGMENT extension name used for a sensor/CCD"""
        # Account for different formating for EXTNAME for LATISS
        if self.instrument == 'GenericCamera':
            extname = f"{self.segname}{seg}"
        else:
            extname = f"{sensor}_{self.segname}{seg}"
        return extname

    def load_templates(self):

        # Read in the primary and segment templates with fitsio
        self.header_primary = read_head_template(self.templ_file['PRIMARY'])
        self.header_segment = read_head_template(self.templ_file['SEGMENT'])
        # Sensor is optional
        if 'SENSOR' in self.templ_file:
            self.header_primary_sensor = read_head_template(self.templ_file['SENSOR'])

        # Start loadin templates into the self.header object
        # 1. Load up the template for the PRIMARY header
        # The main structure that will host the header object
        self.header = {}
        self.header['PRIMARY'] = self.header_primary
        PRIMARY_DATA = camera_coords.setup_primary()
        self.update_records(PRIMARY_DATA, 'PRIMARY')
        self.log.info("Loading template for: PRIMARY")

        # 2. Load up segments (and PRIMARY_SENSOR if needed)
        for sensor in self.sensor_names:

            if 'SENSOR' in self.templ_file:
                # Get the extname for the primary/sensor combo
                extname = self.get_primary_extname(sensor)
                self.header[extname] = copy.deepcopy(self.header_primary_sensor)
                PRIMARY_DATA_SENSOR = self.CCDInfo[sensor].setup_primary_sensor()
                self.log.info(f"Loading template for: {extname}")
                self.update_records(PRIMARY_DATA_SENSOR, extname)

            # Loop over all segment in Sensor/CCD
            for seg in self.segment_names[sensor]:
                # Get the right extnamme for sensor/segment combination
                extname = self.get_segment_extname(sensor, seg)
                self.log.info(f"Loading template for: {extname}")
                self.header[extname] = copy.deepcopy(self.header_segment)
                # Now get the new values for the SEGMENT
                self.log.debug(f"Updating DATA in template for: {extname}")
                SEGMENT_DATA = self.CCDInfo[sensor].setup_segment(seg)
                self.update_records(SEGMENT_DATA, extname)

    def load_geometry(self, geom):
        """
        Function to update geometry information once the parameters are known
        because they were received from a camera event. This is a lighter task
        than uploading the header templates again
        """

        self.log.info("Loading geometry for header")
        # Load up the template for the PRIMARY header
        for sensor in self.sensor_names:
            # Get the extname for the primary/sensor combo
            extname = self.get_primary_extname(sensor)
            # Get the updated primary data
            self.CCDInfo[sensor].update_geom_params(geom[sensor])
            PRIMARY_DATA = self.CCDInfo[sensor].setup_primary_geom()
            # Load up the new PRIMARY_DATA, here we either update PRIMARY
            # or PRIMARY_SENSOR which is defined by {extname}
            self.log.info(f"Updating records for: {extname}")
            self.update_records(PRIMARY_DATA, extname)
            # Loop over all segment in Sensor/CCD
            for seg in self.segment_names[sensor]:
                # Get the right extnamme for sensor/segment combination
                extname = self.get_segment_extname(sensor, seg)
                self.log.debug(f"Updating geom for: {extname}")
                SEGMENT_DATA = self.CCDInfo[sensor].setup_segment_geom(seg)
                self.update_records(SEGMENT_DATA, extname)

    def get_record(self, keyword, extname):
        return get_record(self.header[extname], keyword)

    def get_header_values(self):
        return get_values(self.header)

    def update_record(self, keyword, value, extname):
        """ Update record for key with value """
        # Only update if keyword is already in the template
        # otherwise ignore
        if keyword not in self.header[extname]._index_map:
            self.log.info(f"Ignoring {keyword} not in {extname} template")
        else:
            self.log.debug(f"Updating {keyword} for {extname}")
            rec = self.get_record(keyword, extname)
            rec['value'] = value
            rec['card_string'] = self.header[extname]._record2card(rec)

    def update_records(self, newdict, extname):
        """
        Update all records in a new dictionary, it calls self.update_record()
        """
        for keyword, value in newdict.items():
            self.update_record(keyword, value, extname)

    def write_header_yaml(self, filename):
        """Write a header file in yaml format"""

        # The dict where we will store the header contents
        yaml_header = {}
        # Loop over all of the image extensions to build
        # the dictionary that will hold the metadata
        for extname in self.HDRLIST:
            # Set the empty list per extname
            yaml_header[extname] = []
            # Get all records for EXTNAME
            recs = self.header[extname].records()
            for rec in recs:
                # Avoid undef comments and set them as empty strings
                if 'comment' not in rec:
                    rec['comment'] = ''
                new_rec = {'keyword': rec['name'],
                           'value': rec['value'],
                           'comment': rec['comment']}
                yaml_header[extname].append(new_rec)

        # Write out directly using yaml
        with open(filename, 'w') as outfile:
            yaml.dump(yaml_header, outfile, default_flow_style=False, sort_keys=False)

    def write_header_fits(self, filename):
        """Write a header file using the FITS format with empty HDUs"""
        data = None
        with fitsio.FITS(filename, 'rw', clobber=True, ignore_empty=True) as fits:
            for extname in self.HDRLIST:
                hdr = copy.deepcopy(self.header[extname])
                fits.write(data, header=hdr, extname=extname)

    def write_dummy_fits(self, filename, dtype='random', naxis1=None, naxis2=None, btype='int32'):

        """
        Write a dummy fits file filled with random or zeros
        -- use for testing only
        """

        t0 = time.time()
        with fitsio.FITS(filename, 'rw', clobber=True, ignore_empty=True) as fits:

            # Write the PRIMARY First, with no data
            data = None
            hdr = copy.deepcopy(self.header['PRIMARY'])
            fits.write(data, header=hdr, extname='PRIMARY')

            # Loop over the extensions
            for extname in self.HDRLIST[1:]:
                if dtype == 'random':
                    data = numpy.random.uniform(1, 2**18-1, size=(naxis2, naxis1)).astype(btype)
                elif dtype == 'zero' or dtype == 'zeros':
                    data = numpy.zeros((naxis2, naxis1)).astype(btype)
                elif dtype == 'seq' or dtype == 'sequence':
                    data = numpy.zeros((naxis2, naxis1)).astype(btype) + int(extname[-2:])
                else:
                    raise NameError(f"Data Type: '{dtype}' not implemented")
                hdr = copy.deepcopy(self.header[extname])
                self.log.debug(f"Writing: {extname}".format(extname))
                fits.write(data, extname=extname, header=hdr)
        self.log.info("FITS write time:{}".format(elapsed_time(t0)))

    def write_header(self, filename):
        """
        Writes single header file using the strict FITS format (i.e. empty
        HDUs, write_mode='fits') or YAML (write_mode='yaml')
        """
        t0 = time.time()
        if self.write_mode == 'fits':
            self.write_header_fits(filename)
        elif self.write_mode == 'yaml':
            self.write_header_yaml(filename)
        else:
            msg = "ERROR: header write_mode: {} not recognized".format(self.write_mode)
            self.log.error(msg)
            raise ValueError(msg)
            return

        self.log.info(f"Header write time: {elapsed_time(t0)}")
        return

    def set_mimeType(self):
        """
        Set the mime TYPE of the header based on the write mode
        """
        if self.write_mode == 'fits':
            self.mimeType = 'application/fits'
        elif self.write_mode == 'yaml':
            self.mimeType = 'text/yaml'
        else:
            msg = "ERROR: header write_mode: {} not recognized".format(self.write_mode)
            self.log.error(msg)
            raise ValueError(msg)
            return
        self.log.info(f"Set mime Type to: {self.mimeType}")
