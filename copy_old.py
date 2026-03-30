# Proxy module to avoid shadowing standard library 'copy'
import sys
import os

# Identify the real copy module by bypassing this folder
_cwd = os.path.dirname(os.path.abspath(__file__))
_saved_path = list(sys.path)
while _cwd in sys.path:
    sys.path.remove(_cwd)
while '' in sys.path:
    sys.path.remove('')

import copy as _real_copy
from copy import *

# Restore sys.path for other module discovery
sys.path = _saved_path
del _cwd
del _saved_path
