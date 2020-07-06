#!/usr/bin/env python

"""
This is an S3 HeadeService example to upload a file using salobj

To access the S3 server,
the environment variables are set via:

export S3_ENDPOINT_URL=http://lsst-nfs.ncsa.illinois.edu:9000
export AWS_ACCESS_KEY_ID={access_key}
export AWS_SECRET_ACCESS_KEY={secret_key}
"""

from lsst.ts import salobj
import astropy
import asyncio
import time


async def main(ID):

    filename = f"{ID}.header"
    s3instance = "NTS"

    # 1. Get the bucket name we want
    s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(s3instance=s3instance)
    print(f"--- Will use Bucket name:{s3bucket_name}")

    # 2. Use AsyncS3Bucket to make bucket + S3 connection
    s3bucket = salobj.AsyncS3Bucket(name=s3bucket_name, domock=False)
    # We will re-use the connection made by salobj
    s3conn = s3bucket.service_resource

    # 3. Make sure the bucket exists in the list of bucket names:
    bucket_names = [b.name for b in s3conn.buckets.all()]
    if s3bucket_name not in bucket_names:
        s3conn.create_bucket(Bucket=s3bucket_name)
        print(f"Created Bucket: {s3bucket_name}")
    else:
        print(f"Bucket: {s3bucket_name} already exists")

    # 4. Uploading the file, using filename/key/url combination
    key = s3bucket.make_key(
        salname='CCHeaderService',
        salindexname=0,
        generator=ID,
        date=astropy.time.Time.now(),
    )
    url = f"s3://{s3bucket.name}/{key}"
    print(f"New key:{key}")
    print(f"URL:{url}")

    # Test using boto3 upload_file
    for k in range(10):
        t1 = time.time()
        s3conn.meta.client.upload_file(filename, s3bucket_name, key)
        t2 = time.time()
        print(f"Total time file: {t2-t1}")

    # Test using salobj upload_file
    for k in range(10):
        t1 = time.time()
        with open(filename, "rb") as f:
            await s3bucket.upload(fileobj=f, key=key)
            t2 = time.time()
            print(f"Total time fileobj: {t2-t1}")

    # Now we print the contents
    for bucket in s3conn.buckets.all():
        print(f" + {bucket}")
        for file in bucket.objects.all():
            print(f"   - {file.key}")


if __name__ == "__main__":
    # A header file example from ComCam
    ID = 'CC_O_20200521_000008'
    asyncio.get_event_loop().run_until_complete(main(ID))
