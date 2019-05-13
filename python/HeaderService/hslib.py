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

import salpytools
import HeaderService
import HeaderService.hutils as hutils
import logging
import os
import sys
import socket
import time

# the controller we want to listen to
# TODO: This could be a configurable list
_CONTROLER_list = ['enterControl',
                   'exitControl',
                   'start',
                   'standby',
                   'enable',
                   'disable']

spinner = hutils.spinner

LOGGER = logging.getLogger(__name__)


class HSworker:

    """ A Class to run and manage the Header Service"""

    def __init__(self, **keys):

        self.keys = keys
        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in list(keys.items()):
            setattr(self, k, v)

        self.setup_logging()

        # Inititalize the State class to keep track of the system's state
        self.init_State()

        # Extract the unique channel by topic/device
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.get_channels()

        # Get the hostname and IP address
        self.get_ip()

        # The user running the process
        self.USER = os.environ['USER']

    def get_ip(self):
        self.ip_address = socket.gethostbyname(socket.gethostname())
        LOGGER.info("Will use IP: {} for broadcasting".format(self.ip_address))

    def setup_logging(self):
        """
        Simple Logger definitions across this module, we call the generic function
        defined in hutils.py
        """
        # Make sure the directory exists
        dirname = os.path.dirname(self.logfile)
        if dirname != '':
            self.check_outdir(dirname)
        hutils.create_logger(logfile=self.logfile, level=self.loglevel)
        LOGGER.info("Will send logging to: {}".format(self.logfile))

    def init_State(self, start_state=None):
        """
        Initialize the State object that keeps track of the HS current state.
        We use a start_state to set the initial state
        """
        if start_state:
            self.start_state = start_state

        self.State = salpytools.DeviceState(Device='ATHeaderService', default_state=self.start_state)
        self.State.send_logEvent('summaryState')
        # Create threads for the controller we want to listen to
        self.tControl = {}
        for ctrl_name in _CONTROLER_list:
            self.tControl[ctrl_name] = salpytools.DDSController(ctrl_name, Device='ATHeaderService',
                                                                State=self.State)
            self.tControl[ctrl_name].start()

        # Set the message for 'SettingApplied' here, we should want to control
        # these from here in the future
        self.State.settings = "HeaderService version:{}\nts_xml version:{}".format(HeaderService.version,
                                                                                   self.ts_xml)

    def get_channels(self):
        """Extract the unique channel by topic/device"""
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.channels = extract_telemetry_channels(self.telemetry,
                                                   start_collection_event=self.start_collection_event,
                                                   end_collection_event=self.end_collection_event,
                                                   imageParam_event=self.imageParam_event)

        # Now separate the keys to collect at the 'end' from the ones at 'start'
        t = self.telemetry  # Short-cut
        self.keywords_start = [k for k in t.keys() if t[k]['collect_after_event'] == 'start_collection_event']
        self.keywords_end = [k for k in t.keys() if t[k]['collect_after_event'] == 'end_collection_event']

    def make_connections(self, start=True):
        """
        Make connection to channels and start the threads as defined
        by the meta-data, and make additional connection for Start/End
        of telemetry Events
        """
        # The dict containing all of the threads and connections
        self.SALconn = {}
        for name, c in self.channels.items():
            self.SALconn[name] = salpytools.DDSSubcriber(c['device'], c['topic'], Stype=c['Stype'])
            if start:
                self.SALconn[name].start()

        # Select the start_collection channel
        self.name_start = get_channel_name(self.start_collection_event)
        self.StartInt = self.SALconn[self.name_start]

        # Select the end_collection channel
        self.name_end = get_channel_name(self.end_collection_event)
        self.EndTelem = self.SALconn[self.name_end]

    def check_outdir(self, filepath):
        """ Make sure that we have a place to put the files"""
        if not os.path.exists(filepath):
            os.makedirs(filepath)
            LOGGER.info("Created dirname:{}".format(filepath))

    def run(self, **keys):

        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in list(keys.items()):
            setattr(self, k, v)
            # print k,v

        # Subscribe to each of the channels we want to susbcribe and store
        # the connection in a dictionary
        LOGGER.info("*** Starting Connections for Meta-data ***")
        self.make_connections()

        # Make sure that we have a place to put the files
        self.check_outdir(self.filepath)

        # Start the web server
        hutils.start_web_server(self.filepath, port_number=self.port_number)

        # And the object to send DMHS messages
        # TODO -- Make this configurable too
        self.dmhs = salpytools.DDSSend("ATHeaderService")
        if self.send_efd_message:
            self.efd = salpytools.DDSSend('EFD')

        # Load up the header template
        self.HDR = HeaderService.HDRTEMPL_ATSCam(vendor=self.vendor,
                                                 write_mode=self.write_mode,
                                                 hdu_delimiter=self.hdu_delimiter)
        self.HDR.load_templates()

        # Go into the eternal loop
        self.run_loop()

    def update_header_geometry(self):

        # Image paramters
        LOGGER.info("Extracting Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageParam_event)
        myData = self.SALconn[name].getCurrent(getNone=True)
        # exit in case we cannot get data from SAL
        if myData is None:
            LOGGER.warning("Cannot get geometry myData from {}".format(name))
            return

        # in case we want to get NAXIS1/NAXIS2, etc.
        geom = hutils.get_image_size_from_imageReadoutParameters(myData)
        # We update the headers and reload them
        self.HDR.CCDGEOM.overh = geom['overh']
        self.HDR.CCDGEOM.overv = geom['overv']
        self.HDR.CCDGEOM.preh = geom['preh']
        LOGGER.info("Reloadling templates")
        self.HDR.load_templates()
        LOGGER.info("For reference: NAXIS1={}".format(geom['NAXIS1']))
        LOGGER.info("For reference: NAXIS2={}".format(geom['NAXIS2']))
        LOGGER.info("Received: overv={}, overh={}, preh={}".format(geom['overv'],
                                                                   geom['overh'],
                                                                   geom['preh']))

    def update_header(self):

        """Update FITSIO header object using the captured metadata"""
        for k, v in self.metadata.items():
            LOGGER.info("Updating header with {:8s} = {}".format(k, v))
            self.HDR.update_record(k, v, 'PRIMARY')

    def get_filenames(self):
        """
        Extract from which section of telemetry we will extract
        'imageName' and define the output names based on that ID
        """
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageName_event)
        myData = self.SALconn[name].getCurrent()
        self.imageName = getattr(myData, self.imageName_event['value'])

        # Construct the hdr and fits filename
        self.filename_HDR = os.path.join(self.filepath, self.format_HDR.format(self.imageName))
        self.filename_FITS = self.format_FITS.format(self.imageName)

    def run_loop(self):

        """Run the loop that waits for a newEvent"""
        loop_n = 0
        while True:

            if self.State.current_state != 'ENABLED':
                sys.stdout.flush()
                sys.stdout.write("Current State is {} [{}]".format(self.State.current_state, next(spinner)))
                sys.stdout.write('\r')

            # newEvent (i.e. startIntegration) loop
            elif self.StartInt.newEvent:
                # Clean/purge all metadata
                self.clean()
                sys.stdout.flush()
                LOGGER.info("Received: {} Event".format(self.name_start))
                self.get_filenames()
                LOGGER.info("Extracted value for imageName: {}".format(self.imageName))

                # Collect metadata at start of integration
                LOGGER.info("Collecting Metadata START : {} Event".format(self.name_start))
                self.collect(self.keywords_start)

                # Wait for end Event (i.e. end of telemetry)
                LOGGER.info("Current State is {} -- waiting for {} event".format(self.State.current_state,
                                                                                 self.name_end))
                self.EndTelem.waitEvent(timeout=self.timeout_endTelem,
                                        after_timeStamp=self.StartInt.timeStamp)
                # Make sure that EndTelem.newEvent happens AFTER StartInt.newEvent
                if self.EndTelem.newEvent:
                    sys.stdout.flush()
                    LOGGER.info("Received: {} Signal".format(self.name_end))
                    # The creation date of the header file -- now!!
                    self.DATE_HDR = hutils.get_date_utc()
                    # Collect metadata at end of integration
                    LOGGER.info("Collecting Metadata END: {} Event".format(self.name_end))
                    self.collect(self.keywords_end)
                    # Collect metadata created by the HeaderService
                    LOGGER.info("Collecting Metadata from HeaderService")
                    self.collect_from_HeaderService()
                    # First we update the header using the information from the camera geometry
                    self.update_header_geometry()
                    self.update_header()
                    # Write the header
                    self.write()
                    # Announce creation to DDS
                    self.announce()
                    self.EndTelem.newEvent = False
                    LOGGER.info("------------------------------------------")
                elif self.EndTelem.timeoutEvent:
                    sys.stdout.flush()
                    LOGGER.warning("Received timeout: {} Signal".format(self.name_end))
                    LOGGER.info("Sending Error Event for timeout")
                    self.timeoutError()
                else:
                    LOGGER.warning("Exited newEvent wait without newEvent or timeout")
            else:
                sys.stdout.flush()
                sys.stdout.write("Current State is {} -- waiting for {} Event...[{}]".format(
                    self.State.current_state, self.name_start, next(spinner)))
                sys.stdout.write('\r')
                time.sleep(self.tsleep)

            time.sleep(self.tsleep)
            loop_n += 1

    def timeoutError(self):
        # Send error code for timeout case
        kw = {'errorCode': 3010,
              'errorReport': "Timeout while waiting for {} Event".format(self.name_end),
              'traceback': '',
              'priority': 1,
              }
        self.dmhs.send_Event('errorCode', **kw)
        LOGGER.info("Sent errorCode: {}".format(kw))

    def announce(self):
        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR)
        bytesize = os.path.getsize(self.filename_HDR)
        LOGGER.info("Got MD5SUM: {}".format(md5value))
        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'byteSize': bytesize,
              'checkSum': md5value,
              'generator': 'ATHeaderService',
              'mimeType': 'FITS',
              'url': self.url_format.format(ip_address=self.ip_address,
                                            port_number=self.port_number,
                                            filename_HDR=os.path.basename(self.filename_HDR)),
              'id': self.imageName,
              'version': 1,
              'priority': 1,
              }
        self.dmhs.send_Event('largeFileObjectAvailable', **kw)
        LOGGER.info("Sent largeFileObjectAvailable: {}".format(kw))
        if self.send_efd_message:
            self.efd.send_Event('largeFileObjectAvailable', **kw)

    def write(self):
        """ Function to call to write the header"""
        self.HDR.write_header(self.filename_HDR)
        LOGGER.info("Wrote header to: {}".format(self.filename_HDR))

    def clean(self):
        self.myData = {}
        self.metadata = {}

    def collect(self, keys):
        """ Collect meta-data from the telemetry-connected channels
        and store it in the 'metadata' dictionary"""

        for k in keys:
            name = get_channel_name(self.telemetry[k])
            param = self.telemetry[k]['value']
            # Only access data payload once
            if name not in self.myData:
                self.myData[name] = self.SALconn[name].getCurrent(getNone=True)

                # Only update metadata if self.myData is defined (i.e. not None)
            if self.myData[name] is None:
                LOGGER.warning("Cannot get keyword: {} from topic: {}".format(k, name))
            else:
                self.metadata[k] = getattr(self.myData[name], param)

    def collect_from_HeaderService(self):
        """Collect and update custom meta-data generated or transformed by the HeaderService"""
        self.DATE_OBS = hutils.get_date_utc(self.metadata['DATE-OBS'])
        self.DATE_BEG = hutils.get_date_utc(self.metadata['DATE-BEG'])
        self.DATE_END = hutils.get_date_utc(self.metadata['DATE-END'])
        self.metadata['DATE-OBS'] = self.DATE_OBS.isot
        self.metadata['DATE-BEG'] = self.DATE_BEG.isot
        self.metadata['DATE-END'] = self.DATE_END.isot
        self.metadata['MJD-OBS'] = self.DATE_OBS.mjd
        self.metadata['MJD-BEG'] = self.DATE_BEG.mjd
        self.metadata['MJD-END'] = self.DATE_END.mjd
        self.metadata['DATE'] = self.DATE_HDR.isot
        self.metadata['MJD'] = self.DATE_HDR.mjd
        self.metadata['FILENAME'] = self.filename_FITS
        # THIS IS AN UGLY HACK TO MAKE IT WORK SEQNUM
        # FIX THIS -- FELIPE, TIAGO, MICHAEL and TIM J. are accomplices
        self.metadata['SEQNUM'] = int(self.metadata['OBSID'].split('_')[-1])
        self.metadata['DAYOBS'] = self.metadata['OBSID'].split('_')[2]


