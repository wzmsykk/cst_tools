
import sys
[sys.path.append(i) for i in ['.', '..']]

import unittest
from cstworker import local_cstworker
from preprocess_cst import vbpreprocess
from data.superfish import elligen,elliheader
import json

