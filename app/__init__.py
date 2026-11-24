"""LocalChords: app desktop local-first per accordi, testi, tab e stem."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("localchords")
except PackageNotFoundError:  # pragma: no cover - esecuzione da sorgenti non installati
    __version__ = "0.0.0"
