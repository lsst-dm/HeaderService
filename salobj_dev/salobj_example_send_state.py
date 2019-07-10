#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio
import time
import sys

async def main(req_state):
    async with salobj.Domain() as domain:
        aths = salobj.Remote(domain=domain, name="ATHeaderService", index=0)
        print(f"Sending to {req_state}")
        newstate = getattr(salobj.State,req_state)
        await salobj.set_summary_state(remote=aths, state=newstate)


if __name__ == "__main__":
    req_state = sys.argv[1]
    asyncio.get_event_loop().run_until_complete(main(req_state))

