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

import HeaderService
import HeaderService.hutils as hutils
import HeaderService.hscalc as hscalc
import logging
import os
import sys
import socket
import lsst.ts.salobj as salobj
import asyncio
import time

LOGGER = logging.getLogger(__name__)


class HSWorker(salobj.BaseCsc):

    """ A Class to run and manage the Header Service"""

    def __init__(self, **keys):

        self.keys = keys
        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in list(keys.items()):
            setattr(self, k, v)

        # Get ready non-SAL related tasks
        self.prepare()

        # Extract the unique channel by topic/device
        self.get_channels()

        # Create a salobj.BaseCsc for the HeaderService
        self.create_BaseCsc()

        # Make the connections using saloj.Remote
        self.create_Remotes()

        # Make the connections using saloj.Controller
        self.create_Controllers()

        # Define the callbacks for start/end
        self.define_evt_callbacks()

        # Initialize the timeout task
        self.end_evt_timeout_task = salobj.make_done_future()

    async def close_tasks(self):
        """Close tasks on super and evt timeout"""
        await super().close_tasks()
        self.end_evt_timeout_task.cancel()

    async def end_evt_timeout(self, timeout):
        """Timeout timer for end event telemetry callback"""
        await asyncio.sleep(timeout)
        LOGGER.info(f"{self.name_end} not seen in {timeout} seconds; giving up")
        # Send the timeout warning using the salobj log
        self.log.warning(f"Timeout while waiting for {self.name_end} Event")
        self.clean()

    def report_summary_state(self):
        """Call to report_summary_state and LOGGER"""
        super().report_summary_state()
        LOGGER.info(f"Current state is: {self.summary_state.name}")
        if self.summary_state != salobj.State.ENABLED:
            self.end_evt_timeout_task.cancel()

    def define_evt_callbacks(self):
        """Set the callback functions based on configuration"""

        # Select the start_collection callback
        devname = self.start_collection_event['device']
        topic = self.start_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.start_collection_event_callback

        # Select the end_collection callback
        devname = self.end_collection_event['device']
        topic = self.end_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.end_collection_event_callback

    def start_collection_event_callback(self, data):
        """ The callback function for the START collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            LOGGER.info(f"Current State is {self.summary_state.name}")
            return

        # Clean/purge all metadata
        self.clean()
        sys.stdout.flush()
        LOGGER.info(f"Received: {self.name_start} Event")

        # For safety cancel the timeout task before we start it
        self.end_evt_timeout_task.cancel()
        self.end_evt_timeout_task = asyncio.ensure_future(self.end_evt_timeout(timeout=self.timeout_endTelem))

        # Get the filenames from the start event payload.
        self.get_filenames()
        LOGGER.info(f"Extracted value for imageName: {self.imageName}")

        # Collect metadata at start of integration
        LOGGER.info(f"Collecting Metadata START : {self.name_start} Event")
        self.collect(self.keywords_start)

        # Now we wait for end event
        LOGGER.info(f"Waiting for {self.name_end} Event")

    def end_collection_event_callback(self, data):
        """ The callback function for the END collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            LOGGER.info(f"Current State is {self.summary_state.name}")
            return

        LOGGER.info(f"Received: {self.name_end} Event")
        if self.end_evt_timeout_task.done():
            LOGGER.info(f"Not collecting end data because not expecting {self.name_end}")
            LOGGER.warning(f"{self.name_end} seen when not expected; ignored")
            LOGGER.info(f"Current State is {self.summary_state.name}")
            return

        # Cancel/stop the timeout task because we got the END callback
        self.end_evt_timeout_task.cancel()
        # Store the creation date of the header file -- i.e. now!!
        self.metadata['DATE'] = time.time()
        # Collect metadata at end of integration
        LOGGER.info(f"Collecting Metadata END: {self.name_end} Event")
        self.collect(self.keywords_end)
        # Collect metadata created by the HeaderService
        LOGGER.info("Collecting Metadata from HeaderService")
        self.collect_from_HeaderService()
        # First we update the header using the information
        # from the camera geometry
        self.update_header_geometry()
        self.update_header()
        # Write the header
        self.write()
        # Announce creation event
        self.announce()
        LOGGER.info(f"-------- Done: {self.imageName} -------------------")
        LOGGER.info(f"-------- Ready for next {self.name_start} -----")
        # Report and print the state
        self.report_summary_state()

    def get_ip(self):
        """Figure out the IP we will be using to broadcast"""
        self.ip_address = socket.gethostbyname(socket.gethostname())
        LOGGER.info("Will use IP: {} for web service".format(self.ip_address))

    def setup_logging(self):
        """
        Simple Logger definitions across this module, we call the generic
        function defined in hutils.py
        """
        # Make sure the directory exists
        dirname = os.path.dirname(self.logfile)
        if dirname != '':
            self.check_outdir(dirname)
        hutils.create_logger(logfile=self.logfile, level=self.loglevel,
                             log_format=self.log_format, log_format_date=self.log_format_date)
        LOGGER.info("Logging Started")
        LOGGER.info(f"Will send logging to: {self.logfile}")

    def create_BaseCsc(self):
        """
        Create a BaseCsc for the the HeaderService. We initialize the
        State object that keeps track of the HS current state.  We use
        a start_state to set the initial state
        """
        LOGGER.info(f"Starting the CSC with {self.hs_name}")
        super().__init__(name=self.hs_name, index=self.hs_index, initial_state=self.hs_initial_state)
        LOGGER.info(f"Creating worker for: {self.hs_name}")
        LOGGER.info(f"Running salobj version: {salobj.__version__}")
        LOGGER.info(f"Starting in State:{self.summary_state.name}")

    def create_Remotes(self):
        """
        Create the Remotes to collect telemetry/Events for channels as
        defined by the meta-data
        """
        LOGGER.info("*** Starting Connections for Meta-data ***")
        # The list containing the unique devices (CSCs) to make connection
        self.devices = []
        # The dict containing all of the threads and connections
        self.Remote = {}
        self.Remote_get = {}
        for name, c in self.channels.items():
            devname = c['device']
            # Make sure we only crete these once
            if devname not in self.devices:
                self.devices.append(devname)
                self.Remote[devname] = salobj.Remote(domain=self.domain, name=devname, index=0)
                LOGGER.info(f"Created Remote for {devname}")
            # capture the evt.get() function for the channel
            if c['Stype'] == 'Event':
                self.Remote_get[name] = getattr(self.Remote[devname], f"evt_{c['topic']}").get
                LOGGER.info(f"Storing Remote.evt_{c['topic']}.get() for {name}")
            if c['Stype'] == 'Telemetry':
                self.Remote_get[name] = getattr(self.Remote[devname], f"tel_{c['topic']}").get
                LOGGER.info(f"Storing Remote.tel_{c['topic']}.get() for {name}")

        # Select the start_collection channel
        self.name_start = get_channel_name(self.start_collection_event)
        # Select the end_collection channel
        self.name_end = get_channel_name(self.end_collection_event)

    def create_Controllers(self):
        """
        Create Controllers to send the LFO message Event for the HederService
        and optionally for the EFD in case we want to emulate it
        """
        # We also need to create a Controller for the HeaderService
        self.hs_controller = salobj.Controller(name=self.hs_name, index=0)
        LOGGER.info(f"Created Controller for {self.hs_name}")

        # And another optional in case we want to emulate the EFD
        if self.send_efd_message:
            self.efd_controller = salobj.Controller(name='EFD', index=0)
            LOGGER.info(f"Created Controller for EFD")

    def get_channels(self):
        """Extract the unique channels by topic/device"""
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.channels = extract_telemetry_channels(self.telemetry,
                                                   start_collection_event=self.start_collection_event,
                                                   end_collection_event=self.end_collection_event,
                                                   imageParam_event=self.imageParam_event)
        # Separate the keys to collect at the 'end' from the ones at 'start'
        t = self.telemetry  # Short-cut
        self.keywords_start = [k for k in t.keys() if t[k]['collect_after_event'] == 'start_collection_event']
        self.keywords_end = [k for k in t.keys() if t[k]['collect_after_event'] == 'end_collection_event']

    def check_outdir(self, filepath):
        """ Make sure that we have a place to put the files"""
        if not os.path.exists(filepath):
            os.makedirs(filepath)
            LOGGER.info("Created dirname:{}".format(filepath))

    def prepare(self):
        """
        Non-SAL/salobj related task that need to be prepared
        """
        # Logging
        self.setup_logging()

        # The user running the process
        self.USER = os.environ['USER']

        # Make sure that we have a place to put the files
        self.check_outdir(self.filepath)

        # Get the hostname and IP address
        self.get_ip()

        # Start the web server
        hutils.start_web_server(self.filepath, port_number=self.port_number)

        # Load up the header templates
        self.HDR = HeaderService.HDRTEMPL_ATSCam(vendor=self.vendor,
                                                 write_mode=self.write_mode,
                                                 hdu_delimiter=self.hdu_delimiter)
        self.HDR.load_templates()

    def update_header_geometry(self):
        """ Update the image geometry Camera Event """
        # Image paramters
        LOGGER.info("Extracting Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageParam_event)
        myData = self.Remote_get[name]()
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
        Figure out the section of the telemetry from which we will extract
        'imageName' and define the output names based on that ID
        """
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageName_event)
        myData = self.Remote_get[name]()
        self.imageName = getattr(myData, self.imageName_event['value'])

        # Construct the hdr and fits filename
        self.filename_HDR = os.path.join(self.filepath, self.format_HDR.format(self.imageName))
        self.filename_FITS = self.format_FITS.format(self.imageName)

    def announce(self):
        """
        Broadcast the LFO Event for the HeaderService and optionally
        emulate it for the EFD
        """
        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR)
        bytesize = os.path.getsize(self.filename_HDR)
        LOGGER.info("Got MD5SUM: {}".format(md5value))
        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'byteSize': bytesize,
              'checkSum': md5value,
              'generator': self.hs_name,
              'mimeType': self.write_mode.upper(),
              'url': self.url_format.format(ip_address=self.ip_address,
                                            port_number=self.port_number,
                                            filename_HDR=os.path.basename(self.filename_HDR)),
              'id': self.imageName,
              'version': 1,
              'priority': 1,
              }

        self.hs_controller.evt_largeFileObjectAvailable.set_put(**kw)
        LOGGER.info(f"Sent {self.hs_name} largeFileObjectAvailable: {kw}")
        if self.send_efd_message:
            self.efd_controller.evt_largeFileObjectAvailable.set_put(**kw)
            LOGGER.info(f"Sent EFD largeFileObjectAvailable: {kw}")

    def write(self):
        """ Function to call to write the header"""
        self.HDR.write_header(self.filename_HDR)
        LOGGER.info("Wrote header to: {}".format(self.filename_HDR))

    def clean(self):
        """ Clean up metadata and myData dicts"""
        self.myData = {}
        self.metadata = {}

    def collect(self, keys):
        """ Collect meta-data from the telemetry-connected channels
        and store it in the 'metadata' dictionary"""

        # Make sure the myData payload is reset before collection
        # to clean up data from previous events/telemetry
        self.myData = {}
        for k in keys:
            name = get_channel_name(self.telemetry[k])
            param = self.telemetry[k]['value']
            # Access data payload only once
            if name not in self.myData:
                self.myData[name] = self.Remote_get[name]()
                # Only update metadata if self.myData is defined (not None)
            if self.myData[name] is None:
                LOGGER.warning(f"Cannot get keyword: {k} from topic: {name}")
            else:
                self.metadata[k] = getattr(self.myData[name], param)
                LOGGER.debug(f"Extacted {k}={self.metadata[k]} from topic: {name}")

    def collect_from_HeaderService(self):

        """
        Collect and update custom meta-data generated or transformed by
        the HeaderService
        """

        # Reformat and calculate dates based on different timeStamps
        self.DATE = hscalc.get_date_utc(self.metadata['DATE'])
        self.DATE_OBS = hscalc.get_date_utc(self.metadata['DATE-OBS'])
        self.DATE_BEG = hscalc.get_date_utc(self.metadata['DATE-BEG'])
        self.DATE_END = hscalc.get_date_utc(self.metadata['DATE-END'])
        self.metadata['DATE'] = self.DATE.isot
        self.metadata['DATE-OBS'] = self.DATE_OBS.isot
        self.metadata['DATE-BEG'] = self.DATE_BEG.isot
        self.metadata['DATE-END'] = self.DATE_END.isot
        self.metadata['MJD'] = self.DATE.mjd
        self.metadata['MJD-OBS'] = self.DATE_OBS.mjd
        self.metadata['MJD-BEG'] = self.DATE_BEG.mjd
        self.metadata['MJD-END'] = self.DATE_END.mjd
        self.metadata['FILENAME'] = self.filename_FITS
        # THIS IS AN UGLY HACK TO MAKE IT WORK SEQNUM
        # FIX THIS -- FELIPE, TIAGO, MICHAEL and TIM J. are accomplices
        self.metadata['SEQNUM'] = int(self.metadata['OBSID'].split('_')[-1])
        self.metadata['DAYOBS'] = self.metadata['OBSID'].split('_')[2]

        # The EL/AZ at start
        if 'ELSTART' and 'AZSTART' in self.metadata:
            LOGGER.info("Computing RA/DEC from ELSTART/AZSTART")
            ra, dec = hscalc.get_radec_from_altaz(alt=self.metadata['ELSTART'],
                                                  az=self.metadata['AZSTART'],
                                                  obstime=self.DATE_BEG,
                                                  lat=self.HDR.header['PRIMARY']['OBS-LAT'],
                                                  lon=self.HDR.header['PRIMARY']['OBS-LONG'],
                                                  height=self.HDR.header['PRIMARY']['OBS-ELEV'])
            self.metadata['RASTART'] = ra
            self.metadata['DECSTART'] = dec
        else:
            LOGGER.info("No 'ELSTART' and 'AZSTART'")

        # The EL/AZ at end
        if 'ELEND' and 'AZEND' in self.metadata:
            LOGGER.info("Computing RA/DEC from ELEND/AZEND")
            ra, dec = hscalc.get_radec_from_altaz(alt=self.metadata['ELEND'],
                                                  az=self.metadata['AZEND'],
                                                  obstime=self.DATE_BEG,
                                                  lat=self.HDR.header['PRIMARY']['OBS-LAT'],
                                                  lon=self.HDR.header['PRIMARY']['OBS-LONG'],
                                                  height=self.HDR.header['PRIMARY']['OBS-ELEV'])
            self.metadata['RAEND'] = ra
            self.metadata['DECEND'] = dec
        else:
            LOGGER.info("No 'ELEND' and 'AZEND'")


def get_channel_name(c):
    """ Standard formatting for the name of a channel across modules"""
    return '{}_{}'.format(c['device'], c['topic'])


def get_channel_device(c):
    """ Standard formatting for the name of a channel across modules"""
    return c['device']


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
