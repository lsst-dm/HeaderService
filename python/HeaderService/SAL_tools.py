
import time
import sys
import threading
import logging
import HeaderService.hutils as hutils
import HeaderService.states as states
import inspect
# For now we only load 'dmHeaderService','tcs' and 'camera', but we might need them all.
import SALPY_dmHeaderService
import SALPY_camera 
import SALPY_tcs

"""
Here we store the SAL classes and tools that we use to:
 - Control devices
 - Gather telemetry/events
 - Send Control commands (to sim OCS)
 
"""

spinner = hutils.spinner
LOGGER = hutils.create_logger(level=logging.NOTSET,name=__name__)
SAL__CMD_COMPLETE=303

class DeviceState:

    def __init__(self, module='dmHeaderService',default_state='OFFLINE',
                 tsleep=0.5,
                 eventlist = ['SummaryState',
                              'SettingVersions',
                              'RejectedCommand',
                              'SettingsApplied',
                              'AppliedSettingsMatchStart'] ):

        self.current_state = default_state
        self.tsleep = tsleep
        self.module = module
        
        LOGGER.info('HeaderService Init beginning')
        LOGGER.info('Starting with default state: {}'.format(default_state))

        # Subscribe to all events in list
        self.subscribe_list(eventlist)

    def subscribe_list(self,eventlist):
        # Subscribe to list of logEvents
        self.mgr = {}
        self.myData = {}
        self.logEvent = {}
        self.myData_keys = {}
        for eventname in eventlist:
            self.subscribe_logEvent(eventname)

    def send_logEvent(self,eventname,**kwargs):
        ''' Send logevent for an eventname'''
        # Populate myData object for keys across logevent
        self.myData[eventname].timestamp = kwargs.pop('timestamp',time.time())
        self.myData[eventname].priority  = kwargs.pop('priority',1)
        priority = int(self.myData[eventname].priority)

        # Populate myData with the default cases
        if eventname == 'SummaryState':
            self.myData[eventname].summaryState = states.state_enumeration[self.current_state] 
        if eventname == 'RejectedCommand':
            rejected_state = kwargs.get('rejected_state')
            next_state = states.next_state[rejected_state]
            self.myData[eventname].commandValue = states.state_enumeration[next_state] # CHECK THIS OUT
            self.myData[eventname].detailedState = states.state_enumeration[self.current_state] 

        # Override from kwargs
        for key in kwargs:
            setattr(self.myData[eventname],key,kwargs.get(key))

        LOGGER.info('Sending {}'.format(eventname))
        self.logEvent[eventname](self.myData[eventname], priority)
        LOGGER.info('Sent sucessfully {} Data Object'.format(eventname))
        for key in self.myData_keys[eventname]:
            LOGGER.info('\t{}:{}'.format(key,getattr(self.myData[eventname],key)))
        time.sleep(self.tsleep)
        return True

    def subscribe_logEvent(self,eventname):
        '''Create a subscription for the dmHeaderService_logevent_{eventnname}'''
        self.mgr[eventname] = SALPY_dmHeaderService.SAL_dmHeaderService()
        self.mgr[eventname].salEvent("dmHeaderService_logevent_{}".format(eventname))
        self.logEvent[eventname] = getattr(self.mgr[eventname],'logEvent_{}'.format(eventname))
        self.myData[eventname] = getattr(SALPY_dmHeaderService,'dmHeaderService_logevent_{}C'.format(eventname))()
        self.myData_keys[eventname] = [a[0] for a in inspect.getmembers(self.myData[eventname]) if not(a[0].startswith('__') and a[0].endswith('__'))]
        LOGGER.info('Initializing: dmHeaderService_logevent_{}'.format(eventname))
        
    def get_current_state(self):
        '''Function to get the current state'''
        return self.current_state


