# HeaderService

Development for LSST Meta-data FITS header service

Description
-----------

This is the development for the LSST Meta-data FITS header client. It
uses a set of FITS header library templates and DDS/SAL Python-based
communication layer to populate meta-data and command the header
client to write header files.

Requirements
------------
+ numpy
+ astropy
+ fitsio (https://github.com/esheldon/fitsio)
+ salobj
+ OpenSplice compiled binaries for centOS7
+ A CentOS7 VM or docker container

Examples
--------

```bash
# Setup the path for the HeaderService
source HeaderService/setpath.sh  ~/HeaderService

# Initialize header client (Terminal 1)
ATHS_salobj -c $HEADERSERVICE_DIR/etc/conf/atTelemetry.yaml --send_efd_message   

# Send telemetry to trigger header writing (Terminal 2)
telemetry_sim_ATHS --ra 10 --dec -20.0 --exptime 10 --airmass 1.1 --ha 87 --el 45 --az 15  --NSequence 1  --rotpa 90  --seqnum 1
```
