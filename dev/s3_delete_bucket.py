#!/usr/bin/env python

"""
This is an S3 HeadeService example to delete a bucket using salobj

To access the S3 server,
the environment variables are set via:

export S3_ENDPOINT_URL=http://lsst-nfs.ncsa.illinois.edu:9000
export AWS_ACCESS_KEY_ID={access_key}
export AWS_SECRET_ACCESS_KEY={secret_key}
"""

from lsst.ts import salobj

# 1. Get the bucket name we want -- change accordingly
s3instance = "dummy"
s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(s3instance=s3instance)
print(f" --- Will use Bucket name:{s3bucket_name}")

# 2. Use AsyncS3Bucket to make bucket + S3 connection
s3bucket = salobj.AsyncS3Bucket(name=s3bucket_name, domock=False)
# We will re-use the connection made by salobj
s3conn = s3bucket.service_resource

# In case we want to delete contents and bucket
bucket_names = [b.name for b in s3conn.buckets.all()]
if s3bucket_name in bucket_names:
    print(f"Deleting: {s3bucket_name}")
    s3bucket.bucket.objects.all().delete()
    s3bucket.bucket.delete()
else:
    print(f" --- Cannot delete bucket: {s3bucket_name} it does not exists")
