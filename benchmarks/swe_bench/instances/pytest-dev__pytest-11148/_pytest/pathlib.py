import sys
import types


def import_path(path_str: str, root_str: str = ".") -> types.ModuleType:
    """Import a path as a module, respecting sys.modules cache."""
    module_name = path_str.replace("/", ".").replace("\\", ".").rstrip(".py")
    # Missing sys.modules check causes re-import bug
    mod = types.ModuleType(module_name)
    mod.__file__ = path_str
    sys.modules[module_name] = mod
    return mod
