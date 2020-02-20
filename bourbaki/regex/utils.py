from typing import List, Tuple, Mapping, Collection, Callable, Optional, Union
from collections.abc import Collection as CollectionABC
from functools import singledispatch
import itertools
import re

MAX_UNICODE_CODE_POINT = int("10FFFF", 16)
CHAR_CLASS_RESERVED_CHARS = ("-", "^", "\\", "]")

ALL_REGEX_FLAG_CHARS = set('aiLmsux')
ALL_NON_NEGATABLE_REGEX_FLAG_CHARS = set('aLu')
ALL_NEGATABLE_REGEX_FLAG_CHARS = set('imsx')

_regex_flag_to_regex_flag_char = {
    re.ASCII: 'a',
    re.IGNORECASE: 'i',
    re.LOCALE: 'L',
    re.MULTILINE: 'm',
    re.DOTALL: 's',
    re.UNICODE: 'u',
    re.VERBOSE: 'x',
}
REGEX_FLAG_NAME_TO_REGEX_FLAG_CHAR = {
    flag.name: char for flag, char in _regex_flag_to_regex_flag_char.items()
}
REGEX_FLAG_CHAR_TO_REGEX_FLAG_NAME = dict(map(reversed, REGEX_FLAG_NAME_TO_REGEX_FLAG_CHAR.items()))


AnyRegexFlag = Union[re.RegexFlag, int, str]
AnyRegexFlags = Union[AnyRegexFlag, Collection[AnyRegexFlag]]
RenameFunc = Callable[[str], Optional[str]]


def validate_range_arg(item):
    if not isinstance(item, slice):
        raise TypeError(
            "Arguments to Range[] should be slices, as in Range[start:stop, ...]; got {}".format(
                type(item)
            )
        )
    start, stop, step = item.start, item.stop, item.step

    if (step is not None) or (stop is None) or (start is None):
        msg = ""
        if (stop is None) or (start is None):
            msg = "Range[start:stop]; start and stop cannot be absent; got {}, {}.".format(
                start, stop
            )
        if step is not None:
            msg = " ".join(
                m
                for m in (
                    msg,
                    "Range[start:stop:step] syntax is not supported; got {} for step".format(
                        step
                    ),
                )
                if m
            )
        raise ValueError(msg)

    return start, stop


def validate_groupref(groupref: Union[int, str]) -> Union[int, str]:
    if isinstance(groupref, int):
        if groupref <= 0:
            raise ValueError(
                "integer group references must be positive; got {}".format(groupref)
            )
    elif isinstance(groupref, str):
        if not groupref.isidentifier():
            raise ValueError(
                "string group references must be valid identifiers; got {}".format(
                    repr(groupref)
                )
            )
    else:
        raise TypeError(
            "group references must be int or str; got {}".format(type(groupref))
        )

    return groupref


def validate_repetition_args(
    start: int, stop: int, step: int
) -> Tuple[int, Optional[int], int]:
    for arg, name in zip((start, stop, step), ("start", "stop", "step")):
        if arg is None:
            continue
        if not isinstance(arg, int):
            raise TypeError("{} must be an int; got {}".format(name, type(arg)))
        if arg < 0:
            raise ValueError("{} must be >= 0; got {}".format(name, arg))
    if (stop is not None) and (start is not None):
        if start > stop:
            raise ValueError(
                "stop must be greater than start; got start={}, stop={}".format(
                    start, stop
                )
            )

    if step is None:
        step = 1
    if start is None:
        start = 0
    return start, stop, step


def validate_positive_int(n: int, desc: str) -> int:
    if not isinstance(n, int):
        raise TypeError("{} must be ints; got {}".format(desc, type(n)))
    if n < 0:
        raise ValueError("{} must be positive; got {}".format(desc, n))
    return n


def validate_codepoint(codepoint: int) -> int:
    if codepoint < 0 or codepoint > MAX_UNICODE_CODE_POINT:
        raise ValueError(
            "invalid UTF codepoint: {}; must be in 0-{}, inclusive".format(
                codepoint, MAX_UNICODE_CODE_POINT
            )
        )
    return codepoint


