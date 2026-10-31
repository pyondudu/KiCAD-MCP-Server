"""
KiCad-style placement of a placed symbol's Reference / Value fields.

The previous placement in batch_add_components had three problems that made a
freshly drawn schematic hard to read:

* fields kept field angle 0 whatever the symbol rotation, so on a symbol
  rotated 90/270 the text was drawn vertically (KiCad combines the stored
  field angle with the symbol transform);
* positions came from the pin axis only, so text landed on a connector's pins
  or a LED's emission arrows, and power symbols got the library offsets
  without the Y-flip (``+5V`` drawn under the wire instead of above the arrow);
* every field was forced visible, un-hiding the ``#PWR`` / ``#FLG`` references.

This module mirrors what eeschema does on placement: power symbols keep the
library field offsets, correctly transformed; other symbols get their fields
stacked beside the body (from the library graphics) on the first side with no
pins — right, top, bottom, left — always reading horizontally, with the stored
justification compensated for the symbol transform. Visibility is preserved.
"""

import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import sexpdata
from sexpdata import Symbol

from commands.schematic_text_utils import _find_matching_paren, _move_property_in_block
from commands.wire_dragger import WireDragger

logger = logging.getLogger("kicad_interface")

_GAP = 1.27  # body edge -> text anchor (mm)
_LINE = 2.54  # stacked field pitch (mm)
_FIELDS = ("Reference", "Value")

BBox = Tuple[float, float, float, float]  # x_min, y_min, x_max, y_max


def _items(lst: Any, tag: str) -> List[list]:
    return [x for x in lst if isinstance(x, list) and x and x[0] == Symbol(tag)]


def _first(lst: Any, tag: str) -> Optional[list]:
    found = _items(lst, tag)
    return found[0] if found else None


def _lib_symbol(raw_content: str, lib_id: str) -> Optional[list]:
    """The embedded ``(lib_symbols (symbol "<lib_id>" ...))`` definition, parsed."""
    start = raw_content.find("(lib_symbols")
    if start < 0:
        return None
    m = re.compile(r'\(symbol\s+"' + re.escape(lib_id) + r'"').search(raw_content, start)
    if not m:
        return None
    end = _find_matching_paren(raw_content, m.start())
    if end < 0:
        return None
    try:
        return sexpdata.loads(raw_content[m.start() : end + 1])
    except Exception:
        return None


