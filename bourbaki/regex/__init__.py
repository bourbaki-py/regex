"""Awesomely readable regex construction in pure Python"""

from .base import (
    CharRange,
    CharSet,
    CharClass,
    C,
    L,
    Literal,
    If,
    Alternation,
    START,
    END,
    ANYCHAR,
    StartString,
    EndString,
    Tab,
    Endline,
    BackSpace,
    CarriageReturn,
    WordBoundary,
    WordInternal,
    WordChar,
    NonWordChar,
    Digit,
    NonDigit,
    Whitespace,
    NonWhitespace,
)

__version__ = "0.2.2"
