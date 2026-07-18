import sys
from importlib import import_module

_owner = import_module("loushang.harness.tools.workspace.bash")
sys.modules[__name__] = _owner
