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
import HeaderService
import importlib


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

        # Define the callbacks for start/end
        self.define_evt_callbacks()

        # Load enum idl libraries
        self.load_enums_idl()

        # Define global lock to update dictionaries
        self.dlock = asyncio.Lock()

    async def close_tasks(self):
        """Close tasks on super and evt timeout"""
        await super().close_tasks()
        self.cancel_timeout_tasks()

    async def end_evt_timeout(self, imageName, timeout):
        """Timeout timer for end event telemetry callback"""
        await asyncio.sleep(timeout)
        self.log.info(f"{self.name_end} for {imageName} not seen in {timeout} [s]; giving up")
        # Send the timeout warning using the salobj log
        self.log.warning(f"Timeout while waiting for {self.name_end} Event from {imageName}")
        async with self.dlock:
            self.clean(imageName)

    def cancel_timeout_tasks(self):
        """Cancel the per-image timeout tasks"""
        for imageName in self.end_evt_timeout_task:
            self.end_evt_timeout_task[imageName].cancel()

    async def handle_summary_state(self):
        self.log.info(f"Current state is: {self.summary_state.name}")
        if self.summary_state != salobj.State.ENABLED:
            self.cancel_timeout_tasks()

    def define_evt_callbacks(self):
        """Set the callback functions based on configuration"""

        # Select the start_collection callback
        devname = get_channel_devname(self.config.start_collection_event)
        topic = self.config.start_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.start_collection_event_callback
        self.log.info(f"Defining callback for {devname} {topic}")

        # Select the end_collection callback
        devname = get_channel_devname(self.config.end_collection_event)
        topic = self.config.end_collection_event['topic']
        getattr(self.Remote[devname], f"evt_{topic}").callback = self.end_collection_event_callback
        self.log.info(f"Defining callback for {devname} {topic}")

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

    def get_tstand(self):
        """Figure the Test Stand in use"""
        # Check if definced in self.config or the environment
        if self.config.tstand:
            self.tstand = self.config.tstand
            self.log.info(f"Will use TSTAND: {self.tstand} in configurarion")
        elif 'TSTAND_HEADERSERVICE' in os.environ:
            self.tstand = os.environ['TSTAND_HEADERSERVICE']
            self.log.info(f"Will use TSTAND: {self.tstand} in from environment")
        else:
            # Try to auto-figure out from location
            self.log.warning("The TSTAND was not defined in config/environment")
            address = socket.getfqdn()
            if address.find('.ncsa.') >= 0:
                self.tstand = "NCSA"
                self.log.info(f"Will use auto-config tstand: {self.tstand}")
            else:
                self.tstand = None
                self.log.info("Unable to auto-config tstand -- will be left undefined")

    def get_ip(self):
        """Figure out the IP we will be using to broadcast"""

        # Check if definced in self.config or the environment
        if self.config.ip_address:
            self.ip_address = self.config.ip_address
            self.log.info(f"Will use IP: {self.ip_address} in config for web service")
        elif 'IP_HEADERSERVICE' in os.environ:
            self.ip_address = os.environ['IP_HEADERSERVICE']
            self.log.info(f"Will use IP: {self.ip_address} fron environment for web service")
        else:
            self.ip_address = socket.gethostbyname(socket.gethostname())
            self.log.info(f"Will use IP: {self.ip_address} auto-config for web service")

    def get_s3instance(self):
        """
        Figure the location where are running to define the s3instance
        in case it wasn't defined.
        """
        # Check if defined in self.config or the environment
        if self.config.s3instance:
            s3instance = self.config.s3instance
            self.log.info(f"Will use s3instance in config: {s3instance}")
            return s3instance
        elif 'S3INSTANCE' in os.environ:
            s3instance = os.environ['S3INSTANCE']
            self.log.info(f"Will use s3instance from environment: {s3instance}")
            return s3instance

        # Try to auto-figure out from location
        self.log.warning("The s3instance was not defined in config")
        address = socket.getfqdn()
        if address.find('.ncsa.') >= 0:
            s3instance = 'nts'
        elif address.find('tuc') >= 0:
            s3instance = 'tuc'
        elif address.find('.cp.') >= 0:
            s3instance = 'cp'
        else:
            s3instance = 'dummy'
        self.log.info(f"Will use auto-config s3instance: {s3instance}")
        return s3instance

    def define_s3bucket(self):
        """
        Get the s3instance and define the name for the
        s3 bucket using salobj

        To access the S3 server, the environment variables are set via:

        export S3_ENDPOINT_URL=http://lsst-nfs.ncsa.illinois.edu:9000
        export AWS_ACCESS_KEY_ID={access_key}
        export AWS_SECRET_ACCESS_KEY={secret_key}
        """

        s3instance = self.get_s3instance()
        self.s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(s3instance=s3instance)
        self.log.info(f"Will use Bucket name: {self.s3bucket_name}")

        # 2. Use AsyncS3Bucket to make bucket + S3 connection
        self.s3bucket = salobj.AsyncS3Bucket(name=self.s3bucket_name, domock=False)
        self.log.info(f"Connection established to: {self.s3bucket_name}")
        # We will re-use the connection made by salobj
        self.s3conn = self.s3bucket.service_resource
        self.log.info(f"Will use s3 endpoint_url: {self.s3conn.meta.client.meta.endpoint_url}")

        # 3. Make sure the bucket exists in the list of bucket names:
        bucket_names = [b.name for b in self.s3conn.buckets.all()]
        if self.s3bucket_name not in bucket_names:
            self.s3conn.create_bucket(Bucket=self.s3bucket_name)
            self.log.info(f"Created Bucket: {self.s3bucket_name}")
        else:
            self.log.info(f"Bucket Name: {self.s3bucket_name} already exists")

    def start_web_server(self, logfile, httpserver="http.server"):

        """
        Start a light web service to serve the header files to the EFD
        """

        # Get the hostname and IP address
        self.get_ip()

        # Change PYTHONUNBUFFERED to 1 to allow continuous writing.
        os.environ['PYTHONUNBUFFERED'] = '1'

        # Open the file handle
        weblog = open(logfile, 'a')
        weblog.flush()

        self.log.info(f"Will send web server logs to: {logfile}")
        # Get the system's python
        python_exe = sys.executable
        # Make sure there isn't another process running
        cmd = f"ps -ax | grep \"{httpserver} {self.config.port_number}\" | grep -v grep | awk '{{print $1}}'"
        self.log.info(f"Checking for webserver running: {cmd}")
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
        self.log.info(f"Running HeaderService version: {HeaderService.__version__}")

    def create_BaseCsc(self):
        """
        Create a BaseCsc for the the HeaderService. We initialize the
        State object that keeps track of the HS current state.  We use
        a start_state to set the initial state
        """

        self.version = HeaderService.__version__

        super().__init__(name=self.config.hs_name, index=self.config.hs_index,
                         initial_state=getattr(salobj.State, self.config.hs_initial_state))
        # Logging
        self.setup_logging()
        # Version information
        self.log.info(f"Starting the CSC with {self.config.hs_name}")
        self.log.info(f"Creating worker for: {self.config.hs_name}")
        self.log.info(f"Running salobj version: {salobj.__version__}")
        self.log.info(f"Starting in State:{self.summary_state.name}")

        # Set the CSC version using softwareVersions
        self.log.info(f"Setting softwareVersions Event with version: {HeaderService.__version__}")
        self.evt_softwareVersions.set(cscVersion=HeaderService.__version__)

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
        for channel_name, c in self.channels.items():
            devname = get_channel_devname(c)
            # Make sure we only create these once
            if devname not in self.devices:
                self.devices.append(devname)
                self.Remote[devname] = salobj.Remote(domain=self.domain,
                                                     name=c['device'],
                                                     index=c['device_index'])
                self.log.info(f"Created Remote for {devname}")
            # capture the evt.get() function for the channel
            if c['Stype'] == 'Event':
                self.Remote_get[channel_name] = getattr(self.Remote[devname], f"evt_{c['topic']}").get
                self.log.info(f"Storing Remote.evt_{c['topic']}.get() for {channel_name}")
            if c['Stype'] == 'Telemetry':
                self.Remote_get[channel_name] = getattr(self.Remote[devname], f"tel_{c['topic']}").get
                self.log.info(f"Storing Remote.tel_{c['topic']}.get() for {channel_name}")

        # Select the start_collection channel
        self.name_start = get_channel_name(self.config.start_collection_event)
        # Select the end_collection channel
        self.name_end = get_channel_name(self.config.end_collection_event)

    def load_enums_idl(self):
        """
        Load using importlib the idl libraries for the enumerated CSCs
        """
        # Get the list of enum enum_csc
        self.log.info("Extracting enum CSC's from telemetry dictionary")
        self.enum_csc = get_enum_cscs(self.config.telemetry)
        self.idl_lib = {}
        for csc in self.enum_csc:
            self.log.info(f"importing lsst.ts.idl.enums.{csc}")
            self.idl_lib[csc] = importlib.import_module("lsst.ts.idl.enums.{}".format(csc))

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

        # The user running the process
        self.USER = os.environ['USER']

        # Make sure that we have a place to put the files
        self.check_outdir(self.config.filepath)

        # Start the web server
        if self.config.lfa_mode == 's3':
            self.define_s3bucket()
        elif self.config.lfa_mode == 'http':
            self.start_web_server(self.config.weblogfile)

        # Get the TSTAND
        self.get_tstand()

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

            # Try to get the list of sensor from the Camera Configuration event
            try:
                self.vendor_names, self.sensors = self.read_camera_vendors()
                self.log.info("Extracted vendors/ccdnames from Camera Configuration")
            except Exception:
                # In the absense of a message from camera to provide the list
                # of sensors and vendors, we build the list using a function
                # in hutils
                self.log.warning("Cannot read camera vendor list from event")
                self.log.warning("Will use defaults from config file instead")
                self.sensors = hutils.build_sensor_list(self.config.instrument)
                self.vendor_names = self.config.vendor_names

            self.log.info(f"Will use vendors: {self.vendor_names}")
            self.log.info(f"Will use sensors:{self.sensors}")
            self.HDR[imageName] = hutils.HDRTEMPL(logger=self.log,
                                                  section=self.config.section,
                                                  instrument=self.config.instrument,
                                                  segname=self.config.segname,
                                                  vendor_names=self.vendor_names,
                                                  sensor_names=self.sensors,
                                                  write_mode=self.config.write_mode)
            self.HDR[imageName].load_templates()
            # Get the filenames and imageName from the start event payload.
            self.log.info(f"Defining filenames for: {imageName}")
            self.get_filenames(imageName)

            # Get the requested exposure time to estimate the total timeout
            try:
                timeout_camera = self.read_timeout_from_camera()
                self.log.info(f"Extracted timeout: {timeout_camera}[s] from Camera")
            except AttributeError:
                self.log.warning("Cannot extract timout from camera, will use EXPTIME instead")
                exptime_key = self.config.timeout_keyword
                self.log.info("Collecting key to set timeout as key %s + %s" %
                              (exptime_key, self.config.timeout_exptime))
                metadata_tmp = self.collect([exptime_key])
                timeout_camera = metadata_tmp[exptime_key]
                self.log.info(f"Extracted timeout: {timeout_camera}[s] from {exptime_key}")
            timeout = timeout_camera + self.config.timeout_exptime
            self.log.info(f"Setting timeout: {timeout_camera} + {self.config.timeout_exptime} [s]")
            self.log.info(f"Using timeout: {timeout} [s]")

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
            try:
                self.update_header_geometry(imageName)
            except Exception as e:
                self.log.warning("Failed call to update_header_geometry")
                self.log.warning(e)

            # Update header object with metadata dictionary
            self.update_header(imageName)
            # Write the header
            self.write(imageName)
            # Announce/upload LFO
            await self.announce(imageName)
            # Clean up
            self.clean(imageName)

        self.log.info(f"-------- Done: {imageName} -------------------")
        self.log.info("-------- Ready for next image -----")
        # Cancel timed out tasks
        self.cancel_timeout_tasks()

    def read_camera_vendors(self, sep=":"):
        """ Read the vendor/ccdLocation from camera event """
        name = get_channel_name(self.config.cameraConf_event)
        array_keys = self.config.cameraConf_event['array_keys']
        param = self.config.cameraConf_event['value']
        myData = self.Remote_get[name]()
        # exit in case we cannot get data from SAL
        if myData is None:
            self.log.warning("Cannot get myData from {}".format(name))
            return

        # 1 We get the keywords List from myData
        payload = getattr(myData, array_keys)
        ccdnames = hutils.split_esc(payload, sep)
        if len(ccdnames) <= 1:
            self.log.warning(f"List keys for {name} is <= 1")
            self.log.info(f"For {name}, extracted '{array_keys}': {ccdnames}")
        # 2 Get the actual list of vendor names
        payload = getattr(myData, param)
        vendor_names = hutils.split_esc(payload, sep)
        self.log.info("Successfully read vendors/ccdnames from Camera config event")
        return vendor_names, ccdnames

    def update_header_geometry(self, imageName):
        """ Update the image geometry Camera Event """

        # if config.imageParam_event is False, we skip
        if not self.config.imageParam_event:
            self.log.info("No imageParam_event, will not update_header_geometry")
            return

        # Image paramters
        self.log.info("Extracting CCD/Sensor Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.config.imageParam_event)
        array_keys = self.config.imageParam_event['array_keys']
        myData = self.Remote_get[name]()
        # exit in case we cannot get data from SAL
        if myData is None:
            self.log.warning("Cannot get geometry myData from {}".format(name))
            return

        # Obtain the geometry that we'll use for each segment.
        geom = hutils.get_image_size_from_imageReadoutParameters(myData, array_keys)

        # Update the geometry for the HDR object
        self.log.info(f"Updating header CCD geom for {imageName}")
        self.HDR[imageName].load_geometry(geom)
        self.log.info("Templates Updated")

    def read_timeout_from_camera(self):
        """Extract the timeout from Camera Event"""
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.config.timeout_event)
        myData = self.Remote_get[name]()
        param = self.config.timeout_event['value']
        device = self.config.timeout_event['device']
        if myData is None:
            self.log.warning("Cannot get timeout myData from {}".format(name))
            return
        timeout_camera = getattr(myData, param)
        self.log.info(f"Extracted timeout from {device}: {timeout_camera}")
        return timeout_camera

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

    async def announce(self, imageName):
        """
        Upload and broadcast the LFO Event for the HeaderService
        """

        # if S3 bucket, upload before announcing to get
        # the url that will be broadcast.
        # Upload header file and get key/url
        # key should be like:
        # CCHeaderService/header/2020/05/21/CCHeaderService_header_CC_O_20200521_000008.yaml
        if self.config.lfa_mode == 's3':
            key = self.s3bucket.make_key(
                salname=self.config.hs_name,
                salindexname=self.config.hs_index,
                other=imageName,
                generator='header',
                date=self.metadata[imageName]['DATE-OBS'],
                suffix=".yaml"
            )
            # In case we want to go back to an s3 url
            # url = f"s3://{self.s3bucket.name}/{key}"

            # The url for simple a wget/curl fetch
            # i.e. http://S3_ENDPOINT_URL/s3buket_name/key
            url = f"{self.s3conn.meta.client.meta.endpoint_url}/{self.s3bucket.name}/{key}"
            t0 = time.time()
            with open(self.filename_HDR[imageName], "rb") as f:
                await self.s3bucket.upload(fileobj=f, key=key)
            self.log.info(f"Header s3 upload time: {hutils.elapsed_time(t0)}")
            self.log.info(f"Will use s3 key: {key}")
            self.log.info(f"Will use s3 url: {url}")
        elif self.config.lfa_mode == 'http':
            url = self.config.url_format.format(
                ip_address=self.ip_address,
                port_number=self.config.port_number,
                filename_HDR=os.path.basename(self.filename_HDR[imageName]))
            self.log.info(f"Will use http url: {url}")
        else:
            self.log.error(f"lfa_mode: {self.config.lfa_mode} not supported")

        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR[imageName])
        bytesize = os.path.getsize(self.filename_HDR[imageName])
        self.log.info("Got MD5SUM: {}".format(md5value))

        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'byteSize': bytesize,
              'checkSum': md5value,
              'generator': self.config.hs_name,
              'mimeType': self.config.write_mode.upper(),
              'url': url,
              'id': imageName,
              'version': 1,
              }

        await self.evt_largeFileObjectAvailable.set_write(**kw)
        self.log.info(f"Sent {self.config.hs_name} largeFileObjectAvailable: {kw}")

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
        self.log.info("Creating per imageName dictionaries")
        self.end_evt_timeout_task = {}
        self.metadata = {}
        self.HDR = {}
        self.filename_FITS = {}
        self.filename_HDR = {}

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
                self.log.info(f"Checking expiration for {name}")
                if self.check_telemetry_expired(myData[name]):
                    self.log.warning(f"Expired telemetry for {name} -- will ignore")
                    myData[name] = None
            # Only update metadata if myData is defined (not None)
            if myData[name] is None:
                self.log.warning(f"Cannot get keyword: {keyword} from topic: {name}")
            else:
                try:
                    metadata[keyword] = self.extract_from_myData(keyword, myData[name])
                    self.log.debug(f"Extracted {keyword}: {metadata[keyword]}")
                    # Scale by `scale` if it was defined
                    if 'scale' in self.config.telemetry[keyword]:
                        metadata[keyword] = metadata[keyword]*self.config.telemetry[keyword]['scale']
                        self.log.info(f"Scaled key: {keyword} by: {self.config.telemetry[keyword]['scale']}")
                except KeyError:
                    self.log.warning(f"Cannot extract keyword: {keyword} from topic: {name}")
        return metadata

    def check_telemetry_expired(self, myData):
        """ Check is telemetry has expired using expiresAt parameter"""
        has_expired = False
        # Check if it has the expiresAt attribute
        if hasattr(myData, 'expiresAt'):
            expiresAt = getattr(myData, 'expiresAt')
            self.log.info(f"Found expiresAt: {expiresAt} in payload")
            timestamp_now = time.time()  # unix UTC time
            if timestamp_now > expiresAt:
                has_expired = True
        return has_expired

    def extract_from_myData(self, keyword, myData, sep=":"):

        param = self.config.telemetry[keyword]['value']
        payload = getattr(myData, param)

        # Case 1 -- we want just one value per key (scalar)
        if 'array' not in self.config.telemetry[keyword]:
            self.log.debug(f"{keyword} is a scalar")
            extracted_payload = payload
        # Case 2 -- array of values per sensor
        elif self.config.telemetry[keyword]['array'] == 'CCD_array':
            self.log.debug(f"{keyword} is an array: CCD_array")
            ccdnames = self.get_array_keys(keyword, myData, sep)
            # When ATCamera sends (via SAL/DDS) and array with just one element
            # this is actually not send as a list/array, but as scalar instead.
            # Therefore, if expecting and list/array and length is (1), then we
            # need to recast SAL payload as a list.
            if len(ccdnames) == 1 and not isinstance(payload, list):
                payload = [payload]
                self.log.warning(f"Recasting payload to a list for {keyword}:{payload}")
            extracted_payload = dict(zip(ccdnames, payload))
        elif self.config.telemetry[keyword]['array'] == 'CCD_array_str':
            self.log.debug(f"{keyword} is string array: CCD_array_str")
            ccdnames = self.get_array_keys(keyword, myData, sep)
            # Split the payload into an array of strings
            extracted_payload = dict(zip(ccdnames, hutils.split_esc(payload, sep)))
        elif self.config.telemetry[keyword]['array'] == 'indexed_array':
            self.log.debug(f"{keyword} is an array: indexed_array")
            index = self.config.telemetry[keyword]['array_index']
            # Extract the requested index
            extracted_payload = payload[index]
        elif self.config.telemetry[keyword]['array'] == 'keyed_array':
            self.log.debug(f"{keyword} is an array: keyed_array")
            keywords = self.get_array_keys(keyword, myData, sep)
            key = self.config.telemetry[keyword]['array_keyname']
            # Extract only the requested key from the dictionary
            extracted_payload = dict(zip(keywords, hutils.split_esc(payload, sep)))[key]
        # Case 3 -- enumeration using idl libraries
        elif self.config.telemetry[keyword]['array'] == 'enum':
            device = self.config.telemetry[keyword]['device']
            array_name = self.config.telemetry[keyword]['array_name']
            extracted_payload = getattr(self.idl_lib[device], array_name)(payload).name
        # If some kind of array take first element
        elif hasattr(payload, "__len__") and not isinstance(payload, str):
            self.log.debug(f"{keyword} is just an array")
            extracted_payload = payload[0]
        else:
            self.log.debug(f"Undefined type for {keyword}")
            extracted_payload = None
        return extracted_payload

    def get_array_keys(self, keyword, myData, sep=":"):
        """
        Function to extract a list of keywords for the ':'-separated string
        published by Camera
        """
        array_keys = self.config.telemetry[keyword]['array_keys']
        payload = getattr(myData, array_keys)
        # Make sure we get back something
        if payload is None:
            self.log.warning(f"Cannot get list of keys for: {keyword}")
            keywords_list = None
        else:
            # we extract them using the separator (i.e. ':')
            keywords_list = hutils.split_esc(payload, sep)
            if len(keywords_list) <= 1:
                self.log.warning(f"List keys for {keyword} is <= 1")
            self.log.info(f"For {keyword}, extracted '{array_keys}': {keywords_list}")
        return keywords_list

    def collect_from_HeaderService(self, imageName):

        """
        Collect and update custom meta-data generated or transformed by
        the HeaderService
        """
        # Simplify code with shortcuts for imageName
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
        if self.tstand:
            metadata['TSTAND'] = self.tstand

        # If not LATISS stop here
        if self.config.instrument != 'LATISS':
            # Update the imageName metadata with new dict
            self.metadata[imageName].update(metadata)
            return

        # ---------------------------------------------------------------------
        # This functions will only be used for LATISS

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
    # Assume index=0 if not defined
    if 'device_index' not in c:
        c['device_index'] = 0
    return '{}_{}_{}'.format(c['device'], c['device_index'], c['topic'])


