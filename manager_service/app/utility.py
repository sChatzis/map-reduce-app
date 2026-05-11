from pathlib import PurePosixPath
import re

def is_valid_path(path: str) -> bool:
    if (not PurePosixPath(path).is_absolute()) or ("\0" in path):
        return False

    return bool(re.match(r'^[a-zA-Z0-9/_\-\.]+$', path))