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

# Create a logger for all functions
LOGGER = hutils.create_logger(level=logging.NOTSET,name='HEADERSERVICE')

class HSworker:

    """ A Class to run and manage the Header Service"""

    def __init__(self,**keys):

        self.keys = keys
        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in list(keys.items()):
            setattr(self, k, v)
            #print k,v

        # Inititalize the State class to keep track of the system's state
        self.init_State()

        # Extract the unique channel by topic/device
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.get_channels()

        # Get the hostname and IP address
        self.ip_address = socket.gethostbyname(socket.gethostname())
        LOGGER.info("Will use IP: {} for broadcasting".format(self.ip_address))

        # The user running the process
        self.USER = os.environ['USER']
        
    def init_State(self,start_state=None):
        """
        Initialize the State object that keeps track of the HS current state.
        We use a start_state to set the initial state
        """
        if start_state:
            self.start_state=start_state

        self.State = salpytools.DeviceState(default_state=self.start_state)
        self.State.send_logEvent('SummaryState')
        # Create threads for the controller we want to listen to
        self.tControl = {}
        for ctrl_name in _CONTROLER_list:
            self.tControl[ctrl_name] = salpytools.DDSController(ctrl_name,State=self.State)
            self.tControl[ctrl_name].start()

        # Set the message for 'SettingApplied' here, we should want to control these from here in the future
        self.State.settings = "HeaderService version:{}\nts_xml version:{}".format(HeaderService.version,self.ts_xml)

    def get_channels(self):
        """Extract the unique channel by topic/device"""
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.channels = extract_telemetry_channels(self.telemetry,
                                                   start_collection_event=self.start_collection_event,
                                                   end_collection_event=self.end_collection_event,
                                                   imageParam_event=self.imageParam_event)

        # Now separate the keys to collect at the 'end' from the ones at 'start'
        t = self.telemetry # Short-cut
        self.keywords_start = [k for k in t.keys() if t[k]['collect_after_event'] == 'start_collection_event']
        self.keywords_end   = [k for k in t.keys() if t[k]['collect_after_event'] == 'end_collection_event']

    def make_connections(self,start=True):
        """
        Make connection to channels and start the threads as defined
        by the meta-data, and make additional connection for Start/End
        of telemetry Events
        """
        # The dict containing all of the threads and connections
        self.SALconn = {}
        for name, c in self.channels.items():
            self.SALconn[name] = salpytools.DDSSubcriber(c['device'],c['topic'],Stype=c['Stype'])
            if start: self.SALconn[name].start()

        # Select the start_collection channel
        self.name_start = get_channel_name(self.start_collection_event)
        self.StartInt = self.SALconn[self.name_start]

        # Select the end_collection channel
        self.name_end = get_channel_name(self.end_collection_event)
        self.EndTelem = self.SALconn[self.name_end]

    def check_outdir(self):
        """ Make sure that we have a place to put the files"""
        if not os.path.exists(self.filepath):
            os.makedirs(self.filepath)
            LOGGER.info("Created dirname:{}".format(self.filepath))

    def run(self,**keys):

        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in list(keys.items()):            
            setattr(self, k, v)
            #print k,v

        # Subscribe to each of the channels we want to susbcribe and store
        # the connection in a dictionary
        LOGGER.info("*** Starting Connections for Meta-data ***")
        self.make_connections()

        # Make sure that we have a place to put the files
        self.check_outdir()

        # Start the web server
        #self.filepath_www = os.path.split(self.filepath)[0]
        #self.filepath_www = os.path.split(self.filepath)[0]
        hutils.start_web_server(self.filepath,port_number=self.port_number)

        # And the object to send DMHS messages
        # TODO -- Make this configurable too
        self.dmhs = salpytools.DDSSend("atHeaderService")
        if self.send_efd_message:
            self.efd  = salpytools.DDSSend('efd')
            
        # Load up the header template
        self.HDR = HeaderService.HDRTEMPL_ATSCam(vendor=self.vendor)
        self.HDR.load_templates()

        # Go into the eternal loop
        self.run_loop()

    def update_header_geometry(self):
        
        # Image paramters
        LOGGER.info("Extracting Image Parameters")
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageParam_event)
        myData = self.SALconn[name].getCurrent()
        # in case we want to get NAXIS1/NAXIS2, etc.
        geom = hutils.get_image_size_from_imageReadoutParameters(myData)
        # We update the headers and reload them
        self.HDR.CCDGEOM.overh = geom['overh']
        self.HDR.CCDGEOM.overv = geom['overv']
        self.HDR.CCDGEOM.preh  = geom['preh']
        LOGGER.info("Reloadling templates")
        self.HDR.load_templates()
        LOGGER.info("For reference: NAXIS1={}".format(geom['NAXIS1']))
        LOGGER.info("For reference: NAXIS2={}".format(geom['NAXIS2']))
        LOGGER.info("Received: overv={}, overh={}, preh={}".format(geom['overv'], geom['overh'], geom['preh']))

    def update_header(self):

        """Update FITSIO header object using the captured metadata"""
        for k,v in self.metadata.items():
            LOGGER.debug("Updating header with {:8s} = {}".format(k,v))
            self.HDR.update_record(k,v, 'PRIMARY')

    def get_filenames(self):
        """
        Extract from which section of telemetry we will extract
        'imageName' and define the output names based on that ID
        """
        # Extract from telemetry and identify the channel
        name = get_channel_name(self.imageName_event)
        myData = self.SALconn[name].getCurrent()
        self.imageName = getattr(myData,self.imageName_event['value'])

        # Construct the hdr and fits filename
        self.filename_HDR = os.path.join(self.filepath,self.format_HDR.format(self.imageName))
        self.filename_FITS = self.format_FITS.format(self.imageName)

    def run_loop(self):

        """Run the loop that waits for a newEvent"""
        loop_n = 0
        while True:

            if self.State.current_state!='ENABLE':
                sys.stdout.flush()
                sys.stdout.write("Current State is {} [{}]".format(self.State.current_state,next(spinner)))
                sys.stdout.write('\r') 

            elif self.StartInt.newEvent:

                # Build the DATE of observation immediatly -- we will access it later
                self.DATE_OBS = hutils.get_date_utc()

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
                LOGGER.info("Current State is {} -- waiting for {} event".format(self.State.current_state,self.name_end))
                self.EndTelem.waitEvent()
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
            else:
                sys.stdout.flush()
                sys.stdout.write("Current State is {} -- waiting for {} Event...[{}]".format(self.State.current_state,self.name_start,next(spinner)))
                sys.stdout.write('\r')
                time.sleep(self.tsleep)

            time.sleep(self.tsleep)
            loop_n +=1    

    def announce(self):
        # Get the md5 for the header file
        md5value = hutils.md5Checksum(self.filename_HDR) #,blocksize=1024*512):
        bytesize = os.path.getsize(self.filename_HDR)
        LOGGER.info("Got MD5SUM: {}".format(md5value))
        # Now we publish filename and MD5
        # Build the kwargs
        kw = {'Byte_Size':bytesize,
              'Checksum':md5value,
              'Generator':'atHeaderService',
              'Mime':'FITS',
              'URL': self.url_format.format(ip_address=self.ip_address,
                                            port_number=self.port_number,
                                            filename_HDR=os.path.basename(self.filename_HDR)),
              'ID': self.imageName,
              'Version': 1,
              'priority':1,
              }
        self.dmhs.send_Event('LargeFileObjectAvailable',**kw)
        LOGGER.info("Sent LargeFileObjectAvailable: {}".format(kw))
        if self.send_efd_message:
            self.efd.send_Event('LargeFileObjectAvailable',**kw)
            
    def write(self):
        """ Function to call to write the header"""
        self.HDR.write_header(self.filename_HDR, newline=False)
        LOGGER.info("Wrote header to: {}".format(self.filename_HDR))

    def clean(self):
        self.myData = {}
        self.metadata = {}

    def collect(self,keys):
        """ Collect meta-data from the telemetry-connected channels
        and store it in the 'metadata' dictionary"""
        for k in keys:
            name = get_channel_name(self.telemetry[k])
            param = self.telemetry[k]['value']
            # Only access data payload once
            #if name not in self.myData.keys():
            if name not in self.myData:
                self.myData[name] = self.SALconn[name].getCurrent()
            self.metadata[k] = getattr(self.myData[name],param)

    def collect_from_HeaderService(self):
        """Collect custom meta-data generated by the HeaderService"""
        self.metadata['FILENAME'] = self.filename_FITS
        self.metadata['DATE-OBS'] = self.DATE_OBS.fits
        self.metadata['MJD-OBS'] = self.DATE_OBS.mjd
        self.metadata['DATE'] = self.DATE_HDR.fits
        self.metadata['MJD']  = self.DATE_HDR.mjd
        self.metadata['OBS-NITE'] = hutils.get_obsnite()


def get_channel_name(c):
    """ Standard formatting for the name of a channel across modules"""
    return '{}_{}'.format(c['device'],c['topic'])

def extract_telemetry_channels(telem,start_collection_event=None,
                               end_collection_event=None,
                               imageParam_event=None):
    """
    Get the unique telemetry channels from telemetry dictionary to
    define the topics that we need to subscribe to
    """
    channels = {}
    for key in telem:
        # Make the name of the channel unique by appending device
        c = {'device':telem[key]['device'],    
             'topic': telem[key]['topic'],
             'Stype' :telem[key]['Stype']}
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

def subscribe_to_channels(channels,start=True):
    """ make connection to channels and start the threads"""
    SAL_connection = {}
    for name, c in channels.items():
        SAL_connection[name] = salpytools.DDSSubcriber(c['device'],c['topic'],Stype=c['Stype'])
        if start: SAL_connection[name].start()

    return SAL_connection

    
