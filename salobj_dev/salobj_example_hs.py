#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio

mystate = salobj.State.STANDBY

class HSWorker(salobj.BaseCsc):

    def __init__(self, name='ATHeaderService', initial_state=mystate):

        # Where we will store the metadata
        self.clean()

        # Start the CSC with name
        super().__init__(name=name, index=0, initial_state=mystate)
        print(f"Creating for worker for: {name}")
        print(f"Running {salobj.__version__}")
        self.atcam = salobj.Remote(domain=self.domain, name="ATCamera", index=0)
        self.ATPtg = salobj.Remote(domain=self.domain, name="ATPtg", index=0)
        self.atcam.evt_startIntegration.callback = self.startIntegration_callback
        #self.aloop_task = asyncio.ensure_future(self.aloop())

    #async def close_tasks(self):
    #     await super().close_tasks()
    #     self.aloop_task.cancel()

    def clean(self):
        self.myData = {}
        self.metadata = {}

    #async def aloop(self):
    #    while self.summary_state != salobj.State.OFFLINE:
    #        print(f"I am in a loop and {self.summary_state.name}")
    #        await asyncio.sleep(0.5)

    def startIntegration_callback(self, data):
        if self.summary_state != salobj.State.ENABLED:
            print(f"Current State is {self.summary_state.name}")
            return
        print(f"Got startIntegration({data})")
        print(f"Collecting...")
        self.collect_beg()
        print(f"Metadata:{self.metadata}")
        #self.myData["startIntegration"] = data
        #self.metadata["endReadout"] = self.atcam.evt_endReadout.get()

    def collect_beg(self):

        name = "imageReadoutParameters"
        self.myData[name] = self.atcam.evt_imageReadoutParameters.get()
        self.metadata['OVERH'] = getattr(self.myData[name], 'overCols')
        self.metadata['OVERV'] = getattr(self.myData[name], 'overRows')

        #name = "endReadout"
        #self.myData[name] = self.atcam.evt_endReadout.get()
        #self.metadata['DATE-END'] = getattr(self.myData[name], 'timeStamp')

        name = "startIntegration"
        self.myData[name] = self.atcam.evt_startIntegration.get()
        self.metadata['DATE-BEG'] = getattr(self.myData[name], 'timeStamp')

    def report_summary_state(self):
        super().report_summary_state()
        print(f"State is: {self.summary_state.name}")

if __name__ == "__main__":

    hs = HSWorker()
    #hs.report_summary_state()
    #print(hs.summary_state)
    asyncio.get_event_loop().run_until_complete(hs.done_task)
