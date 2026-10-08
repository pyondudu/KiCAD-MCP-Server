"""Detect the installed KiCad major version and pick matching file-format tokens.

New schematics are written with a KiCad 10 header (``(version 20260101)``) since
issue #221. KiCad 9 refuses to open such a file with a bare "Failed to load
schematic", so on a KiCad 9 install every project created by the server was
unusable until the header was hand-edited. Writing the header for the KiCad
that is actually installed keeps new files loadable there; the dynamic symbol
loader already gates its KiCad 10-only tokens on the file's declared version,
so a v9 header is all that is needed downstream.

Resolution order:

    1. ``$KICAD_MCP_KICAD_MAJOR`` (e.g. ``9``) — explicit override, never cached.
    2. ``kicad-cli version`` of the resolved kicad-cli — cached for the process.
    3. ``None`` — unknown; callers fall back to the newest format.
"""

import logging
import os
import re
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("kicad_interface")

_ENV_VAR = "KICAD_MCP_KICAD_MAJOR"

#: Schematic ``(version ...)`` token and ``generator_version`` per KiCad major.
SCH_FORMATS = {
    8: (20231120, "8.0"),
    9: (20250114, "9.0"),
    10: (20260101, "10.0"),
}
_NEWEST = max(SCH_FORMATS)

_UNSET = object()
_cached_major: object = _UNSET


def _parse_major(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\.\d+", text or "")
    return int(m.group(1)) if m else None


def kicad_major_version() -> Optional[int]:
    """Return the installed KiCad major version, or ``None`` if unknown."""
    global _cached_major

    override = os.environ.get(_ENV_VAR)
    if override:
        major = _parse_major(override if "." in override else f"{override}.0")
        if major is not None:
            return major
        logger.warning("%s=%r is not a version number; ignoring it", _ENV_VAR, override)

    if _cached_major is not _UNSET:
        return _cached_major  # type: ignore[return-value]

    major = None
    try:
        from utils.kicad_cli import resolve_kicad_cli

        cli = resolve_kicad_cli()
        if cli:
            out = subprocess.run(
                [cli, "version"], capture_output=True, text=True, timeout=15
            ).stdout
            major = _parse_major(out)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("kicad-cli version probe failed: %s", e)

    _cached_major = major
    return major


def sch_format() -> Tuple[int, str]:
    """``(file_version, generator_version)`` for new schematics on this install."""
    major = kicad_major_version()
    if major is None or major >= _NEWEST:
        return SCH_FORMATS[_NEWEST]
    return SCH_FORMATS.get(major, SCH_FORMATS[min(SCH_FORMATS)])


def sch_header_line() -> str:
    """Single-line ``(kicad_sch ...`` opener for hand-written schematics."""
    version, generator_version = sch_format()
    return (
        f'(kicad_sch (version {version}) (generator "eeschema")'
        f' (generator_version "{generator_version}")\n\n'
    )


def apply_sch_format(content: str) -> str:
    """Rewrite a schematic's header tokens to the installed KiCad's format."""
    version, generator_version = sch_format()
    content = re.sub(r"\(version \d+\)", f"(version {version})", content, count=1)
    return re.sub(
        r'\(generator_version "[^"]*"\)',
        f'(generator_version "{generator_version}")',
        content,
        count=1,
    )


def reset_cache() -> None:
    """Forget the detected version (primarily for tests)."""
    global _cached_major
    _cached_major = _UNSET
