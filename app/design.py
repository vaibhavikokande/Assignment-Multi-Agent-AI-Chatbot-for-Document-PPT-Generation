"""Shared visual design system for generated DOCX and PPTX artifacts.

The palette, colour maths, and low-level OOXML helpers live here so that the
document and presentation generators produce one consistent, professional look
instead of unstyled default output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_ACCENT = "1F4E79"
WHITE = "FFFFFF"

# Glyphs are written as escapes so this source file stays ASCII-only.
BULLET_CHAR = "▪"  # black small square
DASH_CHAR = "—"  # em dash
DOT_CHAR = "·"  # middle dot


def clean_hex(value: Any, fallback: str = DEFAULT_ACCENT) -> str:
    """Normalize any colour-ish input into a six digit uppercase RGB string."""
    if not isinstance(value, str):
        return fallback
    text = value.strip().lstrip("#").upper()
    if len(text) == 3 and all(char in "0123456789ABCDEF" for char in text):
        text = "".join(char * 2 for char in text)
    if len(text) == 8:  # ARGB
        text = text[2:]
    if len(text) != 6 or any(char not in "0123456789ABCDEF" for char in text):
        return fallback
    return text


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    color = clean_hex(value)
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def rgb_to_hex(rgb: Iterable[float]) -> str:
    return "".join(f"{max(0, min(255, int(round(channel)))):02X}" for channel in rgb)


def mix(color: str, other: str, ratio: float) -> str:
    """Blend ``color`` toward ``other``; 0.0 keeps the colour, 1.0 returns ``other``."""
    ratio = max(0.0, min(1.0, ratio))
    base = hex_to_rgb(color)
    target = hex_to_rgb(other)
    return rgb_to_hex(base[index] + (target[index] - base[index]) * ratio for index in range(3))


def lighten(color: str, amount: float) -> str:
    return mix(color, WHITE, amount)


def darken(color: str, amount: float) -> str:
    return mix(color, "000000", amount)


def luminance(color: str) -> float:
    red, green, blue = hex_to_rgb(color)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


def readable_on(color: str, light: str = WHITE, dark: str = "11161F") -> str:
    """Pick the foreground colour with usable contrast against ``color``."""
    return dark if luminance(color) > 0.55 else light


@dataclass(frozen=True)
class Palette:
    """Derived colour roles shared by both generators."""

    accent: str
    accent_deep: str
    accent_soft: str
    tint: str
    tint_strong: str
    ink: str
    body: str
    muted: str
    rule: str
    surface: str
    on_accent: str
    on_accent_muted: str

    @classmethod
    def from_accent(cls, accent: Any = None) -> "Palette":
        base = clean_hex(accent, DEFAULT_ACCENT)
        # Very light or very dark source accents are pulled toward a usable mid
        # tone so headings, fills, and rules stay legible.
        if luminance(base) > 0.72:
            base = darken(base, 0.42)
        elif luminance(base) < 0.06:
            base = lighten(base, 0.22)
        return cls(
            accent=base,
            accent_deep=darken(base, 0.34),
            accent_soft=lighten(base, 0.55),
            tint=lighten(base, 0.92),
            tint_strong=lighten(base, 0.84),
            ink=darken(base, 0.60),
            body="2B3340",
            muted="6B7482",
            rule=lighten(base, 0.76),
            surface="FBFCFD",
            on_accent=readable_on(base),
            on_accent_muted=mix(readable_on(base), base, 0.30),
        )


def palette_from_profile(profile: dict[str, Any] | None) -> Palette:
    """Build a palette from an uploaded template profile when it exposes colours."""
    style = (profile or {}).get("style", {}) if isinstance(profile, dict) else {}
    if not isinstance(style, dict):
        return Palette.from_accent(DEFAULT_ACCENT)
    candidates: list[Any] = []
    if style.get("accent_color"):
        candidates.append(style["accent_color"])
    theme = style.get("theme")
    if isinstance(theme, dict):
        candidates.extend(theme.get("accent_colors", []) or [])
    styles = style.get("styles")
    if isinstance(styles, list):
        candidates.extend(item.get("font_color") for item in styles[:40] if isinstance(item, dict))
    for candidate in candidates:
        color = clean_hex(candidate, "")
        if not color:
            continue
        # Skip near-white and near-black template colours; they carry no brand signal.
        if 0.08 < luminance(color) < 0.86:
            return Palette.from_accent(color)
    return Palette.from_accent(DEFAULT_ACCENT)


# ---------------------------------------------------------------------------
# DOCX (WordprocessingML) helpers
# ---------------------------------------------------------------------------


def _element(tag: str) -> Any:
    from docx.oxml import OxmlElement

    return OxmlElement(tag)


def _w(name: str) -> Any:
    from docx.oxml.ns import qn

    return qn(name)


# WordprocessingML validates the order of property children. Appending out of
# order produces a file Word reports as corrupt, so every helper below splices
# new elements into their schema-mandated position.
PPR_ORDER = (
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
    "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
    "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
    "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
    "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
    "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
)
RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
    "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
    "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
    "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath", "rPrChange",
)
TCPR_ORDER = (
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap",
    "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark", "headers",
    "cellIns", "cellDel", "cellMerge", "tcPrChange",
)
TBLPR_ORDER = (
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
    "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
    "tblPrChange",
)
TRPR_ORDER = (
    "cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit",
    "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden", "ins", "del", "trPrChange",
)
EDGE_ORDER = ("top", "left", "bottom", "right", "insideH", "insideV", "tl2br", "tr2bl")
MARGIN_ORDER = ("top", "left", "bottom", "right")


def _local_name(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _drop(parent: Any, name: str) -> None:
    for node in parent.findall(_w(f"w:{name}")):
        parent.remove(node)


def _place(parent: Any, name: str, order: tuple[str, ...]) -> Any:
    """Create ``w:{name}`` under ``parent`` at the position the schema requires."""
    _drop(parent, name)
    element = _element(f"w:{name}")
    rank = order.index(name) if name in order else len(order)
    for existing in list(parent):
        sibling = _local_name(existing)
        if sibling in order and order.index(sibling) > rank:
            existing.addprevious(element)
            return element
    parent.append(element)
    return element


def _border(container: Any, edge: str, *, val: str, size: int, space: int, color: str) -> None:
    node = _place(container, edge, EDGE_ORDER)
    node.set(_w("w:val"), val)
    node.set(_w("w:sz"), str(size))
    node.set(_w("w:space"), str(space))
    node.set(_w("w:color"), clean_hex(color))


def _shading(parent: Any, order: tuple[str, ...], color: str) -> None:
    shading = _place(parent, "shd", order)
    shading.set(_w("w:val"), "clear")
    shading.set(_w("w:color"), "auto")
    shading.set(_w("w:fill"), clean_hex(color))


def shade_cell(cell: Any, color: str) -> None:
    _shading(cell._tc.get_or_add_tcPr(), TCPR_ORDER, color)


def cell_borders(cell: Any, edges: dict[str, dict[str, Any]]) -> None:
    """Apply per-edge borders, e.g. ``{"left": {"sz": 24, "color": "1F4E79"}}``."""
    properties = cell._tc.get_or_add_tcPr()
    container = properties.find(_w("w:tcBorders"))
    if container is None:
        container = _place(properties, "tcBorders", TCPR_ORDER)
    for edge in EDGE_ORDER:
        if edge not in edges:
            continue
        spec = edges[edge]
        _border(
            container,
            edge,
            val=str(spec.get("val", "single")),
            size=int(spec.get("sz", 8)),
            space=int(spec.get("space", 0)),
            color=str(spec.get("color", "000000")),
        )


def clear_table_borders(table: Any) -> None:
    borders = _place(table._tbl.tblPr, "tblBorders", TBLPR_ORDER)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        _border(borders, edge, val="none", size=0, space=0, color="auto")


def cell_margins(cell: Any, top: int = 80, start: int = 120, bottom: int = 80, end: int = 120) -> None:
    """Set cell padding in twentieths of a point."""
    margins = _place(cell._tc.get_or_add_tcPr(), "tcMar", TCPR_ORDER)
    values = {"top": top, "left": start, "bottom": bottom, "right": end}
    for name in MARGIN_ORDER:
        node = _place(margins, name, MARGIN_ORDER)
        node.set(_w("w:w"), str(values[name]))
        node.set(_w("w:type"), "dxa")


def _width_pct(parent: Any, name: str, order: tuple[str, ...], percent: float) -> None:
    node = _place(parent, name, order)
    node.set(_w("w:w"), str(int(percent * 50)))  # w:type="pct" counts fiftieths of a percent
    node.set(_w("w:type"), "pct")


def set_table_width_pct(table: Any, percent: float = 100.0) -> None:
    """Make a table occupy a percentage of the text column, independent of template widths."""
    _width_pct(table._tbl.tblPr, "tblW", TBLPR_ORDER, percent)


def set_cell_width_pct(cell: Any, percent: float) -> None:
    _width_pct(cell._tc.get_or_add_tcPr(), "tcW", TCPR_ORDER, percent)


def paragraph_border(
    paragraph: Any,
    edge: str = "bottom",
    color: str = DEFAULT_ACCENT,
    size: int = 8,
    space: int = 6,
) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = properties.find(_w("w:pBdr"))
    if borders is None:
        borders = _place(properties, "pBdr", PPR_ORDER)
    _border(borders, edge, val="single", size=size, space=space, color=color)


def shade_paragraph(paragraph: Any, color: str) -> None:
    _shading(paragraph._p.get_or_add_pPr(), PPR_ORDER, color)


def letter_spacing(run: Any, twips: int = 30) -> None:
    """Track out a run; used for small uppercase eyebrow labels."""
    _place(run._r.get_or_add_rPr(), "spacing", RPR_ORDER).set(_w("w:val"), str(twips))


def keep_with_next(paragraph: Any) -> None:
    _place(paragraph._p.get_or_add_pPr(), "keepNext", PPR_ORDER)


def repeat_header_row(row: Any) -> None:
    _place(row._tr.get_or_add_trPr(), "tblHeader", TRPR_ORDER).set(_w("w:val"), "true")


def keep_row_together(row: Any) -> None:
    """Stop a table row from breaking across a page boundary."""
    _place(row._tr.get_or_add_trPr(), "cantSplit", TRPR_ORDER)


def add_field(paragraph: Any, instruction: str) -> Any:
    """Insert a simple Word field such as PAGE or NUMPAGES."""
    field = _element("w:fldSimple")
    field.set(_w("w:instr"), instruction)
    field.append(_element("w:r"))
    paragraph._p.append(field)
    return field


# ---------------------------------------------------------------------------
# PPTX (DrawingML) helpers
# ---------------------------------------------------------------------------

_DRAWINGML = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _a(name: str) -> str:
    return f"{{{_DRAWINGML}}}{name}"


# CT_TextParagraphProperties requires its children in this order. Appending out
# of order produces XML that PowerPoint silently ignores, so new bullet elements
# are always spliced into the right position.
_PPR_CHILD_ORDER = (
    "lnSpc",
    "spcBef",
    "spcAft",
    "buClrTx",
    "buClr",
    "buSzTx",
    "buSzPct",
    "buSzPts",
    "buFontTx",
    "buFont",
    "buNone",
    "buAutoNum",
    "buChar",
    "tabLst",
    "defRPr",
    "extLst",
)


def _para_properties(paragraph: Any) -> Any:
    properties = paragraph._pPr
    if properties is None:
        properties = paragraph._p.get_or_add_pPr()
    return properties


def _insert_ordered(properties: Any, tag: str) -> Any:
    """Create ``tag`` under ``properties`` at its schema-mandated position."""
    from lxml import etree

    element = etree.SubElement(properties, _a(tag))
    try:
        rank = _PPR_CHILD_ORDER.index(tag)
    except ValueError:  # pragma: no cover - defensive
        return element
    for existing in list(properties):
        name = etree.QName(existing).localname if existing.tag is not etree.Comment else ""
        if name == tag or name not in _PPR_CHILD_ORDER:
            continue
        if _PPR_CHILD_ORDER.index(name) > rank:
            existing.addprevious(element)
            break
    return element


def _drop_children(properties: Any, tags: tuple[str, ...]) -> None:
    for tag in tags:
        for node in properties.findall(_a(tag)):
            properties.remove(node)


def set_bullet(paragraph: Any, color: str, char: str = BULLET_CHAR, indent_emu: int = 209550) -> None:
    """Apply a native coloured bullet with a hanging indent to a PPTX paragraph."""
    properties = _para_properties(paragraph)
    properties.set("marL", str(indent_emu))
    properties.set("indent", str(-indent_emu))
    _drop_children(properties, ("buNone", "buClr", "buFont", "buChar", "buAutoNum"))
    bullet_color = _insert_ordered(properties, "buClr")
    _insert_ordered(bullet_color, "srgbClr").set("val", clean_hex(color))
    _insert_ordered(properties, "buFont").set("typeface", "Arial")
    _insert_ordered(properties, "buChar").set("char", char)


def clear_bullet(paragraph: Any) -> None:
    properties = _para_properties(paragraph)
    _drop_children(properties, ("buClr", "buFont", "buChar", "buAutoNum"))
    if properties.find(_a("buNone")) is None:
        _insert_ordered(properties, "buNone")
    properties.set("marL", "0")
    properties.set("indent", "0")


def send_to_back(shape: Any) -> None:
    """Move a decorative shape behind the slide's content shapes."""
    tree = shape._element.getparent()
    if tree is None:
        return
    tree.remove(shape._element)
    # Index 2 keeps the required nvGrpSpPr and grpSpPr elements first.
    tree.insert(2, shape._element)


def flat_shape(shape: Any) -> None:
    """Strip the default outline and shadow from a decorative shape."""
    shape.line.fill.background()
    try:
        shape.shadow.inherit = False
    except (AttributeError, NotImplementedError):  # pragma: no cover - template dependent
        pass
