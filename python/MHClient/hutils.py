""" Collection of simple functions to handle header mock library """

import os
import fitsio
import numpy
import random

HDRLIST = ['camera','observatory','primary_hdu','telescope']
try:
    MHCLIENT_DIR = os.environ['MHCLIENT_DIR']
except:
    MHCLIENT_DIR = __file__.split('python')

def get_record(header,keyword):
    """ Utility option to gets the record form a FITSHDR header"""
    index = header._index_map[keyword]
    return header._record_list[index]

class HDRTEMPL:

    def __init__(self, hrdlist=HDRLIST, visitID_start=1):
        self.hdrlist = hrdlist
        self.visitID_start = visitID_start
        self.visitID = "%08d" % self.visitID_start
        self.load_templates()

    def load_templates(self):
        """ Load in all of the header templates """
        self.header = fitsio.FITSHDR()
        for hdrname in self.hdrlist:
            hdrfile = os.path.join(MHCLIENT_DIR,'etc',"%s.header" % hdrname)
            self.header = fitsio.read_scamp_head(hdrfile,header=self.header)
                    
    def get_record(self,keyword):
        return get_record(self.header,keyword)
            
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
        

class RANWORDS:

    WORDFILE = os.path.join(MHCLIENT_DIR,'etc','words.txt')
    
    def __init__(self, wordfile=WORDFILE,nparray=True):
        self.wordfile = wordfile
        self.nparray = nparray
        self.load_words()
        
    def load_words(self):
        """ Load in the wordlist"""
        self.words = open(self.wordfile).read().splitlines()
        self.words_vals = [len(w) for w in self.words]
        self.nwords = len(self.words)

        # Make the arrays numpy array
        if self.nparray:
            self.words      = numpy.array(self.words)
            self.words_vaks = numpy.array(self.words_vals)

# TODO:
# Add method for generating poitings based on template
# We want to be able to change RA,DEC, FILTER, etc
