import salpytools
import HeaderService.hutils as hutils
import logging

# the controller we want to listen to
# TODO: This could be a configurable list
_CONTROLER_list = ['enterControl',
                   'exitControl',
                   'start',
                   'standby',
                   'enable',
                   'disable']


# Create a logger for all functions
LOGGER = hutils.create_logger(level=logging.NOTSET,name='HEADERSERVICE')

class HSworker:

    """ A Class to run and manage the Header Service"""

    def __init__(self,**keys):

        self.keys = keys
        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in keys.iteritems():
            setattr(self, k, v)
            print k,v

        # Inititalize the State class to keep track of the system's state
        self.init_State()


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


    def get_channels(self):
        
        # Extract the unique channel by topic/device
        LOGGER.info("Extracting Telemetry channels from telemetry dictionary")
        self.channels = get_telemetry_channels(self.telemetry,
                                               start_collection_event=self.start_collection_event,
                                               end_collection_event=self.end_collection_event)        

    def run_enable(self,**keys):

        # Unpack the dictionary of **keys into variables to do:
        # self.keyname = key['keyname']
        for k, v in keys.iteritems():
            setattr(self, k, v)
            print k,v

        
        


def get_channel_name(c):
    ''' Standard format the name of a channel across module'''
    return '{}_{}'.format(c['device'],c['topic'])

def get_telemetry_channels(telem,start_collection_event=None,end_collection_event=None):
    '''
    Get the unique telemetry channels from telemetry dictionary to define channel
    that we need to subscribe to
    '''
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
        if name not in channels.keys():
            c['Stype'] = 'Event'
            channels[name] = c

    return channels


def subscribe_to_channels(channels,start=True):
    SAL_connection = {}
    for name, c in channels.items():
        SAL_connection[name] = salpytools.DDSSubcriber(c['device'],c['topic'],Stype=c['Stype'])
        if start: SAL_connection[name].start()

    return SAL_connection

    
