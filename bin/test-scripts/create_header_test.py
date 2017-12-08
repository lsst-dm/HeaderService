#!/usr/bin/env python

import fitsio
import numpy

hdrfile = '/Users/felipe/sal-home/HeaderService/etc/TestCamera/ITL/Segment00.header'
newfile = 'test.fits'
data = None

with fitsio.FITS(newfile,'rw',clobber=True) as fits:
    data=None
    fits.write(data,ignore_empty=True)
    hdr=fitsio.read_scamp_head(hdrfile)
    hdr.clean()
    hdr['NAXIS1'] = 1024
    hdr['NAXIS2'] = 1024
    fits[-1].write_keys(hdr, clean=False)


    #fits.write(data)
    fits.write(data,ignore_empty=True)
    hdr=fitsio.read_scamp_head(hdrfile)
    hdr.clean()
    hdr['NAXIS1'] = 1024
    hdr['NAXIS2'] = 1024
    fits[-1].write_keys(hdr, clean=False)

    #fits.write(data)
    fits.write(data,ignore_empty=True)
    hdr=fitsio.read_scamp_head(hdrfile)
    hdr.clean()
    hdr['NAXIS1'] = 1024
    hdr['NAXIS2'] = 1024
    fits[-1].write_keys(hdr, clean=False)

    #fits.write(data)
    fits.write(data,ignore_empty=True)
    hdr=fitsio.read_scamp_head(hdrfile)
    hdr.clean()
    hdr['NAXIS1'] = 1024
    hdr['NAXIS2'] = 1024
    fits[-1].write_keys(hdr, clean=False)



exit()


#data = numpy.zeros((3,5))
#data = numpy.zeros(1)

hdr=fitsio.read_scamp_head(hdrfile)
fits = fitsio.FITS(newfile,'rw')

#img2send=None
#nkeys=len(hdr)
#dims2send=None
#comptype=None
#tile_dims=None
#extname='1'
#extver=1
#
#fits.create_image_hdu(data,
#                      dims=(30,30),
#                      header=hdr,
#                      dtype='i8',
                      #dims=dims2send,
                      #comptype=comptype, 
                      #tile_dims=tile_dims,
                      #extname=extname,
#                      extver=0)
#fits.write(data,dims=(30,30), header=hdr,extver=0)
fits.write(data, header=hdr,extver=0)
fits.write(data, header=hdr,extver=1)
fits.write(data, header=hdr,extver=2)
fits.close()

