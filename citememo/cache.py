"""Two-level cache for corpus files: an in-memory LRU over JSON files on disk.

ADR-0004: no database. The Caselaw Access Project (CAP) files are cached as
JSON in exactly the layout of the committed seed cache::

    <cache dir>/{slug}/VolumesMetadata.json
    <cache dir>/{slug}/{volume_folder}/CasesMetadata.json
    <cache dir>/{slug}/{volume_folder}/cases/{file_name}.json

Cache directory order (BUILD-NOTES §6): ``CITEMEMO_CACHE_DIR`` → ``seed/cache/cap``
when writable → ``/tmp/citememo-cache``. Whatever directory is chosen for
writing, the committed ``seed/cache/cap`` stays readable as a fallback, so the
seeded demo answers from the repo even on a read-only deployment filesystem.

A 404 from CAP is a real answer (DECISION-RULE §1.4 ``Absent``) and is cached as
a small marker file ``<path>.404`` next to where the positive result would
live; the positive layout itself is never faked. Failures (timeouts, 5xx,
non-JSON bodies) are never cached.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CACHE_DIR = REPO_ROOT / "seed" / "cache" / "cap"
"""The committed CAP cache (read-only fallback for every DiskCache)."""
TMP_CACHE_DIR = Path("/tmp/citememo-cache")
"""Last-resort writable cache directory (Vercel: only /tmp is writable)."""
ABSENT_SUFFIX = ".404"
"""Marker file suffix recording that CAP answered 404 for this path."""
DEFAULT_MEMORY_SIZE = 64
"""Entries kept in the in-memory LRU (one volume's CasesMetadata is 0.5–6.5 MB)."""


class _Sentinel:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name

    def __bool__(self) -> bool:
        return False


MISSING = _Sentinel("MISSING")
"""``DiskCache.get`` result: nothing cached for this path (fetch it)."""
ABSENT = _Sentinel("ABSENT")
"""``DiskCache.get`` result: the corpus answered 404 for this path (cached)."""

_TRUE = {"1", "true", "yes", "on"}


def is_offline(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when ``CITEMEMO_OFFLINE`` is set to 1/true/yes/on (case-insensitive)."""
    env = os.environ if env is None else env
    return (env.get("CITEMEMO_OFFLINE") or "").strip().lower() in _TRUE


def is_writable_dir(path: Path) -> bool:
    """True when ``path`` exists (or can be created) and a file can be written in it."""
    try:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".w-", dir=str(path))
        os.close(fd)
        os.unlink(tmp)
        return True
    except OSError:
        return False


def resolve_cache_dir(
    env: Optional[Mapping[str, str]] = None,
    seed_dir: Path = SEED_CACHE_DIR,
    tmp_dir: Path = TMP_CACHE_DIR,
) -> Path:
    """Pick the writable cache directory.

    Order: ``env["CITEMEMO_CACHE_DIR"]`` (created if missing) → ``seed_dir`` when
    writable → ``tmp_dir``. An unwritable ``CITEMEMO_CACHE_DIR`` falls through
    to the next option with a warning. The returned directory exists.
    """
    env = os.environ if env is None else env
    custom = (env.get("CITEMEMO_CACHE_DIR") or "").strip()
    if custom:
        p = Path(custom).expanduser()
        if is_writable_dir(p):
            return p
        log.warning("CITEMEMO_CACHE_DIR=%s is not writable; falling back", custom)
    if is_writable_dir(Path(seed_dir)):
        return Path(seed_dir)
    tmp_dir = Path(tmp_dir)
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.warning("cache dir %s could not be created; cache is memory-only", tmp_dir)
    return tmp_dir


class LRU:
    """A small thread-safe least-recently-used map.

    ``get(key, default=MISSING)`` returns ``default`` on a miss; ``put`` inserts
    or refreshes; the oldest entry is evicted past ``maxsize``.
    """

    def __init__(self, maxsize: int = DEFAULT_MEMORY_SIZE) -> None:
        self.maxsize = max(1, int(maxsize))
        self._d: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = MISSING) -> Any:
        with self._lock:
            if key not in self._d:
                return default
            self._d.move_to_end(key)
            return self._d[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def pop(self, key: str) -> None:
        with self._lock:
            self._d.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._d

    def __len__(self) -> int:
        with self._lock:
            return len(self._d)


class DiskCache:
    """Memory LRU over JSON files, reading from several directories, writing to one.

    ``DiskCache(write_dir=None, read_dirs=None, memory_size=64, env=None)``:
    ``write_dir`` defaults to :func:`resolve_cache_dir`; ``read_dirs`` defaults
    to ``[write_dir, SEED_CACHE_DIR]`` (the committed seed cache is always a
    read fallback). Paths passed to the methods are cache-relative POSIX paths
    such as ``"f3d/925/CasesMetadata.json"``.
    """

    def __init__(
        self,
        write_dir: Optional[Path] = None,
        read_dirs: Optional[Iterable[Path]] = None,
        memory_size: int = DEFAULT_MEMORY_SIZE,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.write_dir = Path(write_dir) if write_dir is not None else resolve_cache_dir(env=env)
        dirs = [self.write_dir] + ([SEED_CACHE_DIR] if read_dirs is None else [Path(d) for d in read_dirs])
        seen: set = set()
        self.read_dirs: list[Path] = []
        for d in dirs:
            if d not in seen:
                seen.add(d)
                self.read_dirs.append(d)
        self._mem = LRU(memory_size)

    # -- paths ------------------------------------------------------------- #

    def path(self, rel: str) -> Path:
        """Where ``rel`` is (or would be) written: ``write_dir / rel``."""
        return self.write_dir / rel

    def find(self, rel: str) -> Optional[Path]:
        """First existing file for ``rel`` across ``read_dirs``, else None."""
        for d in self.read_dirs:
            p = d / rel
            if p.is_file():
                return p
        return None

    def has(self, rel: str) -> bool:
        """True when a positive result for ``rel`` is on disk or in memory."""
        v = self._mem.get(rel)
        if v is not MISSING and v is not ABSENT:
            return True
        return self.find(rel) is not None

    def is_absent(self, rel: str) -> bool:
        """True when a 404 marker for ``rel`` is on disk or in memory."""
        if self._mem.get(rel) is ABSENT:
            return True
        return self.find(rel + ABSENT_SUFFIX) is not None

    # -- read -------------------------------------------------------------- #

    def get(self, rel: str) -> Any:
        """Return the parsed JSON for ``rel``, ``ABSENT`` (cached 404) or ``MISSING``.

        Memory first, then each read directory; a file that is not valid JSON
        is logged and treated as ``MISSING`` so a later fetch can repair it.
        """
        v = self._mem.get(rel)
        if v is not MISSING:
            return v
        p = self.find(rel)
        if p is not None:
            try:
                with p.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                log.warning("unreadable cache file %s: %s", p, exc)
            else:
                self._mem.put(rel, data)
                return data
        if self.find(rel + ABSENT_SUFFIX) is not None:
            self._mem.put(rel, ABSENT)
            return ABSENT
        return MISSING

    # -- write ------------------------------------------------------------- #

    def put(self, rel: str, data: Any) -> Optional[Path]:
        """Store a positive result in memory and atomically on disk (write_dir).

        Returns the file path, or None when the disk is not writable (the
        value then lives in memory only; nothing is raised).
        """
        self._mem.put(rel, data)
        target = self.path(rel)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(target.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
                os.replace(tmp, target)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            marker = self.path(rel + ABSENT_SUFFIX)
            if marker.exists():
                marker.unlink()
        except OSError as exc:
            log.warning("cache write failed for %s: %s", target, exc)
            return None
        return target

    def put_absent(self, rel: str) -> Optional[Path]:
        """Record that the corpus answered 404 for ``rel`` (marker ``rel + '.404'``)."""
        self._mem.put(rel, ABSENT)
        marker = self.path(rel + ABSENT_SUFFIX)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("404\n", encoding="utf-8")
        except OSError as exc:
            log.warning("cache marker write failed for %s: %s", marker, exc)
            return None
        return marker

    def clear_memory(self) -> None:
        """Drop the in-memory layer (files stay)."""
        self._mem.clear()

    def __repr__(self) -> str:
        return f"DiskCache(write_dir={str(self.write_dir)!r}, read_dirs={[str(d) for d in self.read_dirs]!r})"
