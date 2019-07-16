#!/usr/bin/env python3

import time
import argparse
import HeaderService.hutils as hutils
import HeaderService.hscalc as hscalc
import HeaderService.camera_coords as camera_coords
import random

import lsst.ts.salobj as salobj

LOGGER = hutils.create_logger()

# Get the info from the camera_coords library for and E2V sensor
_GEO = camera_coords.CCDGeom('E2V')


def cmdline():

    # Make conf_parser that hold values from a config.ini file
    parser = argparse.ArgumentParser(description="Send telemetry to Header Client")

    # The command-line arguments
    parser.add_argument("--ra", action="store", default=None, type=float,
                        help="The RA of the visit")
    parser.add_argument("--dec", action="store", default=None, type=float,
                        help="The DEC of the visit")
    parser.add_argument("--rotpa", action="store", default=0.0, type=float,
                        help="The ROTPA for the visit")
    parser.add_argument("--filter", action="store", default='r',
                        help="Name of the filter")
    parser.add_argument("--grating", action="store", default='R400',
                        help="Name of the grating")
    parser.add_argument("--imageSequenceName", action="store", default='LSSTTEST',
                        help="ImageSequenceName")
    # Control imageName
    parser.add_argument("--telcode", action="store", default='AT',
                        help="The code for the telecope")
    parser.add_argument("--controller", action="store", default='O',
                        help="The controller (O for OCS, C for CCS)")
    parser.add_argument("--dayobs", action="store", default=None,
                        help="The observation day as defined by image name")
    parser.add_argument("--seqnum", action="store", default=1, type=int,
                        help="The sequence number from the image name")
    parser.add_argument("--NSequence", action="store", default=3, type=int,
                        help="Number of exposure in sequence")

    parser.add_argument("--exptime", action="store", default=15, type=float,
                        help="Exposure time in seconds")
    parser.add_argument("--airmass", action="store", default=1.237, type=float,
                        help="Airmass")
    parser.add_argument("--ha", action="store", default='30.0', type=str,
                        help="The HA")
    parser.add_argument("--el", action="store", default=75.0, type=float,
                        help="The elevation angle")
    parser.add_argument("--az", action="store", default=45.0, type=float,
                        help="The azimuth angle")

    parser.add_argument("--sleeptime", action="store", default=1, type=float,
                        help="Sleep Time between step, in seconds")
    parser.add_argument("--preh", action="store", default=_GEO.preh, type=int,
                        help="prescan horizontal")
    parser.add_argument("--overh", action="store", default=_GEO.overh, type=int,
                        help="overscal horizontal")
    parser.add_argument("--overv", action="store", default=_GEO.overv, type=int,
                        help="overscal vertical")
    args = parser.parse_args()
    return args


