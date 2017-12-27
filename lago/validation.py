import logging
import imp

LOGGER = logging.getLogger(__name__)


def check_import(module_name):
    """
    Search if a module exists, and it is possible to try importing it

    Args:
        module_name(str): module to import

    Returns:
        bool: True if the package is found
    """
    try:
        imp.find_module(module_name)
        return True
    except ImportError:
        return False
