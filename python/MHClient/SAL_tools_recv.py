#!/usr/bin/env python

import time
import sys
import SALPY_camera 
import SALPY_tcs

class tcs_kernel_FK5Target:

    def __init__(self, timeout=3600, tsleep=0.1):
        self.timeout = timeout
        self.tsleep = tsleep
        self.subscribe()

    def subscribe(self):
        self.mgr = SALPY_tcs.SAL_tcs()
        self.mgr.salTelemetrySub("tcs_kernel_FK5Target")
        self.myData = SALPY_tcs.tcs_kernel_FK5TargetC()
        print "# tcs_kernel_FK5Target subscriber ready" 

    def get(self):
        t0 =  time.time()

        while True:
            retval = self.mgr.getNextSample_kernel_FK5Target(self.myData)
            if retval == 0:
                success = True
                self.ra, self.dec, self.visitID = self.myData.ra, self.myData.dec, int(self.myData.rv)
                break
            if time.time() - t0 > self.timeout:
                print "WARNING: Timeout reading FK5Target"
                success = False
                break
            time.sleep(self.tsleep)
        return success

    def close(self):
        print "Shutting down tcs_kernel_FK5Target"
        self.mgr.salShutdown()


class camera_Filter:

    def __init__(self, timeout=3600, tsleep=0.1):
        self.timeout = timeout
        self.tsleep = tsleep
        self.filter_names = ['u','g','r','i','z','Y']
        self.subscribe()

    def subscribe(self):
        t0 =  time.time()
        self.mgr = SALPY_camera.SAL_camera()
        self.mgr.salTelemetrySub("camera_Filter")
        self.myData = SALPY_camera.camera_FilterC()
        print "# camera_Filter subscriber ready"

    def get(self):
        
        t0 =  time.time()
        while True :
            retval = self.mgr.getNextSample_Filter(self.myData)
            if time.time() - t0 > self.timeout:
                print "WARNING: Timeout reading Filter"
                success = False
                self.filter_name = None
                break
            if retval == 0:
                success = True
                self.filter_name = self.filter_names[self.myData.REB_ID] 
                break
            time.sleep(self.tsleep)
        return success

    def close(self):
        print "Shutting down camera_Filter subscriber ready"
        self.mgr.salShutdown()

class camera_logevent_endReadout:
    
    def __init__(self, timeout=10, tsleep=0.1,priority=1):
        self.timeout = timeout
        self.tsleep = tsleep
        self.priority = priority
        self.subscribe()

    def subscribe(self):
        self.mgr = SALPY_camera.SAL_camera()
        self.mgr.salEvent("camera_logevent_endReadout")
        self.event = SALPY_camera.camera_logevent_endReadoutC()
        self.mgr.getEvent_endReadout(self.event)
        print "# camera_endReadout logger ready"

    def get(self):

        t0 =  time.time()
        self.t0 =  time.time()
        endReadout = False
        print "Waiting for Camera Readout event"

        while True:
            retval = self.mgr.getEvent_endReadout(self.event)
            if retval==0:
                endReadout = True
                break
            if time.time() - t0 > self.timeout:
                print "WARNING: Timeout reading endReadout Event..."
                endReadout = False
                break
            time.sleep(self.tsleep)
        return endReadout

    def close(self):
        print "Shutting down camera_logevent_endReadout"
        self.mgr.salShutdown()

    

