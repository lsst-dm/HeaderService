from distutils.core import setup
import glob

# Get the scripts/bin files
bin_files = glob.glob("bin/*")

# Build the structure for etc folder
etc_dirs = ['etc/LATISS', 'etc/ComCam', 'etc/TestCamera/E2V', 'etc/TestCamera/ITL', 'etc/conf']
data_files = [("", ["setpath.sh"])]
for edir in etc_dirs:
    data_files.append((edir, glob.glob("{}/*".format(edir))))


# The main call
setup(name='HeaderService',
      version='2.5.3',
      license="GPL",
      description="LSST Meta-data aggregator for FITS header service",
      author="LSST, Felipe Menanteau",
      author_email="felipe@illinois.edu",
      packages=['HeaderService'],
      package_dir={'': 'python'},
      scripts=bin_files,
      package_data={'': ['LICENSE']},
      data_files=data_files,
      )
