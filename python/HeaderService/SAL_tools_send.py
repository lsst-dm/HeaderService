# This file is part of HeaderService
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

""" A collecion of tools to connect with SAL/DDS """

import time
import sys
import SALPY_dmHeaderService
import SALPY_camera
import SALPY_tcs
import logging
import HeaderService.hutils as hutils

""" Functions to send simply telemetry """

LOGGER = hutils.create_logger(level=logging.NOTSET, name=__name__)

# WARNING
# These function have been deprecated and are here only for legacy purpose. New
# code should the salpytools module instead. https://github.com/lsst-dm/salpytools


def send_camera_logevent_startIntegration(**kw):
    """imageSequenceName imageName imageIndex timeStamp priority"""
    mgr = SALPY_camera.SAL_camera()
    mgr.salEvent("camera_logevent_startIntegration")
    myData = SALPY_camera.camera_logevent_startIntegrationC()
    myData.imageSequenceName = kw.get("imageSequenceName")
    myData.imageName = kw.get("imageName")
    myData.imageIndex = kw.get("imageIndex")
    myData.timeStamp = kw.get("timeStamp", time.time())
    myData.priority = kw.get("priority")
    priority = int(myData.priority)
    mgr.logEvent_startIntegration(myData, priority)
    time.sleep(1)
    mgr.salShutdown()


def send_camera_logevent_endSetFilter(filterName, priority=1):
    mgr = SALPY_camera.SAL_camera()
    mgr.salEvent("camera_logevent_endSetFilter")
    myData = SALPY_camera.camera_logevent_endSetFilterC()
    myData.filterName = filterName
    myData.priority = priority
    mgr.logEvent_endSetFilter(myData, priority)
    time.sleep(1)
    mgr.salShutdown()


def send_Filter(fname):

    filter_names = ['u', 'g', 'r', 'i', 'z', 'Y']
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
    LOGGER.info("Sent FILTER=%s" % fname)
    return retval


def send_FK5Target(ra, dec, visitID=1):

    mgr = SALPY_tcs.SAL_tcs()
    mgr.salTelemetryPub("tcs_kernel_FK5Target")
    myData = SALPY_tcs.tcs_kernel_FK5TargetC()
    myData.ra = ra
    myData.dec = dec
    myData.epoc = 2000
    myData.equinox = 2000
    myData.parallax = 1.0
    myData.pmRA = ra
    myData.pmDec = dec
    # myData.rv = 1.0
    myData.rv = visitID
    retval = mgr.putSample_kernel_FK5Target(myData)
    mgr.salShutdown()
    LOGGER.info("Sent RA:%s, DEC:%s" % (ra, dec))
    return retval


def camera_logevent_endReadout(priority=1):

    mgr = SALPY_camera.SAL_camera()
    mgr.salEvent("camera_logevent_endReadout")
    myData = SALPY_camera.camera_logevent_endReadoutC()
    myData.priority = int(priority)
    priority = int(myData.priority)
    mgr.logEvent_endReadout(myData, priority)
    LOGGER.info("Sent event Camera endReadout")
    time.sleep(1)
    mgr.salShutdown()
    return


def dmHeaderService_logevent_LargeFileObjectAvailable(**kwargs):

    mgr = SALPY_dmHeaderService.SAL_dmHeaderService()
    mgr.salEvent("dmHeaderService_logevent_LargeFileObjectAvailable")
    # Build the myData structure
    myData = SALPY_dmHeaderService.dmHeaderService_logevent_LargeFileObjectAvailableC()
    myData.Byte_Size = kwargs.get('Byte_Size')
    myData.Checksum = kwargs.get('Checksum')
    myData.Generator = kwargs.get('Generator')
    myData.Mime = kwargs.get('Mime', 'text/plain')
    myData.URL = kwargs.get('URL')
    myData.Version = kwargs.get('Version', 1)
    myData.priority = kwargs.get('priority', 1)
    priority = int(myData.priority)
    mgr.logEvent_LargeFileObjectAvailable(myData, priority)
    time.sleep(1)
    mgr.salShutdown()
    return