def get_channel_device(c):
    """ Standard formatting for the device name of a channel across modules"""
    return c['device']


def get_channel_devname(c):
    """ Standard formatting for the 'devname' of a channel across modules"""
    return "{}_{}".format(c['device'], c['device_index'])


def get_enum_cscs(telem):
    """
    Get only the enumerated devices described
    in the telemetry section of the config
    """
    enum_cscs = []
    for key in telem:
        if 'array' in telem[key] and telem[key]['array'] == 'enum':
            if telem[key]['device'] not in enum_cscs:
                enum_cscs.append(telem[key]['device'])
    return enum_cscs


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
        # Add array qualifier -- REVISE or replace by array
        if 'type' not in telem[key]:
            telem[key]['type'] = 'scalar'
        # Add default index=0 if undefined
        if 'device_index' not in telem[key]:
            telem[key]['device_index'] = 0
        name = get_channel_name(telem[key])
        # Make sure we don't create extra channels
        if name not in channels.keys():
            channels[name] = telem[key]

    # We also need to make sure that we subscribe to the start/end
    # collection Events in case these were not contained by the
    if start_collection_event:
        # Shortcut to variable c, note that when we update c
        # we also update the end_collection_event dictionary
        c = start_collection_event
        # Assume index=0 if not defined
        if 'device_index' not in c:
            c['device_index'] = 0
        name = get_channel_name(c)
        if name not in channels.keys():
            c['Stype'] = 'Event'
            channels[name] = c

    if end_collection_event:
        # Shortcut to variable c, note that when we update c
        # we also update the end_collection_event dictionary
        c = end_collection_event
        # Assume index=0 if not defined
        if 'device_index' not in c:
            c['device_index'] = 0
        name = get_channel_name(c)
        if name not in list(channels.keys()):
            c['Stype'] = 'Event'
            channels[name] = c

    # The imageParam event
    if imageParam_event:
        c = imageParam_event
        # Assume index=0 if not defined
        if 'device_index' not in c:
            c['device_index'] = 0
        name = get_channel_name(c)
        if name not in channels.keys():
            c['Stype'] = 'Event'
            channels[name] = c

    return channels