def get_channel_name(c):
    """ Standard formatting for the name of a channel across modules"""
    return '{}_{}'.format(c['device'], c['topic'])


def extract_telemetry_channels(telem, start_collection_event=None,
                               end_collection_event=None,
                               imageParam_event=None):
    """
    Get the unique telemetry channels from telemetry dictionary to
    define the topics that we need to subscribe to
    """
    channels = {}
    for key in telem:
        # Make the name of the channel unique by appending device
        c = {'device': telem[key]['device'],
             'topic': telem[key]['topic'],
             'Stype': telem[key]['Stype']}
        name = get_channel_name(c)
        # Make sure we don't crate extra channels
        if name not in channels.keys():
            channels[name] = c

    # We also need to make sure that we subscribe to the start/end
    # collection Events in case these were not contained by the
    if start_collection_event:
        c = start_collection_event
        name = get_channel_name(c)
        if name not in channels.keys():
            c['Stype'] = 'Event'
            channels[name] = c

    if end_collection_event:
        c = end_collection_event
        name = get_channel_name(c)
        if name not in list(channels.keys()):
            c['Stype'] = 'Event'
            channels[name] = c

    # The imageParam event
    if imageParam_event:
        c = imageParam_event
        name = get_channel_name(c)
        if name not in channels.keys():
            c['Stype'] = 'Event'
            channels[name] = c

    return channels


def subscribe_to_channels(channels, start=True):
    """ make connection to channels and start the threads"""
    SAL_connection = {}
    for name, c in channels.items():
        SAL_connection[name] = salpytools.DDSSubcriber(c['device'], c['topic'], Stype=c['Stype'])
        if start:
            SAL_connection[name].start()

    return SAL_connection
