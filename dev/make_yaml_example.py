#!/usr/bin/env python3

"""
Simple test script to read in and write out the ordered contents of the header
of FITS file in yaml format.
"""

import fitsio
import yaml

# Define header using an example created by the HeaderService
header_file = "AT_O_20190531_000001.header"
header_primary = fitsio.read_header(header_file, ext='PRIMARY')
header = header_primary

# The dict where we will store the header contents
header_out = {}

# The PRIMARY HDU
EXTNAME = header["EXTNAME"]
header_out[EXTNAME] = []

# Get all records from header
recs = header.records()
for rec in recs:
    new_rec = {'keyword': rec['name'],
               'value': rec['value'],
               'comment': rec['comment']}
    header_out[EXTNAME].append(new_rec)

# Loop over each of segments
for k in range(16):
    header = fitsio.read_header(header_file, ext=k+1)
    # Pretebd we are in Raft01/S01
    EXTNAME = "R01S01_{}".format(header['EXTNAME'])
    header_out[EXTNAME] = []

    # Get all records
    recs = header.records()
    for rec in recs:
        new_rec = {'keyword': rec['name'],
                   'value': rec['value'],
                   'comment': rec['comment']}
        header_out[EXTNAME].append(new_rec)

# Write out directly using yaml
yaml_outfile = "header_out.yml"
with open(yaml_outfile, 'w') as outfile:
    yaml.dump(header_out, outfile, default_flow_style=False, sort_keys=False)
print("Wrote file:", yaml_outfile)

# Now we are going to read it back to inspect
with open(yaml_outfile, 'r') as outfile:
    header_loaded = yaml.safe_load(outfile)

# Spot inspect contents

# Recover an int
d = header_loaded['PRIMARY'][1]
print(d['keyword'], d['value'])
print(type(d['value']))

# Recover a str
d = header_loaded['PRIMARY'][22]
print(d['keyword'], d['value'])
print(type(d['value']))


# Now let's create a fitsio file (header only) with no data
data = None
filename = "file-from-yaml.fits"
with fitsio.FITS(filename, 'rw', clobber=True, ignore_empty=True) as fits:
    for extname in header_loaded.keys():
        hdr = fitsio.FITSHDR()
        for rec in header_loaded[extname]:
            # Avoid undef comments and set them as empty strings
            if 'comment' not in rec:
                rec['comment'] = ''
            new_rec = {'name': rec['keyword'],
                       'value': rec['value'],
                       'comment': rec['comment']}
            hdr.add_record(new_rec)
        # Write the hdr out
        fits.write(data, header=hdr, extname=extname)
