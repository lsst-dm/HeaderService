""" Collection of simple functions to handle header mock library """

import os
import fitsio
import numpy
import random
import logging
import multiprocessing
import hashlib
import itertools
import copy
spinner = itertools.cycle(['-', '/', '|', '\\'])


# TODO:
# Merge/inherit HDRTEMPL_XXXX into a master/common class

try:
    HEADERSERVICE_DIR = os.environ['HEADERSERVICE_DIR']
except:
    HEADERSERVICE_DIR = __file__.split('python')[0]

WORDFILE = os.path.join(HEADERSERVICE_DIR,'etc','words.txt')
HDRLIST = ['camera','observatory','primary_hdu','telescope']

def create_logger(level=logging.NOTSET,name='default'):
    logging.basicConfig(level=level,
                        format='[%(asctime)s] [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(name)
    return logger

# Create a logger for all functions
LOGGER = create_logger(level=logging.NOTSET,name='HEADERSERVICE')

def get_record(header,keyword):
    """ Utility option to gets the record form a FITSHDR header"""
    index = header._index_map[keyword]
    return header._record_list[index]

def get_values(header):
    """ Returns a list with all of the values in a FITSHDR header """
    return [hearder[key] for key in header.keys()]

def elapsed_time(t1,verb=False):
    import time
    t2    = time.time()
    stime = "%dm %2.2fs" % ( int( (t2-t1)/60.), (t2-t1) - 60*int((t2-t1)/60.))
    if verb:
        print >>sys.stderr,"Elapsed time: %s" % stime
    return stime

def write_header_string(arg):
    """
    Simple method to write a header string to a filename that can be
    called by the multiprocess function. Therefore the filename and
    str_header are passed as a tuple
    """
    filename, str_header, md5 = arg
    with open(filename,'w') as fobj:
        fobj.write(str_header)
    LOGGER.info("Wrote header to: %s" % filename)
    if md5:
        md5value = md5Checksum(filename) #,blocksize=1024*512):
        LOGGER.info("Got MD5SUM: %s" % md5value)
    return

class HDRTEMPL_TestCamera:

    def __init__(self, section='TestCamera', hdrlist=None, vendor='ITL', visitID_start=1):

        self.section = section
        self.vendor  = vendor
        self.visitID_start = visitID_start
        self.visitID = "%08d" % self.visitID_start
        self.headerpath = os.path.join(HEADERSERVICE_DIR,'etc',self.section,self.vendor)
        self.header_manifest = os.path.join(self.headerpath,'manifest.txt')

        # Create logger
        self.logger = create_logger(level=logging.NOTSET,name='HEADERSERVICE')

        if hdrlist:
            self.hdrlist = hrdlist
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
            hdrfile = os.path.join(HEADERSERVICE_DIR,'etc',self.section,self.vendor,"%s.header" % hdrname)
            LOGGER.info("Loading template for: %s" % HDRNAME)
            self.header[HDRNAME] = fitsio.read_scamp_head(hdrfile)

    def get_record(self,keyword,extname):
        return get_record(self.header[extname],keyword)

    def get_header_values(self):
        return get_values(self.header[extname])

    def update_record(self,keyword,value,extname):
        """ Update record for key with value """
        rec = self.get_record(keyword,extname)
        rec['value'] = value
        rec['card_string'] = self.header[extname]._record2card(rec)


    def string_header(self,delimiter='END'):
        """ Format a header as a string """
        self.hstring = ''
        for extname in self.HDRLIST:
            self.hstring = self.hstring + str(self.header[extname]) + '\n' + delimiter
        return self.hstring 


    def write_headers(self,filenames, MP=False, NP=2, md5=False):

        """
        Write one header per CCD (all the same) for now in order to test I/O performance
        """
        if MP:
            pool = multiprocessing.Pool(processes=NP)
            args = [ (filename, self.hstring, md5) for filename in filenames]
            pool.map(write_header_string, args)
            pool.close()
            pool.join()
        else:
            for filename in filenames:
                arg = filename, self.hstring, md5
                write_header_string(arg)
        return

    def write_header_emptyHDU(self,filename):

        data=None
        with fitsio.FITS(filename,'rw',clobber=True) as fits:
            for extname in self.HDRLIST:

                hdr = copy.deepcopy(self.header[extname])
                fits.write(data,ignore_empty=True)
                hdr.clean()
                # Keep NAXIS1/NAXIS2 intact if present in the template header
                if self.header[extname].get('NAXIS1') and self.header[extname].get('NAXIS2'):
                    hdr.add_record(get_record(self.header[extname],'NAXIS1'))
                    hdr.add_record(get_record(self.header[extname],'NAXIS2'))
                    #print get_record(self.header[extname],'NAXIS')
                fits[-1].write_keys(hdr, clean=False)

    def write_header(self,filename,delimiter='END',newline=False):
        
        """
        Writes the single header file using the strict FITS notation (newline=False)
        or the more human readable (newline=True) with a delimiter for multiple HDU's
        """
        if newline:
            # Update header to a single string
            selt.string_header(delimiter=delimiter)
            with open(filename,'w') as fobj:
                fobj.write(self.hstring)
        else:
            self.write_header_emptyHDU(filename)
        return

class HDRTEMPL_SciCamera:

    # TODO: We might want to add the ability to separate the header by type

    def __init__(self, hrdlist=HDRLIST, visitID_start=1):
        self.hdrlist = hrdlist
        self.visitID_start = visitID_start
        self.visitID = "%08d" % self.visitID_start
        # Create logger
        self.logger = create_logger(level=logging.NOTSET,name='HEADERSERVICE')
        self.load_templates()
        self.header_as_arrays()

    def load_templates(self):
        """ Load in all of the header templates """
        self.header = fitsio.FITSHDR()
        for hdrname in self.hdrlist:
            hdrfile = os.path.join(HEADERSERVICE_DIR,'etc','SciCamera',"%s.header" % hdrname)
            # We read and append at the same time, but we might want
            # to de-couple these two actions, if we want to keept the
            # sections separated so they can be streamed independently
            self.header = fitsio.read_scamp_head(hdrfile,header=self.header)
                    
    def get_record(self,keyword):
        return get_record(self.header,keyword)

    def get_header_values(self):
        return get_values(self.header)

    def update_record(self,keyword,value):
        """ Update record for key with value """
        rec = self.get_record(keyword)
        rec['value'] = value
        rec['card_string'] = self.header._record2card(rec)
        #self.header.write_keys([rec])
        #self.header.add_record(rec)
        
            
    def next_visit(self,filter='r'):
        """ Rev up the visitID counter """
        self.filter = filter
        self.visitID = "%08d" % (int(self.visitID) + 1)
        self.header['VISITID'] = self.visitID
        self.next_pointing()

    def next_pointing(self,RA=None,DEC=None):
        """ Generate a random RA,DEC pointing """
        if not RA and not DEC:
            self.RA  = random.uniform(0, 360)
            self.DEC = random.uniform(10, -70)
        elif RA and DEC:
            self.RA  = RA
            self.DEC = DEC
        else:
            exit("Both RA/DEC need to be defined or undefine")

        self.header['RA']  = self.RA
        self.header['DEC'] = self.DEC

    def header_as_arrays(self):
        """ Make numpy array representations of the header keys and values """
        
        head_keys = self.header.keys()
        head_vals = [self.header[key] for key in self.header.keys()]

        # Make numpy arrays of the heads
        self.header_keys = numpy.array(head_keys)
        self.header_vals = numpy.array(head_vals)

    def write_header(self,filename,newline=False, md5=False):

        """
        Write the header using the strict FITS notation (newline=False)
        or more human readable (newline=True)
        """

        if newline:
            with open(filename,'w') as fobj:
                hstring = str(self.header)
                fobj.write(hstring)
        else:
            data=None
            fitsio.write(filename, data, header=self.header)
        return

class RANWORDS():

    """ Class to generate random words from a dictionary """
    
    def __init__(self, wordfile=WORDFILE,nparray=True): 

        self.wordfile = wordfile
        self.nparray = nparray
        self.load_words()
        self.get_words()

        
    def load_words(self):
        """ Load in the wordlist"""
        self.all_words_keys = open(self.wordfile).read().splitlines()
        self.all_words_vals = [len(w) for w in self.all_words_keys]
        self.nwords = len(self.all_words_keys)

        # Make the arrays numpy array
        if self.nparray:
            self.all_words_keys = numpy.array(self.all_words_keys)
            self.all_words_vals = numpy.array(self.all_words_vals)

    def get_words(self,N=1000):
        idx = numpy.random.choice(self.nwords,N,replace=False)
        idx.sort()
        self.words_keys = self.all_words_keys[idx]
        self.words_vals = self.all_words_vals[idx]


class TELEMSIM(HDRTEMPL_SciCamera):

    """ A class to generate and send telemetry for the header client"""
    
    def __init__(self, wordfile=WORDFILE,nparray=True,hrdlist=HDRLIST, visitID_start=1):
        
        HDRTEMPL.__init__(self, hrdlist=HDRLIST, visitID_start=1)

    def get_stream(self):

        """ We merge the set of random words we selected with the current header"""
        # Update header as array
        self.header_as_arrays()

class HOSER(HDRTEMPL_SciCamera,RANWORDS):

    """ A class to send a telemetry stream """

    SEND_EXE    = 'Telemetry_send'
    RECEIVE_EXE = 'Telemetry_receive'

    """
    TODO:
     - send the using SEND_EXE
     - Resolve if want to send telescope/camera/ccd separatelty
    """

    def __init__(self, wordfile=WORDFILE,nparray=True,hrdlist=HDRLIST, visitID_start=1):

        HDRTEMPL.__init__(self, hrdlist=HDRLIST, visitID_start=1)
        RANWORDS.__init__(self, wordfile=WORDFILE,nparray=True)

    def get_stream(self,shuffle=True):
        """ We merge the set of random words we selected with the current header"""

        # Update header as array
        self.header_as_arrays()
        
        # Make the streams as numpy arrays
        self.stream_keys = numpy.concatenate((self.header_keys, self.words_keys))
        self.stream_vals = numpy.concatenate((self.header_vals, self.words_vals))
        self.stream_size = len(self.stream_keys)

        if shuffle:
            idx = numpy.arange(self.stream_size)
            numpy.random.shuffle(idx)
            self.stream = dict(zip(self.stream_keys[idx].tolist(), self.stream_vals[idx].tolist()))
        else:
            self.stream = dict(zip(self.stream_keys.tolist(), self.stream_vals.tolist()))

        return self.stream


def md5Checksum(filePath,blocksize=1024*512):
    with open(filePath, 'rb') as fh:
        m = hashlib.md5()
        while True:
            data = fh.read(blocksize)
            if not data:
                break
            m.update(data)
    return m.hexdigest()
