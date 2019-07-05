#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio
import time

async def main():
    async with salobj.Domain() as domain:
        aths = salobj.Remote(domain=domain, name="ATHeaderService", index=0)
        print("Sending to OFFLINE")
        await salobj.set_summary_state(remote=aths, state=salobj.State.OFFLINE)

asyncio.get_event_loop().run_until_complete(main())

