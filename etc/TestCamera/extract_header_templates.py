#!/usr/bin/env python3

import fitsio
import sys

try:
    filename = sys.argv[1]
except IndexError:
    exit("ERROR: Please provide a filename")

# filename = 'ITL-3800C-145-Dev_fe55_bias_000_4698D_20170306174623.fits'
F = fitsio.FITS(filename)

for hdu in F:

    header = hdu.read_header()
    extnum = hdu.get_extnum()
    extname = hdu.get_extname()

    if extnum == 0:
        hfname = "primary_hdu.header"
    else:
        hfname = "%s.header" % extname

    print("Writing header from {} --> {}".format(extname, hfname))
    with open(hfname, "w") as o:
        o.write("%s" % header)