def _graphics_points(lib_sym: list, unit: int) -> List[Tuple[float, float]]:
    """Points spanning the body graphics of ``unit`` (lib coords, Y up)."""
    pts: List[Tuple[float, float]] = []
    for sub in _items(lib_sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if m and (int(m.group(1)) not in (0, unit) or int(m.group(2)) != 1):
            continue
        for g in sub:
            if not isinstance(g, list) or not g:
                continue
            tag = str(g[0])
            if tag == "rectangle":
                for key in ("start", "end"):
                    p = _first(g, key)
                    if p:
                        pts.append((float(p[1]), float(p[2])))
            elif tag in ("polyline", "bezier"):
                for xy in _items(_first(g, "pts") or [], "xy"):
                    pts.append((float(xy[1]), float(xy[2])))
            elif tag == "arc":
                for key in ("start", "mid", "end"):
                    p = _first(g, key)
                    if p:
                        pts.append((float(p[1]), float(p[2])))
            elif tag == "circle":
                c, r = _first(g, "center"), _first(g, "radius")
                if c and r:
                    cx, cy, rad = float(c[1]), float(c[2]), float(r[1])
                    pts += [(cx - rad, cy - rad), (cx + rad, cy + rad)]
    return pts


def _unit_pins(lib_sym: list, unit: int) -> List[Tuple[float, float]]:
    """Connection points of the pins drawn by ``unit`` (lib coords, Y up).

    Pins in ``<name>_0_*`` sub-symbols are common to every unit. A multi-unit
    part's other units are placed elsewhere on the sheet, so their pins must
    not decide which side of *this* unit is free.
    """
    pts: List[Tuple[float, float]] = []
    for sub in _items(lib_sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if m and int(m.group(1)) not in (0, unit):
            continue
        for pin in _items(sub, "pin"):
            at = _first(pin, "at")
            if at:
                pts.append((float(at[1]), float(at[2])))
    return pts


def _bbox(points: List[Tuple[float, float]]) -> Optional[BBox]:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _text_flipped(rotation: float, mirror_x: bool, mirror_y: bool, angle: float) -> bool:
    """True when eeschema draws a field of stored ``angle`` right-to-left-justified.

    eeschema keeps field text readable, so when the symbol transform turns the
    text direction leftwards it mirrors the justification: ``justify left`` on
    a symbol rotated 90 grows to the left of its anchor.
    """
    a = math.radians(angle)
    x0, _ = WireDragger.pin_world_xy(0, 0, 0, 0, rotation, mirror_x, mirror_y)
    x1, _ = WireDragger.pin_world_xy(math.cos(a), math.sin(a), 0, 0, rotation, mirror_x, mirror_y)
    return (x1 - x0) < -1e-6


def _set_justify(block: str, prop: str, justify: Optional[str]) -> str:
    """Set the horizontal ``(justify ...)`` of a property's effects (None = centred)."""
    m = re.search(r'\(property\s+"' + re.escape(prop) + r'"', block)
    if not m:
        return block
    pe = _find_matching_paren(block, m.start())
    sub = block[m.start() : pe + 1]
    em = re.search(r"\(effects", sub)
    if not em:
        return block
    ee = _find_matching_paren(sub, em.start())
    effects = re.sub(r"\s*\(justify[^()]*\)", "", sub[em.start() : ee + 1])
    if justify:
        effects = effects[:-1] + f" (justify {justify}))"
    sub = sub[: em.start()] + effects + sub[ee + 1 :]
    return block[: m.start()] + sub + block[pe + 1 :]


def _field_hidden(block: str, prop: str) -> bool:
    m = re.search(r'\(property\s+"' + re.escape(prop) + r'"', block)
    if not m:
        return True
    sub = block[m.start() : _find_matching_paren(block, m.start()) + 1]
    return "(hide yes)" in sub or "(hide)" in sub


def _locked(block: str, prop: str) -> bool:
    """True when the user pinned the field (``(do_not_autoplace yes)``)."""
    m = re.search(r'\(property\s+"' + re.escape(prop) + r'"', block)
    if not m:
        return False
    sub = block[m.start() : _find_matching_paren(block, m.start()) + 1]
    return "(do_not_autoplace yes)" in sub


def _r(v: float) -> float:
    return round(v, 4)


def autoplace_fields(
    block_text: str,
    raw_content: str,
    all_pins: Optional[Dict[str, Any]] = None,
) -> str:
    """Return ``block_text`` with Reference/Value placed the way eeschema would.

    ``block_text`` is one placed ``(symbol (lib_id ...) ...)`` block of
    ``raw_content`` (whose ``lib_symbols`` supplies the library definition);
    ``all_pins`` maps pin number -> world ``(x, y)``. Returns the block
    unchanged when the symbol cannot be analysed.
    """
    try:
        sym = sexpdata.loads(block_text)
    except Exception:
        return block_text
    lib_id_node, at = _first(sym, "lib_id"), _first(sym, "at")
    if not lib_id_node or not at:
        return block_text
    lib_id = str(lib_id_node[1])
    cx, cy = float(at[1]), float(at[2])
    rot = float(at[3]) if len(at) > 3 else 0.0
    mirror = _first(sym, "mirror")
    mx = bool(mirror and str(mirror[1]) == "x")
    my = bool(mirror and str(mirror[1]) == "y")
    unit_node = _first(sym, "unit")
    unit = int(unit_node[1]) if unit_node else 1

    lib_sym = _lib_symbol(raw_content, lib_id)
    if lib_sym is None:
        return block_text

    def world(px: float, py: float) -> Tuple[float, float]:
        return WireDragger.pin_world_xy(px, py, cx, cy, rot, mx, my)

    is_power = _first(lib_sym, "power") is not None
    if is_power:
        # Library offsets, transformed like any other symbol point: KiCad keeps
        # the power symbol's own layout (value above +5V, below GND).
        block = block_text
        for prop in _FIELDS:
            if _locked(block, prop):
                continue
            lp = next((p for p in _items(lib_sym, "property") if p[1] == prop), None)
            lat = _first(lp, "at") if lp else None
            if not lat:
                continue
            wx, wy = world(float(lat[1]), float(lat[2]))
            angle = float(lat[3]) if len(lat) > 3 else 0.0
            block, _ = _move_property_in_block(
                block, prop, _r(wx), _r(wy), angle, not _field_hidden(block, prop)
            )
        return block

    lib_box = _bbox(_graphics_points(lib_sym, unit))
    pins = [world(px, py) for px, py in _unit_pins(lib_sym, unit)]
    if not pins:
        # No pin data in the embedded library symbol: fall back to the
        # caller's pin map (which, for a multi-unit part, spans every unit).
        for c in (all_pins or {}).values():
            px, py = (c[0], c[1]) if isinstance(c, (list, tuple)) else (c["x"], c["y"])
            pins.append((float(px), float(py)))

    if lib_box:
        corners = [world(x, y) for x in (lib_box[0], lib_box[2]) for y in (lib_box[1], lib_box[3])]
        body = _bbox(corners)
    else:
        body = _bbox(pins)
        if body:
            # No body graphics (an op-amp's power unit is just two pins): the
            # pin names are drawn beside the pin line, so keep clear of them.
            body = (body[0] - _LINE, body[1] + _GAP, body[2] + _LINE, body[3] - _GAP)
    if body is None:
        body = (cx - _GAP, cy - _GAP, cx + _GAP, cy + _GAP)
    x0, y0, x1, y1 = body
    bcx, bcy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = max((x1 - x0) / 2, 0.01), max((y1 - y0) / 2, 0.01)

    sides = set()
    for px, py in pins:
        dx, dy = (px - bcx) / hw, (py - bcy) / hh
        if abs(dx) >= abs(dy):
            sides.add("right" if dx > 0 else "left")
        else:
            sides.add("bottom" if dy > 0 else "top")

    shown = [p for p in _FIELDS if not _field_hidden(block_text, p)]
    angle = 90.0 if round(rot) % 180 == 90 else 0.0
    flipped = _text_flipped(rot, mx, my, angle)

    # (x, y, effective horizontal justify) per shown field, top to bottom.
    spots: List[Tuple[float, float, Optional[str]]] = []
    n = len(shown)
    if "right" not in sides:
        top = bcy - (n - 1) * _LINE / 2
        spots = [(x1 + _GAP, top + i * _LINE, "left") for i in range(n)]
    elif "top" not in sides and ("bottom" not in sides or n == 1):
        # Reference above, Value below when both sides are free.
        if n == 2 and "bottom" not in sides:
            spots = [(bcx, y0 - _GAP - 0.635, None), (bcx, y1 + _GAP + 0.635, None)]
        else:
            spots = [(bcx, y0 - _GAP - 0.635 - (n - 1 - i) * _LINE, None) for i in range(n)]
    elif "top" not in sides:
        spots = [(bcx, y0 - _GAP - 0.635 - (n - 1 - i) * _LINE, None) for i in range(n)]
    elif "bottom" not in sides:
        spots = [(bcx, y1 + _GAP + 0.635 + i * _LINE, None) for i in range(n)]
    elif "left" not in sides:
        top = bcy - (n - 1) * _LINE / 2
        spots = [(x0 - _GAP, top + i * _LINE, "right") for i in range(n)]
    else:
        # Pins on every side (NE555: VCC on top, GND below). Centred above the
        # body the text sits on the top pin's wire, so start it just right of
        # the rightmost top pin (Reference) / bottom pin (Value), left-justified.
        def right_of(side_pins: List[Tuple[float, float]]) -> float:
            return max(p[0] for p in side_pins) + _GAP if side_pins else bcx

        top_pins = [p for p in pins if (p[1] - bcy) / hh < -abs((p[0] - bcx) / hw)]
        bottom_pins = [p for p in pins if (p[1] - bcy) / hh > abs((p[0] - bcx) / hw)]
        spots = [
            (right_of(top_pins), y0 - _GAP - 0.635, "left"),
            (right_of(bottom_pins), y1 + _GAP + 0.635, "left"),
        ][:n]

    block = block_text
    for prop, (fx, fy, just) in zip(shown, spots):
        if _locked(block, prop):
            continue
        if just and flipped:
            just = "right" if just == "left" else "left"
        block, _ = _move_property_in_block(block, prop, _r(fx), _r(fy), angle, True)
        block = _set_justify(block, prop, just)
    return block


def symbol_extent(block_text: str, raw_content: str) -> Optional[Dict[str, float]]:
    """World bbox of one placed symbol unit: body graphics plus its own pin tips.

    The pin spread alone misses bodies that reach past the pins (an ATtiny85's
    body runs 12.7 mm left of its pins) and, for a multi-unit part, spans every
    unit placed under the same reference. None when the symbol cannot be read.
    """
    try:
        sym = sexpdata.loads(block_text)
    except Exception:
        return None
    lib_id_node, at = _first(sym, "lib_id"), _first(sym, "at")
    if not lib_id_node or not at:
        return None
    cx, cy = float(at[1]), float(at[2])
    rot = float(at[3]) if len(at) > 3 else 0.0
    mirror = _first(sym, "mirror")
    mx = bool(mirror and str(mirror[1]) == "x")
    my = bool(mirror and str(mirror[1]) == "y")
    unit_node = _first(sym, "unit")
    unit = int(unit_node[1]) if unit_node else 1
    lib_sym = _lib_symbol(raw_content, str(lib_id_node[1]))
    if lib_sym is None:
        return None
    pts = _graphics_points(lib_sym, unit) + _unit_pins(lib_sym, unit)
    box = _bbox([WireDragger.pin_world_xy(x, y, cx, cy, rot, mx, my) for x, y in pts])
    if box is None:
        return None
    return {"x_min": _r(box[0]), "y_min": _r(box[1]), "x_max": _r(box[2]), "y_max": _r(box[3])}


def autoplace_reference_fields(
    schematic_path: Any, reference: str, unit: Optional[int] = None
) -> bool:
    """Autoplace the fields of one placed symbol in a schematic file.

    Returns True when the file was changed. Best-effort: any failure leaves
    the file untouched.
    """
    from pathlib import Path

    from commands.pin_locator import PinLocator
    from commands.schematic_text_utils import _find_placed_symbol_block

    try:
        path = Path(schematic_path)
        content = path.read_text(encoding="utf-8")
        block, start, end = _find_placed_symbol_block(content, reference, unit)
        if not block:
            return False
        pins = PinLocator().get_all_symbol_pins(path, reference) or {}
        new_block = autoplace_fields(block, content, pins)
        if new_block == block:
            return False
        path.write_text(content[:start] + new_block + content[end + 1 :], encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Field autoplace skipped for {reference}: {e}")
        return False
