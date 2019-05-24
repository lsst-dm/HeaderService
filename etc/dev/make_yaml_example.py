#!/usr/bin/env python3

from HeaderService import hutils
import fitsio

header_file = "AT_O_20190515_000001.header"
header_primary = fitsio.read_header(header_file, ext='PRIMARY')

print ("PRIMARY:")

header_yaml = {}
header = header_primary
for keyword in header.keys():

    # ignoring these for now
    if keyword == 'COMMENT' or keyword == 'SIMPLE':
        continue

    # Get the full record
    rec = hutils.get_record(header, keyword)

    print (" {}:".format(rec['name']))
    if rec['dtype'] == 'C':
        print ("  value: '{}'".format(rec['value']))
    else:
        print ("  value: {}".format(rec['value']))
    print ("  type: {}".format(rec['dtype']))
    print ("  comment: {}".format(rec['comment']))
    print ("")

# Loop over each of segments
for k in range(16):

    header = fitsio.read_header(header_file, ext=k+1)
    print ("")
    print ("R01S01_{}:".format(header['EXTNAME']))
    print (" ".format(header['EXTNAME']))
    for keyword in header.keys():

        if keyword == 'COMMENT' or keyword == 'SIMPLE':
            continue

        # Get the full record
        rec = hutils.get_record(header, keyword)

        print (" {}:".format(rec['name']))
        if rec['dtype'] == 'C':
            print ("  value: '{}'".format(rec['value']))
        else:
            print ("  value: {}".format(rec['value']))
        print ("  type: {}".format(rec['dtype']))
        print ("  comment: {}".format(rec['comment']))
