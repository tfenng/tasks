#!/usr/bin/env python3

import os, sys
print('PWD', os.environ.get('PWD', 'unknown'))
print('args', sys.argv[1:])
