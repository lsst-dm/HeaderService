import distutils
from distutils.core import setup
import glob

# Trick to exclude the folder bin/test-scripts
bin_files = set(glob.glob("bin/*")) - set(glob.glob("bin/test-scripts/*"))
print (bin_files)
#exit()

# Build the structure for etc folder
etc_files = {}
etc_dirs = ['ATSCam','TestCamera','conf']
#for edir in etc_dirs:
#ATSCam_files = glob.glob("etc/ATSCam/*")
#TestCamera_files = glob.glob("etc/TestCamera/*")
#conf_files = glob.glob("etc/conf/*")

# The main call
setup(name='HeaderService',
      version ='OCS_IntSpecICC',
      license = "GPL",
      description = "LSST Meta-data aggregator for FITS header service",
      author = "LSST, Felipe Menanteau",
      author_email = "felipe@illinois.edu",
      packages = ['HeaderService'],
      package_dir = {'': 'python'},
      scripts = bin_files,
      #packages=find_packages(exclude=['ups',]),
      package_data={'': ['LICENSE']},
      #include_package_data=True,
      #install_requires=[],
      #data_files=[('etc/SED',   sed_files),
      #            ('etc/FILTER',flt_files),
      #            ('etc',   sql_files)]
      )
