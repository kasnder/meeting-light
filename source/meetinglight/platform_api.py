"""Select the supported desktop integrations without importing another OS's APIs."""
import sys

if sys.platform == 'win32':
    from .platform_windows import *
elif sys.platform == 'darwin':
    from .platform_macos import *
else:
    raise RuntimeError('This release supports Windows and macOS')
