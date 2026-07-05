"""Minimal parser for Clausewitz / Paradox script (the `key = value` / `key = { ... }`
text format used across HOI4's `common/`, `history/`, and save games).

The format is small but has a few quirks we must handle:
  * `#` starts a line comment.
  * A brace block can hold assignments (`steel = 2`) *or* a bare token list
    (`categories = { category_army category_infantry }`) *or* a mix.
  * Keys legitimately repeat (`division_template = {...}` many times in one file;
    `infantry = { x=0 y=0 }` many times in one `regiments` block), so we must
    preserve order and duplicates rather than collapsing into a dict.
  * Values may be quoted strings, numbers, or identifiers.
  * Operators other than `=` appear (`<`, `>`, `>=`, `<=`, `==`, `!=`), mostly in
    triggers; we keep the operator so callers can inspect it.

We deliberately keep this dependency-free and lenient: unknown constructs are
preserved as raw tokens rather than raising, so the parser survives mods that use
syntax we didn't anticipate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

_SPECIAL = set("{}=<>")
_OPERATOR_STARTS = set("=<>!")

Value = Union[str, "Block"]


def _tokenize(text: str) -> Iterator[str]:
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "#":  # comment to end of line
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if c == '"':  # quoted string (keep quotes stripped)
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                buf.append(text[j])
                j += 1
            yield '"' + "".join(buf)  # sentinel prefix marks "this was quoted"
            i = j + 1
            continue
        if c in "{}=":
            yield c
            i += 1
            continue
        if c in "<>!":  # possibly a two-char operator (>=, <=, !=, ==)
            if i + 1 < n and text[i + 1] == "=":
                yield c + "="
                i += 2
            else:
                yield c
                i += 1
            continue
        # bare token: run until whitespace / special char / comment
        j = i
        while j < n and text[j] not in " \t\r\n#" and text[j] not in _SPECIAL:
            j += 1
        yield text[i:j]
        i = j


@dataclass
class Item:
    """One entry in a Block: either an assignment (key op value) or a bare scalar."""

    key: Optional[str]  # None for bare scalars (token lists)
    op: Optional[str]  # '=', '>', ... ; None for bare scalars
    value: Value  # str or Block; equals the scalar itself for bare items


@dataclass
class Block:
    """An ordered collection of Items. Duplicate keys are preserved."""

    items: List[Item] = field(default_factory=list)

    # -- assignment access ------------------------------------------------
    def get(self, key: str) -> Optional[Value]:
        """First value assigned to `key`, or None."""
        for it in self.items:
            if it.key == key:
                return it.value
        return None

    def get_all(self, key: str) -> List[Value]:
        return [it.value for it in self.items if it.key == key]

    def get_str(self, key: str, default: Optional[str] = None) -> Optional[str]:
        v = self.get(key)
        return v if isinstance(v, str) else default

    def get_float(self, key: str, default: Optional[float] = None) -> Optional[float]:
        v = self.get(key)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return default
        return default

    def get_block(self, key: str) -> Optional["Block"]:
        v = self.get(key)
        return v if isinstance(v, Block) else None

    def pairs(self) -> Iterator[Tuple[str, Value]]:
        for it in self.items:
            if it.key is not None:
                yield it.key, it.value

    def scalars(self) -> List[str]:
        """Bare tokens (e.g. the elements of a `categories = { a b c }` list)."""
        return [it.value for it in self.items if it.key is None and isinstance(it.value, str)]

    def __iter__(self) -> Iterator[Item]:
        return iter(self.items)


class _Parser:
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.i = 0

    def _peek(self, ahead: int = 0) -> Optional[str]:
        j = self.i + ahead
        return self.toks[j] if j < len(self.toks) else None

    def _next(self) -> Optional[str]:
        t = self._peek()
        if t is not None:
            self.i += 1
        return t

    @staticmethod
    def _clean(tok: str) -> str:
        return tok[1:] if tok.startswith('"') else tok

    def parse_block(self, top: bool = False) -> Block:
        block = Block()
        while True:
            t = self._peek()
            if t is None:
                if top:
                    break
                break  # tolerate missing closing brace at EOF
            if t == "}":
                self._next()
                break
            # Is this an assignment? key <op> value
            nxt = self._peek(1)
            if nxt is not None and (nxt == "=" or nxt in ("<", ">", ">=", "<=", "==", "!=")):
                key = self._clean(self._next())
                op = self._next()
                val = self._parse_value()
                block.items.append(Item(key=key, op=op, value=val))
            else:
                # bare scalar element
                self._next()
                block.items.append(Item(key=None, op=None, value=self._clean(t)))
        return block

    def _parse_value(self) -> Value:
        t = self._peek()
        if t == "{":
            self._next()
            return self.parse_block(top=False)
        self._next()
        return self._clean(t if t is not None else "")


def parse(text: str) -> Block:
    """Parse Clausewitz-format text into a top-level Block."""
    return _Parser(list(_tokenize(text))).parse_block(top=True)


def parse_file(path: Union[str, Path]) -> Block:
    raw = Path(path).read_bytes()
    # HOI4 files are usually UTF-8 (some with a BOM); fall back to latin-1.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return parse(text)
