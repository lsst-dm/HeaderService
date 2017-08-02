#!/usr/bin/env python

import time
import sys
import SALPY_tcs
import SALPY_camera 
import threading
import logging
import HeaderService.hutils as hutils

LOGGER = hutils.create_logger(level=logging.NOTSET,name='SAL_RECV')

class DDSSubcriber(threading.Thread):

    def __init__(self, module, topic, threadID='1', Stype='Telemetry',tsleep=0.5,timeout=3600,nkeep=100):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.module = module
        self.topic  = topic
        self.tsleep = tsleep
        self.Stype  = Stype
        self.timeout = timeout
        self.nkeep   = nkeep
        self.daemon = True
        self.subscribe()
        
        
    def subscribe(self):

        # This section does the equivalent of:
        # self.mgr = SALPY_tcs.SAL_tcs()
        # The steps are:
        # - 'figure out' the SALPY_xxxx module name
        # - finds the library pointer using globals()
        # - creates a mananger

        self.newTelem = False
        SALPY_lib_name = 'SALPY_%s' % self.module
        SALPY_lib = globals()[SALPY_lib_name]
        self.mgr = getattr(SALPY_lib, 'SAL_%s' % self.module)()

        if self.Stype=='Telemetry':
            self.mgr.salTelemetrySub(self.topic)
            self.myData = getattr(SALPY_lib,self.topic+'C')()
            LOGGER.info("%s subscriber ready for topic: %s" % (self.Stype,self.topic))
        elif self.Stype=='Event':
            self.mgr.salEvent(self.topic)
            self.event = getattr(SALPY_lib,self.topic+'C')()
            self.event_topic = self.topic.split("_")[-1]
            self.getEvent_topic = getattr(self.mgr,'getEvent_'+self.event_topic)
            self.getEvent_topic(self.event)
            LOGGER.info("%s subscriber ready for topic: %s" % (self.Stype,self.topic))

    def run_Telemetry(self):
        t0 =  time.time()

        # Generic method to get for example: self.mgr.getNextSample_kernel_FK5Target
        self.nextsample_topic = self.topic.split(self.module)[-1]
        self.getNextSample = getattr(self.mgr,"getNextSample" + self.nextsample_topic)

        self.myDatalist = []
        self.newTelem = False
        while True:
            retval = self.getNextSample(self.myData)
            if retval == 0:
                self.myDatalist.append(self.myData)
                self.myDatalist = self.myDatalist[-self.nkeep:] # Keep only nkeep entries
                self.newTelem = True
            time.sleep(self.tsleep)
        return 

    def run(self):
        if self.Stype == 'Telemetry':
            self.run_Telemetry()
        elif self.Stype == 'Event':
            self.wait_Event()
        else:
            raise ValueError("Stype=%s not defined\n" % self.Stype)

    def getCurrentTelemetry(self):
        if len(self.myDatalist) > 0:
            Telem = self.myDatalist[-1]
            self.newTelem = False
        else:
            Telem = None
        return Telem

    def wait_Event(self):

        t0 =  time.time()
        self.endEvent = False
        LOGGER.info("Waiting for %s event" % self.topic)

        while True:
            #retval = self.mgr.getEvent_endReadout(self.event)
            retval = self.getEvent_topic(self.event)
            if retval==0:
                self.endEvent = True
                break
            if time.time() - t0 > self.timeout:
                LOGGER.info("WARNING: Timeout reading for Event %s" % self.topic)
                self.endEvent = False
                break
            time.sleep(self.tsleep)
        return self.endEvent

    def get_filter_name(self):
        # Need to move these filter definitions to a better place
        self.filter_names = ['u','g','r','i','z','Y']
        self.filter_name = self.filter_names[self.myData.REB_ID] 
        return self.filter_name 


class tcs_kernel_FK5Target:

    def __init__(self, timeout=3600, tsleep=0.1):
        self.timeout = timeout
        self.tsleep = tsleep
        self.subscribe()

    def subscribe(self):
        self.mgr = SALPY_tcs.SAL_tcs()
        self.mgr.salTelemetrySub("tcs_kernel_FK5Target")
        self.myData = SALPY_tcs.tcs_kernel_FK5TargetC()
        LOGGER.info("tcs_kernel_FK5Target subscriber ready" )

    def get(self):
        t0 =  time.time()

        while True:
            retval = self.mgr.getNextSample_kernel_FK5Target(self.myData)
            if retval == 0:
                success = True
                self.ra, self.dec, self.visitID = self.myData.ra, self.myData.dec, int(self.myData.rv)
                break
            if time.time() - t0 > self.timeout:
                LOGGER.info("WARNING: Timeout reading FK5Target")
                success = False
                break
            time.sleep(self.tsleep)
        return success

    def close(self):
        LOGGER.info("Shutting down tcs_kernel_FK5Target")
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
        LOGGER.info("camera_Filter subscriber ready")

    def get(self):
        
        t0 =  time.time()
        while True :
            retval = self.mgr.getNextSample_Filter(self.myData)
            if time.time() - t0 > self.timeout:
                LOGGER.info("WARNING: Timeout reading Filter")
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
        LOGGER.info("Shutting down camera_Filter subscriber ready")
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
        LOGGER.info("camera_endReadout logger ready")

    def get(self):

        t0 =  time.time()
        self.t0 =  time.time()
        endReadout = False
        LOGGER.info("Waiting for Camera Readout event")

        while True:
            retval = self.mgr.getEvent_endReadout(self.event)
            if retval==0:
                endReadout = True
                break
            if time.time() - t0 > self.timeout:
                LOGGER.info("WARNING: Timeout reading endReadout Event...")
                endReadout = False
                break
            time.sleep(self.tsleep)
        return endReadout

    def close(self):
        LOGGER.info("Shutting down camera_logevent_endReadout")
        self.mgr.salShutdown()

    

