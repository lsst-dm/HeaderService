#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio

mystate = salobj.State.STANDBY

class HSWorker(salobj.BaseCsc):

    def __init__(self, name='ATHeaderService', initial_state=mystate):

        # Start the CSC with name
        super().__init__(name=name, index=0, initial_state=mystate)
        print(f"Creating for worker for: {name}")
        print(f"Running {salobj.__version__}")
        #self.atcam = salobj.Remote(domain=self.domain, name="ATCamera", index=0)
        #self.ATPtg = salobj.Remote(domain=self.domain, name="ATPtg", index=0)
        #self.atcam.evt_startIntegration.callback = self.startIntegration_callback

    def report_summary_state(self):
        super().report_summary_state()
        print(f"State is: {self.summary_state.name}")

if __name__ == "__main__":

    hs = HSWorker()
    asyncio.get_event_loop().run_until_complete(hs.done_task)
