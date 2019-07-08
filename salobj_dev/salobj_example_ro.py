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
        self.atcam.evt_startIntegration.callback = self.startIntegration_callback
        self.atcam.evt_endOfImageTelemetry.callback = self.endOfImageTelemetry_callback

    def startIntegration_callback(self, data):
        if self.summary_state != salobj.State.ENABLED:
            print(f"Current State is {self.summary_state.name}")
            return
        print(f"Got startIntegration")
        print(f"Collecting start...")
        self.collect_start()

    def endOfImageTelemetry_callback(self, data):
        print(f"Got endOfImageTelemetry")
        print(f"Collecting end...")
        self.collect_end()

    def collect_start(self):
        name = "startIntegration"
        self.myData[name] = self.atcam.evt_startIntegration.get()
        self.metadata['DATE-BEG'] = getattr(self.myData[name], 'timeStamp')

    def collect_end(self):
        name = "imageReadoutParameters"
        self.myData[name] = self.atcam.evt_imageReadoutParameters.get()
        self.metadata['OVERH'] = getattr(self.myData[name], 'overCols')
        self.metadata['OVERV'] = getattr(self.myData[name], 'overRows')

    def clean(self):
        self.myData = {}
        self.metadata = {}

    def report_summary_state(self):
        super().report_summary_state()
        print(f"State is: {self.summary_state.name}")

if __name__ == "__main__":

    hs = HSWorker()
    asyncio.get_event_loop().run_until_complete(hs.done_task)
