#!/usr/bin/python
import sys, os
import vars, state
from helpers import err, mkdirp


if not vars.TARGET:
    err('redo-ifcreate: error: must be run from inside a .do\n')
    sys.exit(100)

try:
    for t in sys.argv[1:]:
        if os.path.exists(t):
            err('redo-ifcreate: error: %r already exists\n' % t)
            sys.exit(1)
        else:
            state.add_dep(vars.TARGET, 'c', t)
except KeyboardInterrupt:
    sys.exit(200)