def validate_char(char: str) -> str:
    if not len(char) == 1:
        raise ValueError("single character required; got {}".format(repr(char)))
    return char


def escape_for_char_class(char: str):
    if char in CHAR_CLASS_RESERVED_CHARS:
        return "\\" + char
    return ascii_char_repr_char(char, escape=False)


@singledispatch
def to_char(x) -> str:
    raise TypeError("can't convert type {} to single UTF character".format(type(x)))


@to_char.register(int)
def to_char_from_codepoint(x: int) -> str:
    return chr(validate_codepoint(x))


@to_char.register(str)
def to_char_from_str(s: str) -> str:
    return validate_char(s)


@singledispatch
def ascii_char_repr(x, escape: bool = False) -> str:
    raise TypeError("can't convert type {} to ascii character representation")


@ascii_char_repr.register(int)
def ascii_char_repr_codepoint(x: int, escape: bool = True) -> str:
    x = validate_codepoint(x)
    if x < 128:
        char = chr(x)
        char1 = re.escape(char) if escape else char
        char2 = repr(char)[1:-1]
        return max(char1, char2, key=len)
    return r"\u{:04x}".format(x)


@ascii_char_repr.register(str)
def ascii_char_repr_char(x: str, escape: bool = True) -> str:
    return ascii_char_repr_codepoint(utf_codepoint_str(x), escape=escape)


@singledispatch
def utf_codepoint(x) -> int:
    raise TypeError("can't compute utf codepoint for type {}".format(type(x)))


@utf_codepoint.register(int)
def utf_codepoint_int(x: int) -> int:
    return validate_codepoint(x)


@utf_codepoint.register(str)
def utf_codepoint_str(x: str) -> int:
    return ord(validate_char(x))


def identity(x):
    return x


def all_flag_values(flag: re.RegexFlag) -> List[re.RegexFlag]:
    return list(filter(None, map(flag.__and__, re.RegexFlag)))


@singledispatch
def to_regex_flag_chars(flags: AnyRegexFlags) -> str:
    raise TypeError("Can't interpret value of type {} as regex compilation flags".format(type(flags)))


@to_regex_flag_chars.register(type(None))
def _to_regex_flag_chars_none(flags: type(None)):
    return ''


@to_regex_flag_chars.register(re.RegexFlag)
def _to_regex_flag_chars_regex_flag(flag: re.RegexFlag):
    flags = all_flag_values(flag)
    return ''.join(_regex_flag_to_regex_flag_char[f] for f in flags)


@to_regex_flag_chars.register(str)
def _to_regex_flag_chars_flag_name(name: str):
    char = REGEX_FLAG_NAME_TO_REGEX_FLAG_CHAR.get(name.upper())
    if char is None:
        raise ValueError(
            "can't interpret string {} as a valid inline regex flag - must be a valid regex flag name, for example "
            "'UNICODE' or 'IGNORECASE' (see re.RegexFlag for more details)".format(repr(name))
        )
    return char


# handling this case could be interpreted as support for writing unreadable code, except that some libraries such as
# `regex` actually implement their flags as raw ints bound to global variable names
@to_regex_flag_chars.register(int)
def _to_regex_flag_chars_int(int_flag: int):
    return _to_regex_flag_chars_regex_flag(re.RegexFlag(int_flag))


@to_regex_flag_chars.register(CollectionABC)
def _to_regex_flag_chars_collection(flag_collection: Collection[AnyRegexFlag]):
    return ''.join(itertools.chain.from_iterable(map(to_regex_flag_chars, flag_collection)))


def to_rename_callable(renames: Union[RenameFunc, Mapping[str, str]]) -> RenameFunc:
    if callable(renames):
        return renames
    else:
        return _Rename(renames)


class _Rename:
    def __init__(self, renames: Mapping[str, str]):
        self.renames = dict(renames.items())
        self._hash = None

    def __call__(self, name: str) -> str:
        return self.renames.get(name, name)

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(frozenset(self.renames.items()))
        return self._hash

    def __eq__(self, other):
        return hash(self) == hash(other)