class DDSController(threading.Thread):
    
    def __init__(self, command, module='dmHeaderService', topic=None, threadID='1', tsleep=0.5, State=None):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.module = module
        self.command  = command
        self.COMMAND = self.command.upper()
        # The topic:
        if not topic:
            self.topic = "{}_command_{}".format(module,command)
        else:
            self.topic  = topic
        self.tsleep = tsleep
        self.daemon = True
        self.State = State

        # Store to which state this command is going to move up, using the states.next_state dictionary
        self.next_state = states.next_state[self.COMMAND]
        
        # Subscribe
        self.subscribe()

    def subscribe(self):

        # This section does the equivalent of:
        # self.mgr = SALPY_tcs.SAL_tcs()
        # The steps are:
        # - 'figure out' the SALPY_xxxx module name
        # - find the library pointer using globals()
        # - create a mananger
        # Here we do the equivalent of:
        # mgr.salProcessor("dmHeaderService_command_EnterControl")

        self.newControl = False

        # Get the mgr
        SALPY_lib_name = 'SALPY_{}'.format(self.module)
        SALPY_lib = globals()[SALPY_lib_name]
        self.mgr = getattr(SALPY_lib, 'SAL_{}'.format(self.module))()
        self.mgr.salProcessor(self.topic)
        self.myData = getattr(SALPY_lib,self.topic+'C')()
        LOGGER.info("{} controller ready for topic: {}".format(self.module,self.topic))

        # We use getattr to get the equivalent of for our accept and ack command
        # mgr.acceptCommand_EnterControl()
        # mgr.ackCommand_EnterControl
        self.mgr_acceptCommand = getattr(self.mgr,'acceptCommand_{}'.format(self.command))
        self.mgr_ackCommand = getattr(self.mgr,'ackCommand_{}'.format(self.command))

    def run(self):
        self.run_command()

    def run_command(self):
        while True:
            cmdId = self.mgr_acceptCommand(self.myData)
            if cmdId > 0:
                self.reply_to_transition(cmdId)
                self.newControl = True
            time.sleep(self.tsleep)

    def reply_to_transition(self,cmdId):

        # Check if valid transition
        if validate_transition(self.State.current_state, self.next_state):
            # Send the ACK
            self.mgr_ackCommand(cmdId, SAL__CMD_COMPLETE, 0, "Done : OK");
            # Update the current state
            self.State.current_state = self.next_state

            if self.COMMAND == 'ENTERCONTROL':
                self.State.send_logEvent("SettingVersions",recommendedSettingsVersion='blah')
                self.State.send_logEvent('SummaryState')
            elif self.COMMAND == 'START':
                # Extract 'myData.configure' for START, eventually we
                # will apply the setting for this configuration, for now we
                LOGGER.info("From {} received configure: {}".format(self.COMMAND,self.myData.configure))
                # Here we should apply the setting in the future
                self.State.send_logEvent('SettingsApplied')
                self.State.send_logEvent('AppliedSettingsMatchStart',appliedSettingsMatchStartIsTrue=1)
                self.State.send_logEvent('SummaryState')
            else:
                self.State.send_logEvent('SummaryState')
        else:
            LOGGER.info("WARNING: INVALID TRANSITION from {} --> {}".format(self.State.current_state, self.next_state))
            self.State.send_logEvent('RejectedCommand',rejected_state=self.COMMAND)


def validate_transition(current_state, new_state):
    """
    Stand-alone function to validate transition. It returns true/false
    """
    current_index = states.state_enumeration[current_state]
    new_index = states.state_enumeration[new_state]
    transition_is_valid = states.state_matrix[current_index][new_index]
    if transition_is_valid:
        LOGGER.info("Transition from {} --> {} is VALID".format(current_state, new_state))
    else:
        LOGGER.info("Transition from {} --> {} is INVALID".format(current_state, new_state))
    return transition_is_valid 


