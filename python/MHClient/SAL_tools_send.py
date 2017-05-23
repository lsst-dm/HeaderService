
""" A collecion of tools to connect with SAL/DDS """

import time
import sys
import SALPY_camera 
import SALPY_tcs

""" Functions to send simply telemetry """

# TODO:
# Make these function classes to avoid init overhead

def send_Filter(fname):
    
    filter_names = ['u','g','r','i','z','Y']
    if fname not in filter_names:
        sys.exit("ERROR: filter %s not in filter names" % fname)

    mgr = SALPY_camera.SAL_camera()
    mgr.salTelemetryPub("camera_Filter")
    myData = SALPY_camera.camera_FilterC()

    # Get the index
    filterID = filter_names.index(fname)
    myData.Loader_telemetry = filterID
    myData.REB_ID = filterID
    retval = mgr.putSample_Filter(myData)
    mgr.salShutdown()
    print "Sent FILTER=%s" % fname
    return retval

def send_FK5Target(ra,dec,visitID):

    mgr = SALPY_tcs.SAL_tcs()
    mgr.salTelemetryPub("tcs_kernel_FK5Target")
    myData = SALPY_tcs.tcs_kernel_FK5TargetC()
    myData.ra = ra
    myData.dec = dec
    myData.epoc = 2000
    myData.equinox = 2000
    myData.parallax = 1.0
    myData.pmDec = 1.0
    myData.pmRA = 1.0
    #myData.rv = 1.0
    myData.rv = visitID
    retval = mgr.putSample_kernel_FK5Target(myData)
    mgr.salShutdown()
    print "Sent RA:%s, DEC:%s" % (ra,dec)
    print "Sent visitID:%s" % visitID
    return

def camera_logevent_endReadout(priority=1):

    mgr = SALPY_camera.SAL_camera()
    mgr.salEvent("camera_logevent_endReadout")
    myData = SALPY_camera.camera_logevent_endReadoutC()
    myData.priority=int(priority)
    priority=int(myData.priority)
    mgr.logEvent_endReadout(myData, priority)
    print "Sent event Camera endReadout"
    time.sleep(1)
    mgr.salShutdown()
    return