if __name__ == "__main__":

    # Get the command line arguments
    args = cmdline()

    # Create handlers for the CSCs we want to simulate messages
    cam = salobj.Controller(name="ATCamera", index=0)
    ptg = salobj.Controller(name="ATPtg", index=0)
    mcs = salobj.Controller(name="ATMCS", index=0)
    spec = salobj.Controller(name="ATSpectrograph", index=0)

    # Camera Geometry
    # Send sub-set of imageReadoutParameters, we populate only a few fields
    kwRO = {'overRows': args.overv,
            'overCols': args.overh,
            'preCols': args.preh,
            'readCols': _GEO.dimh,
            'readCols2': 0,
            'readRows': _GEO.dimv}
    cam.evt_imageReadoutParameters.set_put(**kwRO)
    LOGGER.info("Sending imageReadoutParameters")

    # Poiting information
    # Send the pointing event -- here we populate only a few fields
    kwTA = {'timestamp': time.time(),
            'ra': args.ra,
            'declination': args.dec,
            'rotPA': args.rotpa,
            'priority': 1}
    ptg.evt_currentTarget.set_put(**kwTA)
    LOGGER.info("Sending currentTarget")

    # Filter information for ATSpectrograph
    kwFT = {'name': args.filter,
            'position': 1,  # Made up
            'priority': 1}
    spec.evt_reportedFilterPosition.set_put(**kwFT)
    LOGGER.info("Sending reportedFilterPosition")

    # Disperser information for ATSpectrograph
    kwDP = {'name': args.grating,
            'position': 2,  # Made up
            'priority': 1}
    spec.evt_reportedDisperserPosition.set_put(**kwDP)
    LOGGER.info("Sending reportedDisperserPosition")

    # Linear Stage position for ATSpectrograph
    kwLS = {'position': 2,  # Made up
            'priority': 1}
    spec.evt_reportedLinearStagePosition.set_put(**kwLS)
    LOGGER.info("Sending reportedLinearStagePosition")

    LOGGER.info("---Sleeping for 1 s ---")
    time.sleep(1)
    LOGGER.info("---Starting Image loop---")

    # Loop over NSequence
    for k in range(args.NSequence):

        timeStamp = time.time()
        seqN = args.seqnum + k
        LOGGER.info("----Starting Integration {}".format(seqN))

        # We need to emulate this format from camera:
        # AT_O_20190409_000008.header
        if args.dayobs:
            DAYOBS = args.dayobs
        else:
            DATE_OBS = hscalc.get_date_utc(timeStamp)
            DAYOBS = DATE_OBS.datetime.strftime('%Y%m%d')
        imageName = "{}_{}_{}_{:06d}".format(args.telcode, args.controller, DAYOBS, seqN)

        # Send CCD temperature telemetry using a random generator
        kwCCD = {'ccdTemp0': random.uniform(-30, 0)}
        cam.tel_wreb.set_put(**kwCCD)
        LOGGER.info("Sending wreb")

        # The START telemetry for Airmass using ATPtg.prospectiveTargetStatus
        kwTA = {'timestamp': time.time(),
                'ha': args.ha,
                'airmass': args.airmass}
        ptg.tel_prospectiveTargetStatus.set_put(**kwTA)
        LOGGER.info("Sending prospectiveTargetStatus")

        # The START telemetry for EL and AZ from the ATMCS.mountEncoders
        kwMC = {'elevationCalculatedAngle': args.el,
                'azimuthCalculatedAngle': args.az}
        mcs.tel_mountEncoders.set_put(**kwMC)
        LOGGER.info("Sending mountEncoders")

        # Send the startIntegration for image: k
        LOGGER.info("Sending starIntegration")
        kwInt = {'imageSequenceName': args.imageSequenceName,
                 'imageName': imageName,
                 'imageIndex': k+1,
                 'timeStamp': timeStamp,
                 'exposureTime': args.exptime,
                 'priority': 1}
        cam.evt_startIntegration.set_put(**kwInt)
        LOGGER.info("Sending startIntergration: {}".format(kwInt))
        LOGGER.info(f"Waiting for {args.exptime} sec")
        time.sleep(args.exptime)

        # Send startReadout Event after integration is finished
        LOGGER.info("Sending startReadout")
        cam.evt_startReadout.set_put(**kwInt)

        # Send Measured exptime event
        LOGGER.info("Sending Measured Exptime")
        cam.evt_shutterMotionProfile.set_put(measuredExposureTime=args.exptime+0.35)

        # The END telemetry for Airmass using ATPtg.prospectiveTargetStatus
        kwTA = {'timestamp': time.time(),
                'ha': str(float(args.ha)*1.01),
                'airmass': args.airmass*1.01}
        ptg.tel_prospectiveTargetStatus.set_put(**kwTA)
        LOGGER.info("Sending prospectiveTargetStatus")

        # The END telemetry for EL and AZ from the ATMCS.mountEncoders
        kwMC = {'elevationCalculatedAngle': args.el*1.01,
                'azimuthCalculatedAngle': args.az*1.01}
        mcs.tel_mountEncoders.set_put(**kwMC)
        LOGGER.info("Sending mountEncoders")

        # Send endReadout event
        LOGGER.info("Sending endReadout")
        kwInt['timeStamp'] = time.time()
        cam.evt_endReadout.set_put(**kwInt)

        # send endOfImageTelemetry event
        LOGGER.info("Sending endOfImageTelemetry")
        kwInt['timeStamp'] = time.time()
        cam.evt_endOfImageTelemetry.set_put(**kwInt)
