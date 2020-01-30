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

import os
import sys
import socket
import asyncio
import time
import types
import subprocess
from . import hutils
from . import hscalc
from lsst.ts import salobj


class HSWorker(salobj.BaseCsc):

    """ A Class to run and manage the Header Service"""

    def __init__(self, **keys):

        # Load the configurarion
        self.config = types.SimpleNamespace(**keys)

        # Create a salobj.BaseCsc and get logger
        self.create_BaseCsc()

        # Get ready non-SAL related tasks
        self.prepare()

        # Extract the unique channel by topic/device
        self.get_channels()

        # Make the connections using saloj.Remote
        self.create_Remotes()

        # Make an optional Controller in case we want to emulate the EFD
        if self.config.send_efd_message:
            self.efd_controller = salobj.Controller(name='EFD', index=0)
            self.log.info(f"Created Controller for EFD")

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
        self.log.info(f"{self.name_end} not seen in {timeout} seconds; giving up")
        # Send the timeout warning using the salobj log
        self.log.warning(f"Timeout while waiting for {self.name_end} Event")
        self.clean()

    def report_summary_state(self):
        """Call to report_summary_state and LOGGER"""
        super().report_summary_state()
        self.log.info(f"Current state is: {self.summary_state.name}")
        if self.summary_state != salobj.State.ENABLED:
            self.end_evt_timeout_task.cancel()

    def define_evt_callbacks(self):
        """Set the callback functions based on configuration"""

        # Select the start_collection callback
        devname = self.config.start_collection_event['device']
        topic = self.config.start_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.start_collection_event_callback

        # Select the end_collection callback
        devname = self.config.end_collection_event['device']
        topic = self.config.end_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.end_collection_event_callback

    def start_collection_event_callback(self, data):
        """ The callback function for the START collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            self.log.info(f"Current State is {self.summary_state.name}")
            return

        # Clean/purge all metadata
        self.clean()
        sys.stdout.flush()
        self.log.info(f"Received: {self.name_start} Event")

        # Get the requested exposure time to estimate the timeout
        exptime_key = self.config.timeout_keyword
        self.log.info("Collecting key to set timeout as key %s + %s" %
                      (exptime_key, self.config.timeout_exptime))
        self.collect([exptime_key])
        timeout = self.metadata[exptime_key] + self.config.timeout_exptime
        self.log.info(f"Using timeout: %s [s]" % timeout)

        # For safety cancel the timeout task before we start it
        self.end_evt_timeout_task.cancel()
        self.end_evt_timeout_task = asyncio.ensure_future(self.end_evt_timeout(timeout=timeout))

        # Get the filenames from the start event payload.
        self.get_filenames()
        self.log.info(f"Extracted value for imageName: {self.imageName}")

        # Collect metadata at start of integration
        self.log.info(f"Collecting Metadata START : {self.name_start} Event")
        self.collect(self.keywords_start)

        # Now we wait for end event
        self.log.info(f"Waiting for {self.name_end} Event")

    def end_collection_event_callback(self, data):
        """ The callback function for the END collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            self.log.info(f"Current State is {self.summary_state.name}")
            return

        self.log.info(f"Received: {self.name_end} Event")
        if self.end_evt_timeout_task.done():
            self.log.info(f"Not collecting end data because not expecting {self.name_end}")
            self.log.warning(f"{self.name_end} seen when not expected; ignored")
            self.log.info(f"Current State is {self.summary_state.name}")
            return

        # Cancel/stop the timeout task because we got the END callback
        self.end_evt_timeout_task.cancel()
        # Store the creation date of the header file -- i.e. now!!
        self.metadata['DATE'] = time.time()
        # Collect metadata at end of integration
        self.log.info(f"Collecting Metadata END: {self.name_end} Event")
        self.collect(self.keywords_end)
        # Collect metadata created by the HeaderService
        self.log.info("Collecting Metadata from HeaderService")
        self.collect_from_HeaderService()
        # First we update the header using the information
        # from the camera geometry
        self.update_header_geometry()
        self.update_header()
        # Write the header
        self.write()
        # Announce creation event
        self.announce()
        self.log.info(f"-------- Done: {self.imageName} -------------------")
        self.log.info(f"-------- Ready for next {self.name_start} -----")
        # Report and print the state
        self.report_summary_state()

    def get_ip(self):
        """Figure out the IP we will be using to broadcast"""
        self.ip_address = socket.gethostbyname(socket.gethostname())
        self.log.info("Will use IP: {} for web service".format(self.ip_address))

    def start_web_server(self, logfile, httpserver="http.server"):

        """
        Start a light web service to serve the header files to the EFD
        """

        # Change PYTHONUNBUFFERED to 1 to allow continuous writing.
        os.environ['PYTHONUNBUFFERED'] = '1'

        # Open the file handle
        weblog = open(logfile, 'a')
        weblog.flush()

        self.log.info(f"Will send web server logs to: {logfile}")
        # Get the system's python
        python_exe = sys.executable
        # Make sure there isn't another process running
        cmd = "ps -ax | grep {0} | grep -v grep | awk '{{print $1}}'".format(httpserver)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        pid = p.stdout.read().decode()
        self.log.info(f"Writing web log to: {logfile}")

        if pid == '':
            # Store the current location so we can go back here
            cur_dirname = os.getcwd()
            os.chdir(self.config.filepath)
            # The subprocess call
            self.log.info(f"Will start web server on dir: {self.config.filepath}")
            self.log.info(f"Serving at port: {self.config.port_number}")
            p = subprocess.Popen([python_exe, '-m', httpserver, str(self.config.port_number)],
                                 stdout=weblog, stderr=weblog)
            time.sleep(1)
            self.log.info("Done Starting web server")
            # Get back to where we were
            os.chdir(cur_dirname)
        elif int(pid) > 0:
            self.log.info(f"{httpserver} already running with pid:{int(pid)}  ... Bye")
        else:
            self.log.info("Warning: Wrong process id - will not start www service")

    def setup_logging(self):
        """
        Simple Logger definitions across this module, we call the generic
        function defined in hutils.py
        """
        # Make sure the directory exists
        dirname = os.path.dirname(self.config.logfile)
        if dirname != '':
            self.check_outdir(dirname)
        hutils.configure_logger(self.log, logfile=self.config.logfile,
                                level=self.config.loglevel,
                                log_format=self.config.log_format,
                                log_format_date=self.config.log_format_date)
        self.log.info(f"Logging Started at level:{self.config.loglevel}")
        self.log.info(f"Will send logging to: {self.config.logfile}")

    def create_BaseCsc(self):
        """
        Create a BaseCsc for the the HeaderService. We initialize the
        State object that keeps track of the HS current state.  We use
        a start_state to set the initial state
        """
        super().__init__(name=self.config.hs_name, index=self.config.hs_index,
                         initial_state=getattr(salobj.State, self.config.hs_initial_state))
        self.log.info(f"Starting the CSC with {self.config.hs_name}")
        self.log.info(f"Creating worker for: {self.config.hs_name}")
        self.log.info(f"Running salobj version: {salobj.__version__}")
        self.log.info(f"Starting in State:{self.summary_state.name}")

    def create_Remotes(self):
        """
        Create the Remotes to collect telemetry/Events for channels as
        defined by the meta-data
        """
        self.log.info("*** Starting Connections for Meta-data ***")
        # The list containing the unique devices (CSCs) to make connection
        self.devices = []
        # The dict containing all of the threads and connections
        self.Remote = {}
        self.Remote_get = {}
        for name, c in self.channels.items():
            devname = c['device']
            # Make sure we only create these once
            if devname not in self.devices:
                self.devices.append(devname)
                self.Remote[devname] = salobj.Remote(domain=self.domain, name=devname, index=0)
                self.log.info(f"Created Remote for {devname}")
            # capture the evt.get() function for the channel
            if c['Stype'] == 'Event':
                self.Remote_get[name] = getattr(self.Remote[devname], f"evt_{c['topic']}").get
                self.log.info(f"Storing Remote.evt_{c['topic']}.get() for {name}")
            if c['Stype'] == 'Telemetry':
                self.Remote_get[name] = getattr(self.Remote[devname], f"tel_{c['topic']}").get
                self.log.info(f"Storing Remote.tel_{c['topic']}.get() for {name}")

        # Select the start_collection channel
        self.name_start = get_channel_name(self.config.start_collection_event)
        # Select the end_collection channel
        self.name_end = get_channel_name(self.config.end_collection_event)

    def get_channels(self):
        """Extract the unique channels by topic/device"""
        self.log.info("Extracting Telemetry channels from telemetry dictionary")
        self.channels = extract_telemetry_channels(self.config.telemetry,
                                                   start_collection_event=self.config.start_collection_event,
                                                   end_collection_event=self.config.end_collection_event,
                                                   imageParam_event=self.config.imageParam_event)
        # Separate the keys to collect at the 'end' from the ones at 'start'
        self.keywords_start = [key for key, value in self.config.telemetry.items()
                               if value['collect_after_event'] == 'start_collection_event']
        self.keywords_end = [key for key, value in self.config.telemetry.items()
                             if value['collect_after_event'] == 'end_collection_event']

    def check_outdir(self, filepath):
        """ Make sure that we have a place to put the files"""
        if not os.path.exists(filepath):
            os.makedirs(filepath)
            self.log.info(f"Created dirname:{filepath}")

    def prepare(self):
        """
        Non-SAL/salobj related task that need to be prepared
        """
        # Logging
        self.setup_logging()

        # The user running the process
        self.USER = os.environ['USER']

        # Make sure that we have a place to put the files
        self.check_outdir(self.config.filepath)

        # Get the hostname and IP address
        self.get_ip()

        # Start the web server
        self.start_web_server(self.config.weblogfile)
        # Load up the header templates
        self.HDR = hutils.HDRTEMPL_ATSCam(logger=self.log,
                                          vendor=self.config.vendor,
                                          write_mode=self.config.write_mode,
                                          hdu_delimiter=self.config.hdu_delimiter)
        self.HDR.load_templates()

    def update_header_geometry(self):
        """ Update the image geometry Camera Event """
        # Image paramters
        self.log.info("Extracting Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.config.imageParam_event)
        myData = self.Remote_get[name]()
        # exit in case we cannot get data from SAL
        if myData is None:
            self.log.warning("Cannot get geometry myData from {}".format(name))
            return

        # in case we want to get NAXIS1/NAXIS2, etc.
        geom = hutils.get_image_size_from_imageReadoutParameters(myData)
        # We update the headers and reload them
        self.HDR.CCDGEOM.overh = geom['overh']
        self.HDR.CCDGEOM.overv = geom['overv']
        self.HDR.CCDGEOM.preh = geom['preh']
        self.log.info("Reloadling templates")
        self.HDR.load_templates()
        self.log.info("For reference: NAXIS1={}".format(geom['NAXIS1']))
        self.log.info("For reference: NAXIS2={}".format(geom['NAXIS2']))
        self.log.info("Received: overv={}, overh={}, preh={}".format(geom['overv'],
                                                                     geom['overh'],
                                                                     geom['preh']))

    def update_header(self):

        """Update FITSIO header object using the captured metadata"""
        for k, v in self.metadata.items():
            self.log.info("Updating header with {:8s} = {}".format(k, v))
            self.HDR.update_record(k, v, 'PRIMARY')

    def get_filenames(self):
        """
        Figure out the section of the telemetry from which we will extract
        'imageName' and define the output names based on that ID
        """
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.config.imageName_event)
        myData = self.Remote_get[name]()
        self.imageName = getattr(myData, self.config.imageName_event['value'])

        # Construct the hdr and fits filename
        self.filename_HDR = os.path.join(self.config.filepath, self.config.format_HDR.format(self.imageName))
        self.filename_FITS = self.config.format_FITS.format(self.imageName)

    def announce(self):
        """
        Broadcast the LFO Event for the HeaderService and optionally
        emulate it for the EFD
        """
        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR)
        bytesize = os.path.getsize(self.filename_HDR)
        self.log.info("Got MD5SUM: {}".format(md5value))
        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'byteSize': bytesize,
              'checkSum': md5value,
              'generator': self.config.hs_name,
              'mimeType': self.config.write_mode.upper(),
              'url': self.config.url_format.format(ip_address=self.ip_address,
                                                   port_number=self.config.port_number,
                                                   filename_HDR=os.path.basename(self.filename_HDR)),
              'id': self.imageName,
              'version': 1,
              'priority': 1,
              }

        self.evt_largeFileObjectAvailable.set_put(**kw)
        self.log.info(f"Sent {self.config.hs_name} largeFileObjectAvailable: {kw}")
        if self.config.send_efd_message:
            self.efd_controller.evt_largeFileObjectAvailable.set_put(**kw)
            self.log.info(f"Sent EFD largeFileObjectAvailable: {kw}")

    def write(self):
        """ Function to call to write the header"""
        self.HDR.write_header(self.filename_HDR)
        self.log.info("Wrote header to: {}".format(self.filename_HDR))

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
            name = get_channel_name(self.config.telemetry[k])
            param = self.config.telemetry[k]['value']
            # Access data payload only once
            if name not in self.myData:
                self.myData[name] = self.Remote_get[name]()
                # Only update metadata if self.myData is defined (not None)
            if self.myData[name] is None:
                self.log.warning(f"Cannot get keyword: {k} from topic: {name}")
            else:
                # In case of a long telemetry array we take the first element
                # TODO : if we happen to have many cases like this, we should
                # state which element of the array in the configuration file.
                payload = getattr(self.myData[name], param)
                if hasattr(payload, "__len__") and not isinstance(payload, str):
                    self.metadata[k] = payload[0]
                else:
                    self.metadata[k] = payload
                # Scale by `scale` if it was defined
                if 'scale' in self.config.telemetry[k]:
                    self.metadata[k] = self.metadata[k]*self.config.telemetry[k]['scale']
                self.log.debug(f"Extacted {k}={self.metadata[k]} from topic: {name}")

    def collect_from_HeaderService(self):

        """
        Collect and update custom meta-data generated or transformed by
        the HeaderService
        """

        # Reformat and calculate dates based on different timeStamps
        # NOTE: For now the timestamp are coming in UTC from Camera and are
        # transformed to TAI by the function hscalc.get_date()
        self.DATE = hscalc.get_date(self.metadata['DATE'])
        self.DATE_OBS = hscalc.get_date(self.metadata['DATE-OBS'])
        self.DATE_BEG = hscalc.get_date(self.metadata['DATE-BEG'])
        self.DATE_END = hscalc.get_date(self.metadata['DATE-END'])
        self.metadata['DATE'] = self.DATE.isot
        self.metadata['DATE-OBS'] = self.DATE_OBS.isot
        self.metadata['DATE-BEG'] = self.DATE_BEG.isot
        self.metadata['DATE-END'] = self.DATE_END.isot
        self.metadata['MJD'] = self.DATE.mjd
        self.metadata['MJD-OBS'] = self.DATE_OBS.mjd
        self.metadata['MJD-BEG'] = self.DATE_BEG.mjd
        self.metadata['MJD-END'] = self.DATE_END.mjd
        self.metadata['FILENAME'] = self.filename_FITS

        # The EL/AZ at start
        if set(('ELSTART', 'AZSTART')).issubset(self.metadata):
            self.log.info("Computing RA/DEC from ELSTART/AZSTART")
            ra, dec = hscalc.get_radec_from_altaz(alt=self.metadata['ELSTART'],
                                                  az=self.metadata['AZSTART'],
                                                  obstime=self.DATE_BEG,
                                                  lat=self.HDR.header['PRIMARY']['OBS-LAT'],
                                                  lon=self.HDR.header['PRIMARY']['OBS-LONG'],
                                                  height=self.HDR.header['PRIMARY']['OBS-ELEV'])
            self.metadata['RASTART'] = ra
            self.metadata['DECSTART'] = dec
        else:
            if 'ELSTART' not in self.metadata:
                self.log.info("No 'ELSTART' needed to compute RA/DEC START")
            if 'AZSTART' not in self.metadata:
                self.log.info("No 'AZSTART' needed to compute RA/DEC START")

        # The EL/AZ at end
        if set(('ELEND', 'AZEND')).issubset(self.metadata):
            self.log.info("Computing RA/DEC from ELEND/AZEND")
            ra, dec = hscalc.get_radec_from_altaz(alt=self.metadata['ELEND'],
                                                  az=self.metadata['AZEND'],
                                                  obstime=self.DATE_BEG,
                                                  lat=self.HDR.header['PRIMARY']['OBS-LAT'],
                                                  lon=self.HDR.header['PRIMARY']['OBS-LONG'],
                                                  height=self.HDR.header['PRIMARY']['OBS-ELEV'])
            self.metadata['RAEND'] = ra
            self.metadata['DECEND'] = dec
        else:
            if 'ELEND' not in self.metadata:
                self.log.info("No 'ELEND' needed to compute RA/DEC END")
            if 'AZEND' not in self.metadata:
                self.log.info("No 'AZEND' needed to compute RA/DEC END")

        if set(('RA', 'DEC', 'ROTPA', 'RADESYS')).issubset(self.metadata):
            self.log.info("Computing WCS-TAN from RA/DEC/ROTPA")
            wcs_TAN = self.HDR.CCDGEOM.wcs_TAN(self.metadata['RA'],
                                               self.metadata['DEC'],
                                               self.metadata['ROTPA'],
                                               self.metadata['RADESYS'])
            # Update the metadata
            self.metadata.update(wcs_TAN)
        else:
            if 'RA' not in self.metadata:
                self.log.info("No 'RA' needed to compute WCS")
            if 'DEC' not in self.metadata:
                self.log.info("No 'DEC' needed to compute WCS")
            if 'ROTPA' not in self.metadata:
                self.log.info("No 'ROTPA' needed to compute WCS")
            if 'RADESYS' not in self.metadata:
                self.log.info("No 'RADESYS' needed to compute WCS")


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

    valid_collection_events = frozenset(["start_collection_event", "end_collection_event"])

    channels = {}
    for key in telem:

        # Make sure telemetry as a valid collection event definition
        if telem[key]['collect_after_event'] not in valid_collection_events:
            raise ValueError(f"Wrong collection_event in telemetry definition for keyword:{key}")

        # Make the name of the channel unique by appending device
        c = {'device': telem[key]['device'],
             'topic': telem[key]['topic'],
             'Stype': telem[key]['Stype']}
        # Add scale if present in the definition -- although not used elsewhere
        if 'scale' in telem[key]:
            c['scale'] = telem[key]['scale']
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
