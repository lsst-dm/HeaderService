#!/usr/bin/env python3

"""
Simple test script to read in and manually write out the ordered contents
of the header of FITS file in yaml format.
"""

import fitsio

# Define header using an example created by the HeaderService
header_file = "AT_O_20190531_000001.header"
header_primary = fitsio.read_header(header_file, ext='PRIMARY')

header = header_primary
print("{}:".format(header["EXTNAME"]))

# Retrieve all records in the header
recs = header.records()
for rec in recs:
    name = rec['name']
    value = rec['value']
    comment = rec['comment']
    print(" {}:".format(rec['name']))
    if type(value) is str:
        print("  value: \"{}\"".format(rec['value']))
    else:
        print("  value: {}".format(rec['value']))
    print("  comment: \"{}\"".format(rec['comment']))


# Loop over each of segments
for k in range(16):

    header = fitsio.read_header(header_file, ext=k+1)
    print("")
    print("R01S01_{}:".format(header['EXTNAME']))

    # Get all records
    recs = header.records()
    for rec in recs:
        name = rec['name']
        value = rec['value']
        comment = rec['comment']
        print(" {}:".format(rec['name']))
        if type(value) is str:
            print("  value: \"{}\"".format(rec['value']))
        else:
            print("  value: {}".format(rec['value']))
        print("  comment: \"{}\"".format(rec['comment']))
