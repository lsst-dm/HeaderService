#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio
import time

async def main():
    async with salobj.Domain() as domain:
        aths = salobj.Remote(domain=domain, name="ATHeaderService", index=0)
        print("Sending to ENABLED")
        await salobj.set_summary_state(remote=aths, state=salobj.State.ENABLED)
        atcam = salobj.Controller(name="ATCamera", index=0)

        print("Sending imageReadoutParameters")
        kw = {'overRows': 10,
              'overCols': 20,
              'preCols':  30,
              'readCols': 40,
              'readCols2': 50,
              'readRows':  60}
        atcam.evt_imageReadoutParameters.set_put(**kw)

        print("Sending StartIntergration")
        kw = {'imageSequenceName': 'HEllo',
              'imageName': 'CAT',
              'imageIndex': 3,
              'timeStamp': time.time(),
              'exposureTime': 10,
              'priority': 1}
        atcam.evt_startIntegration.set_put(**kw)

        # Sending to OFFLINE now
        # print("Sending to OFFLINE")
        # await salobj.set_summary_state(remote=aths, state=salobj.State.OFFLINE)


asyncio.get_event_loop().run_until_complete(main())

