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

        # Define global lock to update dictionaries
        self.dlock = asyncio.Lock()

    async def close_tasks(self):
        """Close tasks on super and evt timeout"""
        await super().close_tasks()
        # Loop over all task and cancel all of them
        for imageName in self.end_evt_timeout_task:
            self.end_evt_timeout_task[imageName].cancel()

    async def end_evt_timeout(self, imageName, timeout):
        """Timeout timer for end event telemetry callback"""
        await asyncio.sleep(timeout)
        self.log.info(f"{self.name_end} for {imageName} not seen in {timeout} [s]; giving up")
        # Send the timeout warning using the salobj log
        self.log.warning(f"Timeout while waiting for {self.name_end} Event from {imageName}")
        async with self.dlock:
            self.clean(imageName)

    def report_summary_state(self):
        """Call to report_summary_state and LOGGER"""
        super().report_summary_state()
        self.log.info(f"Current state is: {self.summary_state.name}")
        if self.summary_state != salobj.State.ENABLED:
            # Loop over all task and cancel all of them
            for imageName in self.end_evt_timeout_task:
                self.end_evt_timeout_task[imageName].cancel()

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

    def start_collection_event_callback(self, myData):
        """ The callback function for the START collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            self.log.info(f"Received: {self.name_start} Event")
            self.log.info(f"Ignoring as current state is {self.summary_state.name}")
            return

        sys.stdout.flush()
        self.log.info(f"---------- Received: {self.name_start} Event -----------------")

        # Extract the key to match start/end events
        imageName = self.get_imageName(myData)
        self.log.info(f"Starting callback for imageName: {imageName}")

        # Update header object and metadata dictionaries with lock and wait
        asyncio.ensure_future(self.complete_tasks_START(imageName))

    def end_collection_event_callback(self, myData):
        """ The callback function for the END collection event"""

        # If not in ENABLED mode we do nothing
        if self.summary_state != salobj.State.ENABLED:
            self.log.info(f"Received: {self.name_end} Event")
            self.log.info(f"Ignoring as current state is {self.summary_state.name}")
            return

        # Extract the key to match start/end events
        imageName = self.get_imageName(myData)

        # Check for rogue end collection events
        self.log.info(f"Received: {self.name_end} Event for {imageName}")
        if imageName not in self.end_evt_timeout_task:
            self.log.warning(f"Received orphan {self.name_end} Event without a timeout task")
            self.log.warning(f"{self.name_end} will be ignored for: {imageName}")
            self.log.info(f"Current State is {self.summary_state.name}")
            return

        # Cancel/stop the timeout task because we got the END callback
        self.end_evt_timeout_task[imageName].cancel()

        # Final collection using asyncio lock, will call functions that
        # take care of updating data structures. We also write the header file.
        asyncio.ensure_future(self.complete_tasks_END(imageName))

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

        # Create dictionaries keyed to imageName
        self.create_dicts()

    async def complete_tasks_START(self, imageName):
        """
        Update data objects at START with asyncio lock
        and complete all tasks started with START event.
        """
        async with self.dlock:

            # Collect metadata at start of integration and
            # load it on the self.metadata dictionary
            self.log.info(f"Collecting Metadata START : {self.name_start} Event")
            self.metadata[imageName] = self.collect(self.keywords_start)

            # Create the HDR object to be populated with the collected metadata
            # when loading the templates we get a HDR.header object
            self.log.info(f"Creating header object for : {imageName}")
            # In the absense of a message from camera with the list of sensors
            # we build the list using a function in hutils
            self.sensors = hutils.build_sensor_list(self.config.instrument)
            self.HDR[imageName] = hutils.HDRTEMPL(logger=self.log,
                                                  section=self.config.section,
                                                  instrument=self.config.instrument,
                                                  vendor_names=self.config.vendor_names,
                                                  sensor_names=self.sensors,
                                                  write_mode=self.config.write_mode)
            self.HDR[imageName].load_templates()
            # Get the filenames and imageName from the start event payload.
            self.log.info(f"Defining filenames for: {imageName}")
            self.get_filenames(imageName)

            # Get the requested exposure time to estimate the total timeout
            exptime_key = self.config.timeout_keyword
            self.log.info("Collecting key to set timeout as key %s + %s" %
                          (exptime_key, self.config.timeout_exptime))
            metadata_tmp = self.collect([exptime_key])
            timeout = metadata_tmp[exptime_key] + self.config.timeout_exptime
            self.log.info(f"Using timeout: %s [s]" % timeout)

            # Create timeout_task per imageName
            self.end_evt_timeout_task[imageName] = asyncio.ensure_future(self.end_evt_timeout(imageName,
                                                                                              timeout))
            self.log.info(f"Waiting {timeout} [s] for {self.name_end} Event for: {imageName}")

    async def complete_tasks_END(self, imageName):
        """
        Update data objects at END with asyncio lock
        and complete all tasks started with END event
        """
        async with self.dlock:

            # Collect metadata at end of integration
            self.log.info(f"Collecting Metadata END: {self.name_end} Event")
            self.metadata[imageName].update(self.collect(self.keywords_end))
            # Collect metadata created by the HeaderService
            self.log.info("Collecting Metadata from HeaderService")
            # Update header with information from HS
            self.collect_from_HeaderService(imageName)

            # Update header using the information from the camera geometry
            self.log.info("Updating Header with Camera information")
            self.update_header_geometry(imageName)
            # Update header object with metadata dictionary
            self.update_header(imageName)
            # Write the header
            self.write(imageName)
            # Announce creation event
            self.announce(imageName)
            # Clean up
            self.clean(imageName)

        self.log.info(f"-------- Done: {imageName} -------------------")
        self.log.info(f"-------- Ready for next image -----")
        # Report and print the state
        self.report_summary_state()

    def update_header_geometry(self, imageName):
        """ Update the image geometry Camera Event """
        # Image paramters
        self.log.info("Extracting CCD/Sensor Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.config.imageParam_event)
        myData = self.Remote_get[name]()
        # exit in case we cannot get data from SAL
        if myData is None:
            self.log.warning("Cannot get geometry myData from {}".format(name))
            return

        # in case we want to get NAXIS1/NAXIS2, etc.
        geom = hutils.get_image_size_from_imageReadoutParameters(myData)

        # Update the geometry for the HDR object
        self.log.info(f"Updating header CCD geom for {imageName}")
        self.HDR[imageName].load_geometry(geom)
        self.log.info("Templates Updated")

    def update_header(self, imageName):

        """Update FITSIO header object using the captured metadata"""
        for keyword, value in self.metadata[imageName].items():

            # Check if dictionary with per-sensor values
            if isinstance(value, dict):
                for sensor in value.keys():
                    extname = self.HDR[imageName].get_primary_extname(sensor)
                    self.HDR[imageName].update_record(keyword, value[sensor], extname)
                    self.log.info(f"Updating header[{extname}] with {keyword:8s} = {value[sensor]}")
            # Otherwise we put it into the PRIMARY
            else:
                extname = 'PRIMARY'
                self.HDR[imageName].update_record(keyword, value, extname)
                self.log.info(f"Updating header[{extname}] with {keyword:8s} = {value}")

    def get_imageName(self, myData):
        """
        Method to extract the key to match start/end events
        (i.e: imageName) uniformly across the class
        """
        imageName = getattr(myData, self.config.imageName_event['value'])
        return imageName

    def get_filenames(self, imageName):
        """
        Figure out the section of the telemetry from which we will extract
        'imageName' and define the output names based on that ID
        """
        # Construct the hdr and fits filename
        self.filename_FITS[imageName] = self.config.format_FITS.format(imageName)
        self.filename_HDR[imageName] = os.path.join(self.config.filepath,
                                                    self.config.format_HDR.format(imageName))

    def announce(self, imageName):
        """
        Broadcast the LFO Event for the HeaderService and optionally
        emulate it for the EFD
        """
        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR[imageName])
        bytesize = os.path.getsize(self.filename_HDR[imageName])
        self.log.info("Got MD5SUM: {}".format(md5value))
        url = self.config.url_format.format(ip_address=self.ip_address,
                                            port_number=self.config.port_number,
                                            filename_HDR=os.path.basename(self.filename_HDR[imageName]))
        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'byteSize': bytesize,
              'checkSum': md5value,
              'generator': self.config.hs_name,
              'mimeType': self.config.write_mode.upper(),
              'url': url,
              'id': imageName,
              'version': 1,
              'priority': 1,
              }

        self.evt_largeFileObjectAvailable.set_put(**kw)
        self.log.info(f"Sent {self.config.hs_name} largeFileObjectAvailable: {kw}")
        if self.config.send_efd_message:
            self.efd_controller.evt_largeFileObjectAvailable.set_put(**kw)
            self.log.info(f"Sent EFD largeFileObjectAvailable: {kw}")

    def write(self, imageName):
        """ Function to call to write the header"""
        self.HDR[imageName].write_header(self.filename_HDR[imageName])
        self.log.info("Wrote header to: {}".format(self.filename_HDR[imageName]))

    def clean(self, imageName):
        """ Clean up imageName data structures"""
        self.log.info(f"Cleaning data for: {imageName}")
        del self.end_evt_timeout_task[imageName]
        del self.metadata[imageName]
        del self.HDR[imageName]
        del self.filename_HDR[imageName]
        del self.filename_FITS[imageName]

    def create_dicts(self):
        """
        Create the dictionaries holding per image information, such as:
        timeout tasks, metadata and headers
        """
        self.log.info(f"Creating per imageName dictionaries")
        self.end_evt_timeout_task = {}
        self.metadata = {}
        self.HDR = {}
        self.filename_FITS = {}
        self.filename_HDR = {}

    def collect_old(self, keys):
        """ Collect meta-data from the telemetry-connected channels
        and store it in the 'metadata' dictionary"""

        # Define myData and metadata dictionaries
        # myData: holds the payload from Telem/Events
        # metadata: holds the metadata to be inserted into the Header object
        myData = {}
        metadata = {}
        for k in keys:
            name = get_channel_name(self.config.telemetry[k])
            param = self.config.telemetry[k]['value']
            # Access data payload only once
            if name not in myData:
                myData[name] = self.Remote_get[name]()
            # Only update metadata if myData is defined (not None)
            if myData[name] is None:
                self.log.warning(f"Cannot get keyword: {k} from topic: {name}")
            else:
                # In case of a long telemetry array we take the first element
                # TODO : if we happen to have many cases like this, we should
                # state which element of the array in the configuration file.
                payload = getattr(myData[name], param)
                if hasattr(payload, "__len__") and not isinstance(payload, str):
                    metadata[k] = payload[0]
                else:
                    metadata[k] = payload
                # Scale by `scale` if it was defined
                if 'scale' in self.config.telemetry[k]:
                    metadata[k] = metadata[k]*self.config.telemetry[k]['scale']
                self.log.debug(f"Extacted {k}={metadata[k]} from topic: {name}")
        return metadata

    def collect(self, keys):
        """ Collect meta-data from the telemetry-connected channels
        and store it in the 'metadata' dictionary"""

        # Define myData and metadata dictionaries
        # myData: holds the payload from Telem/Events
        # metadata: holds the metadata to be inserted into the Header object
        myData = {}
        metadata = {}
        for keyword in keys:
            name = get_channel_name(self.config.telemetry[keyword])
            # Access data payload only once
            if name not in myData:
                myData[name] = self.Remote_get[name]()
            # Only update metadata if myData is defined (not None)
            if myData[name] is None:
                self.log.warning(f"Cannot get keyword: {keyword} from topic: {name}")
            else:
                metadata[keyword] = self.extract_from_myData(keyword, myData[name])
        return metadata

    def extract_from_myData(self, keyword, myData):

        param = self.config.telemetry[keyword]['value']
        payload = getattr(myData, param)

        # Case 1 -- we want just one value per key (scalar)
        if 'array' not in self.config.telemetry[keyword]:
            self.log.debug(f"{keyword} is a scalar")
            extracted_payload = payload
        # Case 2 -- array of values per sensor
        elif self.config.telemetry[keyword]['array'] == 'CCD_array':
            self.log.debug(f"{keyword} is an array")
            ccdnames = self.get_CCD_keywords(keyword, myData)
            self.log.info(f"For {keyword} extracted ccdnames: {ccdnames}")
            extracted_payload = dict(zip(ccdnames, payload))
        # If some kind of array, take first element
        elif hasattr(payload, "__len__") and not isinstance(payload, str):
            extracted_payload = payload[0]
        else:
            self.log.debug(f"Undefined type for {keyword}")
            extracted_payload = None
        return extracted_payload

    def get_CCD_keywords(self, keyword, myData, sep=":"):
        """
        Function to extract a list of CCDs/Sensors for the ':'
        separated string published by Camera
        """
        array_key = self.config.telemetry[keyword]['array_key']
        payload = getattr(myData, array_key)
        # Make sure we get back something
        if payload is None:
            self.log.warning(f"Cannot get list of CCD keys for {keyword}")
            ccd_keywords = None
        else:
            # we extract them using separator
            ccd_keywords = payload.split(sep)
            if len(ccd_keywords) <= 1:
                self.log.warning(f"List CCD keys for {keyword} is <= 1")
        return ccd_keywords

    def collect_from_HeaderService(self, imageName):

        """
        Collect and update custom meta-data generated or transformed by
        the HeaderService
        """
        # Simplify code with shortcuts for imageName
        header = self.HDR[imageName].header
        metadata = self.metadata[imageName]

        # Reformat and calculate dates based on different timeStamps
        # NOTE: For now the timestamp are coming in UTC from Camera and are
        # transformed to TAI by the function hscalc.get_date()
        # Store the creation date of the header file -- i.e. now!!
        DATE = hscalc.get_date(time.time())
        DATE_OBS = hscalc.get_date(metadata['DATE-OBS'])
        DATE_BEG = hscalc.get_date(metadata['DATE-BEG'])
        DATE_END = hscalc.get_date(metadata['DATE-END'])
        metadata['DATE'] = DATE.isot
        metadata['DATE-OBS'] = DATE_OBS.isot
        metadata['DATE-BEG'] = DATE_BEG.isot
        metadata['DATE-END'] = DATE_END.isot
        # Need to force MJD dates to floats for yaml header
        metadata['MJD'] = float(DATE.mjd)
        metadata['MJD-OBS'] = float(DATE_OBS.mjd)
        metadata['MJD-BEG'] = float(DATE_BEG.mjd)
        metadata['MJD-END'] = float(DATE_END.mjd)
        metadata['FILENAME'] = self.filename_FITS[imageName]

        # If not LATISS stop here
        if self.config.instrument != 'LATISS':
            # Update the imageName metadata with new dict
            self.metadata[imageName].update(metadata)
            return

        # ---------------------------------------------------------------------
        # This functions will only be usef for LATISS
        # The EL/AZ at start
        if set(('ELSTART', 'AZSTART')).issubset(metadata):
            self.log.info("Computing RA/DEC from ELSTART/AZSTART")
            ra, dec = hscalc.get_radec_from_altaz(alt=metadata['ELSTART'],
                                                  az=metadata['AZSTART'],
                                                  obstime=DATE_BEG,
                                                  lat=header['PRIMARY']['OBS-LAT'],
                                                  lon=header['PRIMARY']['OBS-LONG'],
                                                  height=header['PRIMARY']['OBS-ELEV'])
            metadata['RASTART'] = ra
            metadata['DECSTART'] = dec
        else:
            if 'ELSTART' not in metadata:
                self.log.info("No 'ELSTART' needed to compute RA/DEC START")
            if 'AZSTART' not in metadata:
                self.log.info("No 'AZSTART' needed to compute RA/DEC START")

        # The EL/AZ at end
        if set(('ELEND', 'AZEND')).issubset(metadata):
            self.log.info("Computing RA/DEC from ELEND/AZEND")
            ra, dec = hscalc.get_radec_from_altaz(alt=metadata['ELEND'],
                                                  az=metadata['AZEND'],
                                                  obstime=DATE_END,
                                                  lat=header['PRIMARY']['OBS-LAT'],
                                                  lon=header['PRIMARY']['OBS-LONG'],
                                                  height=header['PRIMARY']['OBS-ELEV'])
            metadata['RAEND'] = ra
            metadata['DECEND'] = dec
        else:
            if 'ELEND' not in metadata:
                self.log.info("No 'ELEND' needed to compute RA/DEC END")
            if 'AZEND' not in metadata:
                self.log.info("No 'AZEND' needed to compute RA/DEC END")

        if set(('RA', 'DEC', 'ROTPA', 'RADESYS')).issubset(metadata):
            sensor = self.sensors[0]
            self.log.info(f"Computing WCS-TAN from RA/DEC/ROTPA for {sensor}")
            wcs_TAN = self.HDR[imageName].CCDInfo[sensor].wcs_TAN(metadata['RA'],
                                                                  metadata['DEC'],
                                                                  metadata['ROTPA'],
                                                                  metadata['RADESYS'])
            # Update the metadata
            metadata.update(wcs_TAN)
        else:
            if 'RA' not in metadata:
                self.log.info("No 'RA' needed to compute WCS")
            if 'DEC' not in metadata:
                self.log.info("No 'DEC' needed to compute WCS")
            if 'ROTPA' not in metadata:
                self.log.info("No 'ROTPA' needed to compute WCS")
            if 'RADESYS' not in metadata:
                self.log.info("No 'RADESYS' needed to compute WCS")
        # ---------------------------------------------------------------------

        # Update the imageName metadata with new dict
        self.metadata[imageName].update(metadata)


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
        # Add array qualifier
        if 'type' in telem[key]:
            c['type'] = telem[key]['type']
        else:
            c['type'] = 'scalar'

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
