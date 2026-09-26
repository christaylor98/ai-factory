"""Opt-in .env loading (see the package docstring for why it is not done on import)."""
from typing import Optional


def load_env(path: Optional[str] = None) -> bool:
    """Load a .env file into os.environ without overriding what is already set. With no path, python-dotenv's
    search: the current directory, then its parents. Returns whether a file was loaded; False when python-dotenv
    is not installed."""
    try:
        from dotenv import load_dotenv, find_dotenv
    except ImportError:
        return False
    target = path or find_dotenv(usecwd=True)
    return bool(target) and load_dotenv(target, override=False)
