#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio

mystate = salobj.State.STANDBY


class HSWorker(salobj.BaseCsc):

    def __init__(self, name='ATHeaderService', initial_state=mystate):

        # Where we will store the metadata
        self.clean()

        # Start the CSC with name
        super().__init__(name=name, index=0, initial_state=initial_state)
        print(f"Creating for worker for: {name}")
        print(f"Running {salobj.__version__}")
        self.atcam = salobj.Remote(domain=self.domain, name="ATCamera", index=0)
        self.atcam.evt_startIntegration.callback = self.startIntegration_callback
        self.atcam.evt_endOfImageTelemetry.callback = self.endOfImageTelemetry_callback
        self.endOfImage_timeout_task = salobj.make_done_future()

    async def close_tasks(self):
        await super().close_tasks()
        self.endOfImage_timeout_task.cancel()

    def report_summary_state(self):
        super().report_summary_state()
        if self.summary_state != salobj.State.ENABLED:
            self.endOfImage_timeout_task.cancel()

    def startIntegration_callback(self, data):
        if self.summary_state != salobj.State.ENABLED:
            print(f"Current State is {self.summary_state.name}")
            return
        print("Got startIntegration")
        print("Collecting start...")
        self.endOfImage_timeout_task.cancel()
        self.collect_start()
        self.endOfImage_timeout_task = asyncio.ensure_future(self.endOfImage_timeout(timeout=20))

    def endOfImageTelemetry_callback(self, data):
        if self.summary_state != salobj.State.ENABLED:
            print(f"Current State is {self.summary_state.name}")
            return
        print("Got endOfImageTelemetry")
        if self.endOfImage_timeout_task.done():
            print("Not collecting end data because not expecting endOfImage")
            self.log.error("endOfImage seen when not expected; ignored")
            return
        print("Collecting end...")
        self.endOfImage_timeout_task.cancel()
        self.collect_end()

    async def endOfImage_timeout(self, timeout):
        """Timeout timer for endOfImage telemetry callback"""
        await asyncio.sleep(timeout)
        self.log.error("endOfImage not seen in {timeout} seconds; giving up")
        self.clean()

    def collect_start(self):
        self.clean()
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


if __name__ == "__main__":

    hs = HSWorker()
    asyncio.get_event_loop().run_until_complete(hs.done_task)
