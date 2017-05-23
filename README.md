# MHClient

Development for LSST Meta-data FITS header client

Description
-----------

This is the development for the LSST Meta-data FITS header client. It
uses a set of FITS header library templates and DDS/SAL Python-based
communication layer to populate meta-data and command the header
client to write header files.

Requirements
------------
+ numpy
+ fitsio (https://github.com/esheldon/fitsio)
+ Python DDS/SAL libraries 
+ OpenSplice compiled binaries for centOS7
+ A CentOS7 VM or docker container

Examples
--------

```bash
# Setup the path for the MHClient
source MHClient/setpath.sh  ~/MHClient 

# Initialize header client (Terminal 1)
header_client_test 

# Send telemetry a control writing of header (Terminal 2)
telemetry_sim_single --ra 21.723 --dec -45.127 --band r --visitID 1

```