class DDSSubcriber(threading.Thread):

    def __init__(self, module, topic, threadID='1', Stype='Telemetry',tsleep=0.01,timeout=3600,nkeep=100):
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
        # - find the library pointer using globals()
        # - create a mananger

        self.newTelem = False
        self.newEvent = False
        SALPY_lib_name = 'SALPY_%s' % self.module
        SALPY_lib = globals()[SALPY_lib_name]
        self.mgr = getattr(SALPY_lib, 'SAL_%s' % self.module)()
        self.myData = getattr(SALPY_lib,self.topic+'C')()
        if self.Stype=='Telemetry':
            self.mgr.salTelemetrySub(self.topic)
            # Generic method to get for example: self.mgr.getNextSample_kernel_FK5Target
            self.nextsample_topic = self.topic.split(self.module)[-1]
            self.getNext = getattr(self.mgr,"getNextSample" + self.nextsample_topic)
            LOGGER.info("%s subscriber ready for topic: %s" % (self.Stype,self.topic))
        elif self.Stype=='Event':
            self.mgr.salEvent(self.topic)
            # Generic method to get for example: self.mgr.getEvent_startIntegration(event)
            self.event_topic = self.topic.split("_")[-1]
            self.getNext = getattr(self.mgr,'getEvent_'+self.event_topic)
            LOGGER.info("%s subscriber ready for topic: %s" % (self.Stype,self.topic))
            
    def run(self):

        ''' The run method for the threading'''
        if self.Stype == 'Telemetry':
            self.newTelem = False
        elif self.Stype == 'Event':
            self.newEvent = False
        else:
            raise ValueError("Stype=%s not defined\n" % self.Stype)

        self.myDatalist = []
        while True:
            #retval = self.getNextSample(self.myData)
            retval = self.getNext(self.myData)
            if retval == 0:
                self.myDatalist.append(self.myData)
                self.myDatalist = self.myDatalist[-self.nkeep:] # Keep only nkeep entries
                self.newTelem = True
                self.newEvent = True
            time.sleep(self.tsleep)
        return 

    def getCurrent(self):
        if len(self.myDatalist) > 0:
            Current = self.myDatalist[-1]
            self.newTelem = False
            self.newEvent = False
        else:
            Current = None
        return Current

    def getCurrentTelemetry(self):
        return self.getCurrent()
    
    def getCurrentEvent(self):
        return self.getCurrent()
    
    def waitEvent(self,tsleep=None,timeout=None):

        """ Loop for waiting for new event """
        if not tsleep:
            tsleep = self.tsleep
        if not timeout:
            timeout = self.timeout
            
        t0 =  time.time()
        while not self.newEvent:
            sys.stdout.flush()
            sys.stdout.write("Wating for %s event.. [%s]" % (self.topic, spinner.next()))
            sys.stdout.write('\r') 
            if time.time() - t0 > timeout:
                LOGGER.info("WARNING: Timeout reading for Event %s" % self.topic)
                self.newEvent = False
                break
            time.sleep(tsleep)
        return self.newEvent

    def resetEvent(self):
        ''' Simple function to set it back'''
        self.newEvent=False

    def get_filter_name(self):
        # Need to move these filter definitions to a better place

        myData = self.getCurrentTelemetry()
        self.filter_names = ['u','g','r','i','z','Y']
        try:
            self.filter_name = self.filter_names[myData.REB_ID] 
        except:
            self.filter_name = 'zzz'

        return self.filter_name 

    
def command_sequencer(commands,Device='dmHeaderService',wait_time=1, sleep_time=3):

    """
    Stand-alone function to send a sequence of OCS Commands
    """

    # Trick to import modules dynamically as needed/depending on the Device we want
    try:
        exec "import SALPY_{}".format(Device)
    except:
        raise ValueError("import SALPY_{}: failed".format(Device))
    import time

    # We get the equivalent of:
    #  mgr = SALPY_dmHeaderService.SAL_dmHeaderService()
    SALPY_lib = globals()['SALPY_{}'.format(Device)]
    mgr = getattr(SALPY_lib,'SAL_{}'.format(Device))()
    myData = {}
    issueCommand = {}
    waitForCompletion = {}
    for cmd in commands:
        myData[cmd] = getattr(SALPY_lib,'dmHeaderService_command_{}C'.format(cmd))()
        issueCommand[cmd] = getattr(mgr,'issueCommand_{}'.format(cmd))
        waitForCompletion[cmd] = getattr(mgr,'waitForCompletion_{}'.format(cmd))
        # If Start we send some non-sense value
        if cmd == 'Start':
            myData[cmd].configure = 'blah.json'
        
    for cmd in commands:
        LOGGER.info("Issuing command: {}".format(cmd)) 
        LOGGER.info("Wait for Completion: {}".format(cmd)) 
        cmdId = issueCommand[cmd](myData[cmd])
        waitForCompletion[cmd](cmdId,wait_time)
        LOGGER.info("Done: {}".format(cmd)) 
        time.sleep(sleep_time)

    return

