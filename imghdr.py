"""
Compatibility shim for Python 3.13 where the stdlib 'imghdr' module was removed.

This minimal stub provides the 'what' API Tweepy imports. We don't upload images,
so returning None is sufficient for our text-only usage.
"""

from typing import Optional, Union, IO

def what(file: Optional[Union[str, bytes, IO[bytes]]] = None, h: Optional[bytes] = None) -> Optional[str]:
    """
    Mimic the old imghdr.what signature. Always returns None (unknown format).
    """
    return None