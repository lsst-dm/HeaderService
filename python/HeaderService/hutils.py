""" Collection of simple functions to handle header mock library """

import os
import time
import fitsio
import numpy
import logging
import multiprocessing
import hashlib
import itertools
import copy
from .camera_coords import CCDGeom
spinner = itertools.cycle(['-', '/', '|', '\\'])

try:
    HEADERSERVICE_DIR = os.environ['HEADERSERVICE_DIR']
except KeyError:
    HEADERSERVICE_DIR = __file__.split('python')[0]

HDRLIST = ['camera', 'observatory', 'primary_hdu', 'telescope']


def create_logger(level=logging.NOTSET, name='default'):
    logging.basicConfig(level=level,
                        format='[%(asctime)s] [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(name)
    return logger


# Create a logger for all functions
LOGGER = create_logger(level=logging.NOTSET, name='HEADERSERVICE')


def get_record(header, keyword):
    """ Utility option to gets the record form a FITSHDR header"""
    index = header._index_map[keyword]
    return header._record_list[index]


def get_values(header):
    """ Returns a list with all of the values in a FITSHDR header """
    return [header[key] for key in header]


def elapsed_time(t1, verb=False):
    import time
    t2 = time.time()
    stime = "%dm %2.2fs" % (int((t2-t1)/60.), (t2-t1) - 60*int((t2-t1)/60.))
    if verb:
        print("Elapsed time: %s" % stime)
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
    import datetime
    """
    Get the obs-nite from a 'datetime.datetime.now()' kind of data object, but it will not
    work 'datetime.date.today()' has it has no hour
    """
    if date is None:
        date = datetime.datetime.now()
    # If hour < 14 we are still in the previous night date
    if date.hour < thresh_hour:
        date = date - datetime.timedelta(days=1)
    obsnite = format.format(year=date.year, month=date.month, day=date.day)
    return obsnite


def write_header_string(arg):
    """
    Simple method to write a header string to a filename that can be
    called by the multiprocess function. Therefore the filename and
    str_header are passed as a tuple
    """
    filename, str_header, md5 = arg
    with open(filename, 'w') as fobj:
        fobj.write(str_header)
    LOGGER.info("Wrote header to: %s" % filename)
    if md5:
        md5value = md5Checksum(filename)
        LOGGER.info("Got MD5SUM: %s" % md5value)
    return


def get_date_utc(time=None, format='isot'):
    from astropy.time import Time
    from datetime import datetime
    if time is None:
        time = (datetime.utcnow()).isoformat()
    t = Time(time, format=format, scale='utc')
    return t


def get_image_size_from_imageReadoutParameters(myData):

    ''' The stucture of the myData object for the imageReadoutParameters is:
     imageName    # string
     ccdNames     # string
     ccdType      # short
     overRows     # int
     overCols     # int
     readRows     # int
     readCols     # int
     readCols2    # int
     preCols      # int
     preRows      # int
     postCols     # int
     priority     # long
     '''

    geom = {
        'NAXIS1': myData.readCols + myData.readCols2 + myData.overCols + myData.preCols,
        'NAXIS2': myData.readRows + myData.overRows,
        'overv': myData.overRows,
        'overh': myData.overCols,
        'preh': myData.preCols,
        # 'dimh': myData.readCols  -- not in myData, in case we want to fudge it
        # 'dimv': myData.readRows  -- not in myData, in case we want to fudge it
        }
    geom['naxis1'] = geom['NAXIS1']
    geom['naxis2'] = geom['NAXIS2']
    return geom


def start_web_server(dirname, port_number=8000, exe='start_www.sh'):
    import subprocess
    LOGGER.info("Will start web server on dir: {}".format(dirname))
    subprocess.Popen([exe, dirname, str(port_number)])
    time.sleep(1)
    LOGGER.info("Done Starting web server")


class HDRTEMPL_TestCamera:

    def __init__(self, section='TestCamera', hdrlist=None, vendor='ITL', visitID_start=1):

        self.section = section
        self.vendor = vendor
        self.visitID_start = visitID_start
        self.visitID = "%08d" % self.visitID_start
        self.headerpath = os.path.join(HEADERSERVICE_DIR, 'etc', self.section, self.vendor)
        self.header_manifest = os.path.join(self.headerpath, 'manifest.txt')

        # Create logger
        self.logger = create_logger(level=logging.NOTSET, name='HEADERSERVICE')

        if hdrlist:
            self.hdrlist = hdrlist
        else:
            self.build_header_list()
        self.load_templates()

    def build_header_list(self):
        """ Build the hdrlist"""

        # Read in the full set of tiles
        if os.path.exists(self.header_manifest):
            LOGGER.info("Loading templates from: %s" % self.header_manifest)
            with open(self.header_manifest) as f:
                self.hdrlist = f.read().splitlines()
        else:
            exit("ERROR:No manifest file defined")

        # Keep an upper case copy
        self.HDRLIST = [x.upper() for x in self.hdrlist]
        return

    def load_templates(self):
        """ Load in all of the header templates """

        LOGGER.info("Loading templates from vendor: %s" % self.vendor)
        self.header = {}
        for hdrname in self.hdrlist:
            # Let's keep HDU-like section as upper cases
            HDRNAME = hdrname.upper()
            hdrfile = os.path.join(HEADERSERVICE_DIR, 'etc', self.section, self.vendor, "%s.header" % hdrname)
            LOGGER.info("Loading template for: %s" % HDRNAME)
            self.header[HDRNAME] = fitsio.read_scamp_head(hdrfile)

    def get_record(self, keyword, extname):
        return get_record(self.header[extname], keyword)

    def get_header_values(self):
        return get_values(self.header)

    def update_record(self, keyword, value, extname):
        """ Update record for key with value """
        rec = self.get_record(keyword, extname)
        rec['value'] = value
        rec['card_string'] = self.header[extname]._record2card(rec)

    def string_header(self, delimiter='END'):
        """ Format a header as a string """
        self.hstring = ''
        for extname in self.HDRLIST:
            self.hstring = self.hstring + str(self.header[extname]) + '\n' + delimiter
        return self.hstring

    def write_headers(self, filenames, MP=False, NP=2, md5=False):

        """
        Write one header per CCD (all the same) for now in order to test I/O performance
        """
        if MP:
            pool = multiprocessing.Pool(processes=NP)
            args = [(filename, self.hstring, md5) for filename in filenames]
            pool.map(write_header_string, args)
            pool.close()
            pool.join()
        else:
            for filename in filenames:
                arg = filename, self.hstring, md5
                write_header_string(arg)
        return

    def write_header_emptyHDU(self, filename):

        data = None
        with fitsio.FITS(filename, 'rw', clobber=True) as fits:
            for extname in self.HDRLIST:
                hdr = copy.deepcopy(self.header[extname])
                fits.write(data, ignore_empty=True)
                hdr.clean()
                # Keep NAXIS1/NAXIS2 intact if present in the template header
                if self.header[extname].get('NAXIS1') and self.header[extname].get('NAXIS2'):
                    hdr.add_record(get_record(self.header[extname], 'NAXIS1'))
                    hdr.add_record(get_record(self.header[extname], 'NAXIS2'))
                fits[-1].write_keys(hdr, clean=False)

    def write_header(self, filename, delimiter='END', newline=False):

        """
        Writes the single header file using the strict FITS notation (newline=False)
        or the more human readable (newline=True) with a delimiter for multiple HDU's
        """
        if newline:
            # Update header to a single string
            self.string_header(delimiter=delimiter)
            with open(filename, 'w') as fobj:
                fobj.write(self.hstring)
        else:
            self.write_header_emptyHDU(filename)
        return


class HDRTEMPL_ATSCam:

    def __init__(self,
                 section='ATSCam',
                 vendor='E2V',
                 segname='Segment',
                 templ_path=None,
                 templ_primary_name='primary_hdu.header',
                 templ_segment_name='segment_hdu.header'):

        self.section = section
        self.vendor = vendor
        self.segname = segname
        self.templ_path = templ_path
        self.templ_primary_name = templ_primary_name
        self.templ_segment_name = templ_segment_name

        # Create logger
        self.logger = create_logger(level=logging.NOTSET, name='HEADERSERVICE_ATSCam')

        # Init the class with geometry for a vendor
        self.CCDGEOM = CCDGeom(self.vendor, segname=self.segname)

        # Build the segments names
        self.build_segment_list()

        # Build the HDRLIST (PRIMARY,Segment01,...,Segment17)
        self.build_hdrlist()

        # Set template file names
        self.set_template_filenames()
        # Load them up
        # self.load_templates()

    def set_template_filenames(self):
        """Set the filenames of the primary and segment header templates"""
        # The path for the templates
        if not self.templ_path:
            self.templ_path = os.path.join(HEADERSERVICE_DIR, 'etc', self.section)
        self.templ_primary_file = os.path.join(self.templ_path, self.templ_primary_name)
        self.templ_segment_file = os.path.join(self.templ_path, self.templ_segment_name)

    def build_segment_list(self, n=16):
        """ Function to create the names and keys for Segments"""
        self.segment_names = []
        for k in range(n):
            channel = k+1
            segment_name = self.CCDGEOM.SEGNAME[channel]
            self.segment_names.append(segment_name)

    def build_hdrlist(self):
        self.HDRLIST = ['PRIMARY']
        for SEG in self.segment_names:
            EXTNAME = '{}{}'.format(self.segname, format(SEG))
            self.HDRLIST.append(EXTNAME)

    def load_templates(self):

        self.header = {}
        # Read in the primary and segment templates with fitsio
        self.header_segment = fitsio.read_scamp_head(self.templ_segment_file)
        self.header_primary = fitsio.read_scamp_head(self.templ_primary_file)

        # Load up the template for the PRIMARY header
        LOGGER.info("Loading template for: {}".format('PRIMARY'))
        self.header['PRIMARY'] = self.header_primary

        # Update PRIMARY with new value in self.CCDGEOM
        LOGGER.info("Updating GEOM in template for: {}".format('PRIMARY'))
        PRIMARY_DATA = self.CCDGEOM.get_extension('PRIMARY')
        self.update_records(PRIMARY_DATA, 'PRIMARY')

        # For the Segments, we load it once and then copy and modify each segment
        for SEG in self.segment_names:
            EXTNAME = '{}{}'.format(self.segname, format(SEG))
            LOGGER.info("Loading template for: {}".format(EXTNAME))
            self.header[EXTNAME] = copy.deepcopy(self.header_segment)
            # Now get the new value for the SEGMENT
            LOGGER.info("Updating GEOM in template for: {}".format(SEG))
            EXTENSION_DATA = self.CCDGEOM.get_extension(SEG)
            self.update_records(EXTENSION_DATA, EXTNAME)

    def get_record(self, keyword, extname):
        return get_record(self.header[extname], keyword)

    def get_header_values(self):
        return get_values(self.header)

    def update_record(self, keyword, value, extname):
        """ Update record for key with value """
        rec = self.get_record(keyword, extname)
        rec['value'] = value
        rec['card_string'] = self.header[extname]._record2card(rec)

    def update_records(self, newdict, extname):
        """
        Update all records in a new dictionary, it calls self.update_record()
        """
        for keyword, value in newdict.items():
            try:
                self.update_record(keyword, value, extname)
                LOGGER.debug("Updating {}".format(keyword))
            except Exception:
                LOGGER.debug("WARNING: Could not update {}".format(keyword))

    def string_header(self, delimiter='END'):
        """ Format a header as a string """
        self.hstring = ''
        for extname in self.HDRLIST:
            self.hstring = self.hstring + str(self.header[extname]) + '\n' + delimiter
        return self.hstring

    def write_headers(self, filenames, MP=False, NP=2, md5=False):

        """
        Write one header per CCD (all the same) for now in order to test I/O performance
        """
        if MP:
            pool = multiprocessing.Pool(processes=NP)
            args = [(filename, self.hstring, md5) for filename in filenames]
            pool.map(write_header_string, args)
            pool.close()
            pool.join()
        else:
            for filename in filenames:
                arg = filename, self.hstring, md5
                write_header_string(arg)
        return

    def write_header_emptyHDU(self, filename):

        data = None
        with fitsio.FITS(filename, 'rw', clobber=True) as fits:
            for extname in self.HDRLIST:
                hdr = copy.deepcopy(self.header[extname])
                fits.write(data, extname=extname, ignore_empty=True)
                hdr.clean()
                # # We do not need this -- as NAXIS1/2 should be done by the
                # # entity in charge of building the FITS file
                # # Keep NAXIS1/NAXIS2 intact if present in the template header
                # #if self.header[extname].get('NAXIS1') and self.header[extname].get('NAXIS2'):
                # #    hdr.add_record(get_record(self.header[extname],'NAXIS1'))
                # #    hdr.add_record(get_record(self.header[extname],'NAXIS2'))
                # #    #print get_record(self.header[extname],'NAXIS')
                fits[-1].write_keys(hdr, clean=False)

    def write_fits(self, filename, dtype='random', naxis1=None, naxis2=None, btype='int32'):

        """ Write a dummy fits file -- use for testing only"""

        # Figure out the dimensions following the camera geometry
        if not naxis1:
            naxis1 = self.CCDGEOM.dimh + self.CCDGEOM.overh + self.CCDGEOM.preh
        if not naxis2:
            naxis2 = self.CCDGEOM.dimv + self.CCDGEOM.overv

        t0 = time.time()
        with fitsio.FITS(filename, 'rw', clobber=True) as fits:

            # Write the PRIMARY First, with no data
            data = None
            hdr = copy.deepcopy(self.header['PRIMARY'])
            fits.write(data, extname='PRIMARY', ignore_empty=True)
            hdr.clean()
            fits[-1].write_keys(hdr, clean=False)

            # Loop over the extensions
            for extname in self.HDRLIST[1:]:
                if dtype == 'random':
                    data = numpy.random.uniform(1, 2**18-1, size=(naxis2, naxis1)).astype(btype)
                elif dtype == 'zero' or dtype == 'zeros':
                    data = numpy.zeros((naxis2, naxis1)).astype(btype)
                elif dtype == 'seq' or dtype == 'sequence':
                    data = numpy.zeros((naxis2, naxis1)).astype(btype) + int(extname[-2:])
                else:
                    raise NameError("Data Type: '{}' not implemented".format(dtype))
                hdr = copy.deepcopy(self.header[extname])
                LOGGER.debug("Writing: {}".format(extname))
                fits.write(data, extname=extname, header=hdr)
        LOGGER.info("FITS write time:{}".format(elapsed_time(t0)))

    def write_header(self, filename, delimiter='END', newline=False):

        """
        Writes the single header file using the strict FITS notation (newline=False)
        or the more human readable (newline=True) with a delimiter for multiple HDU's
        """
        if newline:
            # Update header to a single string
            self.string_header(delimiter=delimiter)
            with open(filename, 'w') as fobj:
                fobj.write(self.hstring)
        else:
            t0 = time.time()
            self.write_header_emptyHDU(filename)
            LOGGER.info("Header write time:{}".format(elapsed_time(t0)))
        return
