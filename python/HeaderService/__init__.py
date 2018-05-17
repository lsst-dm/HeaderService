__author__  = "LSST/Felipe Menanteau"
__version__ = '1VNIA'
version = __version__

from . import hutils
from . import camera_coords
#from .hutils import HDRTEMPL_SciCamera
from .hutils import HDRTEMPL_TestCamera
from .hutils import HDRTEMPL_ATSCam
from .camera_coords import CCDGeom
#from . import SAL_tools
#from . import SAL_tools_send
from . import states

