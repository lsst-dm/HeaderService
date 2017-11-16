
import time
import sys
import SALPY_dmHeaderService
import threading
import logging
import HeaderService.hutils as hutils
import HeaderService.states as states

LOGGER = hutils.create_logger(level=logging.NOTSET,name=__name__)
SAL__CMD_COMPLETE=303

class DeviceState:

    def __init__(self, module='dmHeaderService',default_state='OFFLINE',
                 tsleep=0.5,
                 eventlist = ['SummaryState',
                              'SettingVersions',
                              'RejectedCommand'] ):

        self.current_state = default_state
        self.tsleep = tsleep
        self.module = module
        
        LOGGER.info('HeaderService Init beginning')
        LOGGER.info('Starting with default state: {}'.format(default_state))

        # Subscribe to events 
        #self.subscribe()

        # Subscribe to all events in list
        self.subscribe_list(eventlist)

    def subscribe_list(self,eventlist):
    
        # Subscribe to events 
        self.mgr = {}
        self.myData = {}
        self.logEvent = {}
        for eventname in eventlist:
            self.subscribe_logEvent(eventname)

    def send_logEvent(self,eventname,**kwargs):
        
        ''' Send logevent for an eventname'''
        # Populate myData object for keys across logevent
        self.myData[eventname].timestamp = kwargs.pop('timestamp',time.time())
        self.myData[eventname].priority  = kwargs.pop('priority',1)
        priority = int(self.myData[eventname].priority)
        if eventname == 'SummaryState':
            self.myData[eventname].summaryState = states.state_enumeration[self.current_state] 

        # Override from kwargs
        for key in kwargs:
            setattr(self.myData[eventname],key,kwargs.get(key))

        LOGGER.info('Sending {}'.format(eventname))
        self.logEvent[eventname](self.myData[eventname], priority)
        LOGGER.info('Sent {}: sucessfully'.format(eventname))
        time.sleep(self.tsleep)
        return True

    def subscribe_logEvent(self,eventname):
        '''Create a subscription for the dmHeaderService_logevent_{eventnname}'''
        self.mgr[eventname] = SALPY_dmHeaderService.SAL_dmHeaderService()
        self.mgr[eventname].salEvent("dmHeaderService_logevent_{}".format(eventname))
        self.logEvent[eventname] = getattr(self.mgr[eventname],'logEvent_{}'.format(eventname))
        self.myData[eventname] = getattr(SALPY_dmHeaderService,'dmHeaderService_logevent_{}C'.format(eventname))()
        #self.myData_keys[eventname] = [a[0] for a in inspect.getmembers(self.myData[eventname]) if not(a[0].startswith('__') and a[0].endswith('__'))]
        LOGGER.info('Initializing: dmHeaderService_logevent_{}'.format(eventname))
        
    def subscribe(self):
        self.subscribe_SummaryState()
        self.subscribe_SettingVersions()
        self.subscribe_RejectedCommand()

    def subscribe_SummaryState(self):
        '''Create a subscription for the dmHeaderService_logevent_SummaryState'''
        self.mgr_SummaryState = SALPY_dmHeaderService.SAL_dmHeaderService()
        self.mgr_SummaryState.salEvent("dmHeaderService_logevent_SummaryState")
        self.myData_SummaryState = SALPY_dmHeaderService.dmHeaderService_logevent_SummaryStateC()
        LOGGER.info('Initializing: dmHeaderService_logevent_SummaryState')

    def subscribe_SettingVersions(self):
        '''Create a subscription for the dmHeaderService_logevent_SettingVersions'''
        self.mgr_SettingVersions = SALPY_dmHeaderService.SAL_dmHeaderService()
        self.mgr_SettingVersions.salEvent("dmHeaderService_logevent_SettingVersions")
        self.myData_SettingVersions = SALPY_dmHeaderService.dmHeaderService_logevent_SettingVersionsC()
        LOGGER.info('Initializing: dmHeaderService_logevent_SettingVersions')

    def subscribe_RejectedCommand(self):
        '''Create a subscription for the dmHeaderService_logevent_RejectedCommand'''
        self.mgr_RejectedCommand = SALPY_dmHeaderService.SAL_dmHeaderService()
        self.mgr_RejectedCommand.salEvent("dmHeaderService_logevent_RejectedCommand")
        self.myData_RejectedCommand = SALPY_dmHeaderService.dmHeaderService_logevent_RejectedCommandC()
        LOGGER.info('Initializing: dmHeaderService_logevent_RejectedCommand')
        
    def send_SummaryState(self,priority=1):
        '''Send the summary state for a device'''
        # Short-cut for myData and mgr
        myData = self.myData_SummaryState
        mgr = self.mgr_SummaryState
        
        myData.summaryState = states.state_enumeration[self.current_state] 
        myData.timestamp = time.time()
        myData.priority = priority

        LOGGER.info('Sending SummaryState: {}[{}]'.format(self.current_state,myData.summaryState))
        mgr.logEvent_SummaryState(myData, priority)
        LOGGER.info('Sent SummaryState: {}[{}] sucessfully'.format(self.current_state,myData.summaryState))
        time.sleep(self.tsleep)
        return True

    def send_SettingVersions(self,priority=1):
        '''Send the SettingVersions for a device'''
        # Short-cut for myData and mgr
        myData = self.myData_SettingVersions
        mgr = self.mgr_SettingVersions

        myData.recommendedSettingsVersion = ''
        myData.timestamp = time.time()
        myData.priority = priority

        LOGGER.info('Sending SettingVersions: {}'.format(myData.recommendedSettingsVersion))
        mgr.logEvent_SettingVersions(myData, priority)
        LOGGER.info('Sent SettingVersions: {} sucessfully'.format(myData.recommendedSettingsVersion))
        time.sleep(self.tsleep)
        return True

    def send_RejectedCommand(self,priority=1,rejected_state=None):
        '''Send RejectedCommand if transition is not valid'''
        next_state = states.next_state[rejected_state]
        # Short-cut for myData and mgr
        myData = self.myData_RejectedCommand
        mgr = self.mgr_RejectedCommand

        myData.commandValue = states.state_enumeration[next_state] # CHECK THIS OUT
        myData.detailedState = states.state_enumeration[self.current_state] 
        myData.timestamp = time.time()
        myData.priority = priority

        LOGGER.info('Sending RejectedCommand: {}[{}]'.format(next_state,myData.commandValue))
        mgr.logEvent_RejectedCommand(myData, priority)
        LOGGER.info('Sent RejectedCommand: {}[{}] sucessfully'.format(next_state,myData.commandValue))
        return True
        
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
            self.mgr_ackCommand(cmdId, SAL__CMD_COMPLETE, 0, "Done : OK");

            # New way
            # Update the current state
            self.State.current_state = self.next_state
            self.State.send_logEvent('SummaryState')
            #self.State.current_state = self.next_state
            #self.State.send_SummaryState()
            #self.State.send_SettingVersions()
        else:
            LOGGER.info("WARNING: INVALID TRANSITION from {} --> {}".format(self.State.current_state, self.next_state))
            self.State.send_RejectedCommand(rejected_state=self.COMMAND)
        

def validate_transition(current_state, new_state):
    current_index = states.state_enumeration[current_state]
    new_index = states.state_enumeration[new_state]
    transition_is_valid = states.state_matrix[current_index][new_index]
    if transition_is_valid:
        LOGGER.info("Transition from {} --> {} is VALID".format(current_state, new_state))
    else:
        LOGGER.info("Transition from {} --> {} is INVALID".format(current_state, new_state))
    return transition_is_valid 
