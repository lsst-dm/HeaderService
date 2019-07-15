#!/usr/bin/env python3

import lsst.ts.salobj as salobj
import asyncio
import time
import sys

def cmdline():

    import argparse
    parser = argparse.ArgumentParser(description="Send CSC to a given State")

    # The optional arguments
    parser.add_argument("state", action="store",
                        help="Desired State")
    parser.add_argument("-c", "--csc_name", action="store", default='ATHeaderService',
                        help="Name of CSC")
    args = parser.parse_args()
    return args

async def main(args):
    async with salobj.Domain() as domain:
        aths = salobj.Remote(domain=domain, name=args.csc_name, index=0)
        newstate = getattr(salobj.State,args.state)
        print(f"Sending {args.csc_name} to: {args.state}")
        await salobj.set_summary_state(remote=aths, state=newstate)
        print(f"Done")

if __name__ == "__main__":
    args = cmdline()
    asyncio.get_event_loop().run_until_complete(main(args))

