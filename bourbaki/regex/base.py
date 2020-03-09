from typing import List, Dict, Mapping, Collection, Callable, Iterator, Iterable, Optional, Union
from copy import copy
import itertools
import functools
import operator
from warnings import warn

# change this to another module if you want to swap in another engine such as that provided by `regex`
import re

from .utils import utf_codepoint, to_char, escape_for_char_class, identity, to_rename_callable, to_regex_flag_chars
from .utils import (
    validate_positive_int,
    validate_range_arg,
    validate_groupref,
    validate_repetition_args,
    AnyRegexFlag,
    AnyRegexFlags,
    RenameFunc,
)
from .utils import (
    MAX_UNICODE_CODE_POINT, 
    CHAR_CLASS_RESERVED_CHARS, 
    REGEX_FLAG_CHAR_TO_REGEX_FLAG_NAME,
    ALL_NON_NEGATABLE_REGEX_FLAG_CHARS,
)


# change these if you want to swap in another engine such as that provided by `regex`
REQUIRE_FIX_LEN_LOOKBEHIND = True
REQUIRE_UNIQUE_GROUP_NAMES = True
ATOMIC_GROUP_SUPPORT = False

Pattern = type(re.compile(""))
Match = type(re.compile("").match(""))


class Regex:
    _require_group_for_quantification = True

    def compile(
        self, flags: Optional[Union[int, re.RegexFlag]] = re.UNICODE
    ) -> Pattern:
        self.validate()
        return re.compile(self.pattern, flags)

    @property
    def compiled(self):
        regex = self.compile()
        self.__dict__["compiled"] = regex
        return regex

    def match(self, string: str) -> Optional[Match]:
        """see `re.match`"""
        return self.compiled.match(string)

    def search(self, string: str) -> Optional[Match]:
        """see `re.search`"""
        return self.compiled.search(string)

    def fullmatch(self, string: str) -> Optional[Match]:
        """see `re.fullmatch`"""
        return self.compiled.fullmatch(string)

    def finditer(self, string: str) -> Iterable[Match]:
        """see `re.finditer`"""
        return self.compiled.finditer(string)

    def findall(self, string: str) -> List[str]:
        """see `re.findall`"""
        return self.compiled.findall(string)

    def sub(self, repl: str, string: str, count: int = 0) -> str:
        """see `re.sub`"""
        return self.compiled.sub(repl, string, count)

    def subn(self, repl: str, string: str, count: int):
        """see `re.subn`"""
        return self.compiled.subn(repl, string, count)

    def split(self, string: str, maxsplit: int) -> List[str]:
        """see `re.split`"""
        return self.compiled.split(string, maxsplit)

    @property
    def pattern(self) -> str:
        """The string literal pattern for this regex"""
        return self.pattern_in(None)

    def as_(self, name: Optional[str]) -> 'CaptureGroup':
        """Return a named group containing this regex with the given name"""
        return NamedGroup(self, name)

    def rename(self, renames: Union[RenameFunc, Mapping[str, str]]) -> 'Regex':
        """Rename named groups with either a mapping from current name to new name or a callable accepting
        current names and returning new names. If either mapping lookup fails to find the current name, it
        is left as-is. If the lookup values contain None or the callable returns None, the corresponding named
        groups will be converted into unnamed capture groups (int-indexed)"""
        return self

    def drop_names(self):
        """Return a regex with all named capture groups converted to unnamed capture groups"""
        return self.rename(lambda name: None)

    @property
    def captured(self) -> 'CaptureGroup':
        """Return a capture group containing this regex"""
        return CaptureGroup(self)

    @property
    def optional(self) -> 'RangeRepeated':
        """Return a regex matching this one zero or one times"""
        return ZeroOrOne(self)

    @property
    def zero_or_more(self) -> 'RangeRepeated':
        """Return a regex matching this one zero or more times"""
        return ZeroOrMore(self)

    @property
    def one_or_more(self) -> 'RangeRepeated':
        """Return a regex matching this one one or more times"""
        return OneOrMore(self)

    def with_options(self, *pos_flags: AnyRegexFlag) -> '_WithLocalFlags':
        """Return a copy of this regex with the given compile flags locally activated"""
        pos_flags = to_regex_flag_chars(pos_flags)
        return _WithLocalFlags(self, pos_flags, None)

    def without_options(self, *neg_flags: AnyRegexFlag) -> '_WithLocalFlags':
        """Return a copy of this regex with the given compile flags locally deactivated"""
        neg_flags = to_regex_flag_chars(neg_flags)
        return _WithLocalFlags(self, None, neg_flags)

    def comment(self, comment: str):
        """Return this regex with an added comment at the end"""
        return self + Comment(comment)

    def pattern_in(self, regex: Optional['Regex'] = None) -> str:
        """Required for literal backreferences; they're the only classes that need to know their index/name
        in the containing regex. This method should in general recurse on subregexes"""
        raise NotImplementedError("pattern is not defined for instance {} of type {}".format(repr(self), type(self)))

    def pattern_for_quantification(self, regex: Optional['Regex'] = None):
        if self._require_group_for_quantification:
            return "(?:{})".format(self.pattern_in(regex))
        return self.pattern_in(regex)

    @property
    def subregexes(self) -> Iterator['Regex']:
        """Iterate over all sub-regexes contained in this one"""
        yield from ()

    @property
    def capture_groups(self) -> Iterator['CaptureGroup']:
        """Iterate over all capture groups contained in this one (named and unnamed)"""
        return (
            regex
            for regex in self._depth_first_walk()
            if isinstance(regex, (CaptureGroup, NamedGroup))
        )

    @property
    def named_groups(self) -> Iterator['NamedGroup']:
        """Iterate over all named capture groups contained in this one"""
        return (
            regex for regex in self._depth_first_walk() if isinstance(regex, NamedGroup)
        )

    @property
    def backrefs(self) -> Iterator['_BackRef']:
        """Iterate over all back-references to previous groups contained in this regex"""
        return (
            regex for regex in self._depth_first_walk() if isinstance(regex, _BackRef)
        )

    def validate(self) -> 'Regex':
        """Check for:
        - repeated names in named groups
        - backrefs to groups which haven't been encountered yet
        - variable-length lookbehind assertions"""

        named_groups = {}
        numbered_groups = {}
        group_ids = {}
        last_group_index = 0
        for group in self._depth_first_walk():
            if isinstance(group, _BackRef):
                if isinstance(group, _LiteralBackref):
                    if id(group.groupref) not in group_ids:
                        raise IndexError(
                            "group {} is literal backref to a group that does not appear prior in pattern {}".format(
                                repr(group), repr(self)
                            )
                        )
                elif isinstance(group, NamedBackref):
                    if group.groupref not in named_groups:
                        raise IndexError(
                            "group {} is named backref to group with name '{}' which doesn't appear "
                            "prior in pattern {}".format(
                                group, group.groupref, repr(self)
                            )
                        )
                elif isinstance(group, IntBackref):
                    if group.groupref > last_group_index:
                        raise IndexError(
                            "group {} is integer backref to group at index {} but only {} capture groups "
                            "appear prior in pattern {}".format(
                                group, group.groupref, last_group_index, repr(self)
                            )
                        )
            elif isinstance(group, NamedGroup):
                if group.name in named_groups:
                    msg = ("named group {} uses name '{}' which appears previously in pattern {}"
                           .format(group, group.name, repr(self)))
                    if REQUIRE_UNIQUE_GROUP_NAMES:
                        raise NameError(msg)
                    else:
                        warn(msg)

                group_ids[id(group)] = group
                named_groups[group.name] = group
                last_group_index += 1
                numbered_groups[last_group_index] = group
            elif isinstance(group, CaptureGroup):
                group_ids[id(group)] = group
                last_group_index += 1
                numbered_groups[last_group_index] = group
            elif REQUIRE_FIX_LEN_LOOKBEHIND and isinstance(group, Lookbehind):
                if not group.assertion_is_fixed_len(named_groups, numbered_groups):
                    raise ValueError(
                        "lookbehind assertion in pattern '{}' is not fixed-length".format(
                            group
                        )
                    )

        return self

    def debug_match(self, string: str, print_failures: bool = False):
        match = None
        for regex in self.partial_regexes(debug=True):
            match = regex.match(string)
            if print_failures and match is None:
                print("FAIL: '{}'\n".format(regex))
            elif match:
                print("MATCH IN '{}':\n" "    '{}'\n".format(regex, match.group()))
        return match

    def _depth_first_walk(self) -> Iterator['Regex']:
        yield self
        for regex in self.subregexes:
            yield from regex._depth_first_walk()

    def partial_regexes(self, debug: bool = False) -> Iterator['Regex']:
        yield self

    def __str__(self):
        return self.pattern

    def __getitem__(self, item: slice):
        msg = "can only index Regex instances with a single integer slice; got {}"
        if isinstance(item, tuple):
            if len(item) != 1:
                raise IndexError(msg.format(repr(item)))
            item = item[0]
        if not isinstance(item, slice):
            raise IndexError(msg.format(repr(item)))

        return RangeRepeated(self, item.start, item.stop, item.step)

    def __mul__(self, num: int) -> 'Repeated':
        return Repeated(self, num)

    def __floordiv__(self, comment: str) -> 'Sequence':
        return self.comment(comment)

    def __add__(self, other: Union['Regex', str]) -> 'Sequence':
        return Sequence(self, other)

    def __radd__(self, other: Union['Regex', str]) -> 'Sequence':
        return Sequence(other, self)

    def __or__(self, other: Union['Regex', str]) -> 'Alternation':
        return Alternation(self, other)

    def __ror__(self, other: Union['Regex', str]) -> 'Alternation':
        return Alternation(other, self)

    def __rshift__(self, other: Union['Regex', str]) -> 'Lookahead':
        return Lookahead(self, other)

    def __rrshift__(self, other: Union['Regex', str]) -> 'Lookahead':
        return Lookahead(other, self)

    def __lshift__(self, other: Union['Regex', str]) -> 'Lookbehind':
        return Lookbehind(self, other)

    def __rlshift__(self, other: Union['Regex', str]) -> 'Lookbehind':
        return Lookbehind(other, self)

    def __and__(self, other: AnyRegexFlags):
        return self.with_options(other)

    def __sub__(self, other: AnyRegexFlags):
        return self.without_options(other)

    def __neg__(self) -> '_NegativeAssertion':
        return _NegativeAssertion(self)

    def __pos__(self) -> 'Regex':
        return Atomic(self)

    def __invert__(self):
        return AnythingBut(self)

    def __call__(self, name: Optional[str] = None) -> 'CaptureGroup':
        if name is None:
            return CaptureGroup(self)
        return NamedGroup(self, name)

    @property
    def atomic(self) -> 'Regex':
        return Atomic(self)

    @property
    def len(self) -> Optional[int]:
        return None


class _WithOneSubRegex(Regex):
    _regex = None

    @property
    def subregexes(self):
        yield self._regex

    @property
    def len(self):
        return self._regex.len

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> '_WithOneSubRegex':
        return type(self)(self._regex.rename(renames))


class _SpecialClass(Regex):
    _require_group_for_quantification = False

    def __init__(self, char: str):
        self.char = char

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return r"\{}".format(self.char)

    @property
    def len(self):
        return 0


class _SpecialSymbol(Regex):
    def __init__(self, symbol: str, len_=0):
        self.symbol = symbol
        self._len = len_

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return self.symbol

    @property
    def len(self):
        return self._len


class _AcceptableInCharClass(Regex):
    _require_group_for_quantification = False

    def __or__(self, other):
        if isinstance(other, _AcceptableInCharClass):
            return CharClass(self, other)
        other = to_regex(other)
        if isinstance(other, Literal) and len(other.string) == 1:
            return CharClass(self, other.string)
        return super().__or__(other)

    def __ror__(self, other):
        other = to_regex(other)
        if isinstance(other, _AcceptableInCharClass) or (isinstance(other, Literal) and len(other.string) == 1):
            return CharClass(self, other.string)
        return super().__ror__(other)

    @property
    def pattern_in_char_class(self):
        raise NotImplementedError()

    @property
    def len(self):
        return 1


class _SpecialClassAcceptableInCharClass(_SpecialClass, _AcceptableInCharClass):
    # repeated def from second parent class in case of diamond problem
    __ror__ = _AcceptableInCharClass.__ror__

    def __invert__(self):
        return NegatedCharClass(self)

    @property
    def pattern_in_char_class(self):
        return self.pattern

    @property
    def len(self):
        return 1


class Comment(Regex):
    def __init__(self, comment: str):
        if not isinstance(comment, str):
            raise TypeError("comment must be a string; got {}".format(type(comment)))
        self.comment = comment

    def partial_regexes(self, debug: bool = False):
        if debug:
            print("COMMENT: {}\n".format(self.comment))
        yield from ()

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return "(?#{})".format(self.comment)

    @property
    def len(self):
        return 0


class _WithLocalFlags(_WithOneSubRegex):
    def __init__(
        self, regex: Regex,
        pos_flags: Optional[Collection[str]] = None,
        neg_flags: Optional[Collection[str]] = None,
    ):
        pos_flags = set(pos_flags or ())
        neg_flags = set(neg_flags or ())
        bad_neg_flags = neg_flags.intersection(ALL_NON_NEGATABLE_REGEX_FLAG_CHARS)
        if bad_neg_flags:
            raise ValueError(
                "can't negate regex flags {}; at least one must always be present. Apply one to negate the others"
                .format([REGEX_FLAG_CHAR_TO_REGEX_FLAG_NAME[c] for c in bad_neg_flags])
            )
        mutually_exclusive_pos_flags = pos_flags.intersection(ALL_NON_NEGATABLE_REGEX_FLAG_CHARS)
        if len(mutually_exclusive_pos_flags) > 1:
            raise ValueError(
                "can't simultaneously specify flags {}; they are mutually exclusive"
                .format([REGEX_FLAG_CHAR_TO_REGEX_FLAG_NAME[c] for c in mutually_exclusive_pos_flags])
            )
        overlap = pos_flags.intersection(neg_flags)

        self.pos_flags = frozenset(pos_flags).difference(overlap)
        self.neg_flags = frozenset(neg_flags).difference(overlap)
        self._regex = to_regex(regex)

    @property
    def pattern(self) -> str:
        flag_str = (''.join(sorted(self.pos_flags)) + '-' + ''.join(sorted(self.neg_flags))).rstrip('-')
        return "(?{}:{})".format(flag_str, self._regex.pattern)

    def with_options(self, *pos_flags: AnyRegexFlag) -> '_WithLocalFlags':
        pos_flags = to_regex_flag_chars(pos_flags)
        return _WithLocalFlags(self._regex, self.pos_flags.union(pos_flags), self.neg_flags)

    def without_options(self, *neg_flags: AnyRegexFlag) -> '_WithLocalFlags':
        neg_flags = to_regex_flag_chars(neg_flags)
        return _WithLocalFlags(self._regex, self.pos_flags, self.neg_flags.union(neg_flags))

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> '_WithLocalFlags':
        return type(self)(self._regex.rename(renames), self.pos_flags, self.neg_flags)


class _NegativeAssertion(_WithOneSubRegex):
    def __init__(self, regex: Regex):
        self._regex = regex

    def __neg__(self):
        return self._regex

    def comment(self, comment: str):
        new = copy(self)
        new._regex = self._regex.comment(comment)
        return new


def AnythingBut(regex: Regex):
    """Matches any string except those matched by the supplied regex"""
    return Lookahead(Literal(""), _NegativeAssertion(regex)) + ANYCHAR[:]


class Lookahead(Regex):
    def __init__(self, regex: Regex, ahead: Regex):
        self._regex = to_regex(regex)
        self.ahead = to_regex(ahead)

    @property
    def subregexes(self):
        yield from (self._regex, self.ahead)

    def partial_regexes(self, debug: bool = False):
        yield from self._regex.partial_regexes(debug)
        for r in self.ahead.partial_regexes(debug):
            yield Lookahead(self._regex, r)

    def pattern_in(self, regex: Optional[Regex] = None):
        regex = regex or self
        if isinstance(self.ahead, _NegativeAssertion):
            assertion, ahead = '!', self.ahead._regex
        else:
            assertion, ahead = '=', self.ahead

        return "{}(?{}{})".format(
            self._regex.pattern_in(regex), assertion, ahead.pattern_in(regex)
        )

    @property
    def len(self):
        return self._regex.len

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'Lookahead':
        rename = to_rename_callable(renames)
        return type(self)(self._regex.rename(rename), self.ahead.rename(rename))


class Lookbehind(Regex):
    def __init__(self, behind: Regex, regex: Regex):
        self._regex = to_regex(regex)
        self.behind = to_regex(behind)

    @property
    def subregexes(self):
        yield from (self.behind, self._regex)

    def partial_regexes(self, debug: bool = False):
        empty = Literal("")
        for r in self.behind.partial_regexes(debug):
            yield Lookbehind(r, empty)
        for r in self._regex.partial_regexes(debug):
            yield Lookbehind(self.behind, r)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        if isinstance(self.behind, _NegativeAssertion):
            assertion, behind = '!', self.behind._regex
        else:
            assertion, behind = '=', self.behind

        return "(?<{}{}){}".format(
            assertion, behind.pattern_in(regex), self._regex.pattern_in(regex)
        )

    @property
    def len(self):
        return self._regex.len

    def assertion_is_fixed_len(
        self,
        named_groups: Optional[Dict[str, Regex]] = None,
        numbered_groups: Optional[Dict[int, Regex]] = None,
    ) -> bool:
        len_ = self.behind.len

        if len_ is None:
            behind = None
            if named_groups is not None and isinstance(self.behind, NamedBackref):
                behind = named_groups.get(self.behind.name)
            elif numbered_groups is not None and isinstance(self.behind, IntBackref):
                behind = numbered_groups.get(self.behind.n)

            if behind is not None:
                return behind.len is not None
            return False
        else:
            return True

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'Lookbehind':
        rename = to_rename_callable(renames)
        return type(self)(self.behind.rename(rename), self._regex.rename(rename))


class _Atomic(_WithOneSubRegex):
    def __init__(self, regex: Regex):
        self._regex = regex

    def pattern_in(self, regex: Optional['Regex'] = None):
        regex = regex or self
        return "(?>{})".format(self._regex.pattern_in(regex))


def Atomic(regex: Regex) -> Regex:
    """An atomic group, i.e. one which, upon matching, is permanently consumed; no later backtracking which would
    negate the contents of the match can be performed. The Python `re` module doesn't support this natively but it
    can be expressed with lookbehind assertions"""
    if ATOMIC_GROUP_SUPPORT:
        return _Atomic(regex)
    group = CaptureGroup(regex)
    return Lookahead(Literal(""), group) + BackRef(group)


class Literal(Regex):
    def __init__(self, string: str):
        if not isinstance(string, str):
            raise TypeError(
                "regex literals take only a string arg; got {}".format(type(string))
            )
        self.string = string

    def partial_regexes(self, debug: bool = False):
        for i in range(1, len(self.string) + 1):
            yield Literal(self.string[:i])

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return re.escape(self.string)

    def pattern_for_quantification(self, regex: Optional['Regex'] = None):
        if len(self.string) == 1:
            return re.escape(self.string)
        return super().pattern_for_quantification(regex)

    @property
    def len(self):
        return len(self.string)


class _CaptureGroupMixin:
    def __init__(self):
        self._rename_cache = {}

    def _rename(self, renames):
        raise NotImplementedError()

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'CaptureGroup':
        # there _might_ be some LiteralBackreference holding a reference to `self` and we want to be able to tell it
        # where the renamed `self` went to when `self` is renamed
        rename = to_rename_callable(renames)
        renamed = self._rename_cache.get(rename)
        if renamed is None:
            renamed = self._rename(rename)
            self._rename_cache[rename] = renamed

        return renamed


class CaptureGroup(_CaptureGroupMixin, _WithOneSubRegex):
    _require_group_for_quantification = False

    def _rename(self, renames):
        return _WithOneSubRegex.rename(self, renames)

    def __init__(self, regex: Regex):
        super().__init__()
        self._regex = to_regex(regex)

    def partial_regexes(self, debug: bool = False):
        if debug:
            print("CAPTURE GROUP\n")
        for r in self._regex.partial_regexes(debug):
            yield CaptureGroup(r)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        return "({})".format(self._regex.pattern_in(regex))


class NamedGroup(_CaptureGroupMixin, _WithOneSubRegex):
    _require_group_for_quantification = False

    def __init__(self, regex: Regex, name: str):
        super().__init__()
        self._regex = to_regex(regex)
        if not isinstance(name, str):
            raise TypeError(
                "named group references must be strings; got {}".format(type(name))
            )
        self.name = validate_groupref(name)

    def partial_regexes(self, debug: bool = False):
        if debug:
            print("NAMED GROUP: {}\n".format(self.name))
        for r in self._regex.partial_regexes(debug):
            yield NamedGroup(r, self.name)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        return "(?P<{}>{})".format(self.name, self._regex.pattern_in(regex))

    def _rename(self, renames):
        rename = to_rename_callable(renames)
        new_name = rename(self.name)
        if new_name is None:
            return CaptureGroup(self._regex.rename(rename))
        return type(self)(self._regex.rename(rename), new_name)


class _Flattening(Regex):
    regexes = ()

    def __init__(self, *regexes: Regex):
        self.regexes = tuple(
            itertools.chain.from_iterable(map(self._to_regexes, regexes))
        )

    @classmethod
    def _to_regexes(cls, other):
        if isinstance(other, cls):
            return other.regexes
        return (to_regex(other),)

    @property
    def subregexes(self):
        yield from self.regexes

    def partial_regexes(self, debug: bool = False):
        cls = type(self)
        rs = []
        for r in self.regexes:
            for s in r.partial_regexes(debug):
                yield cls(*rs, s)
            rs.append(r)

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> '_Flattening':
        rename = to_rename_callable(renames)
        return type(self)(*(r.rename(rename) for r in self.regexes))


class Sequence(_Flattening):
    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        return "".join(r.pattern_in(regex) for r in self.regexes)

    @property
    def len(self):
        len_ = 0
        for l in map(operator.attrgetter("len"), self.regexes):
            if l is None:
                return None
            len_ += l
        return len_


class Alternation(_Flattening):
    _require_group_for_quantification = False

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        if regex is None:
            template, regex = "{}", self
        else:
            template = "(?:{})"
        return template.format("|".join(r.pattern_in(regex) for r in self.regexes))

    @property
    def len(self):
        len_ = None
        for l in map(operator.attrgetter("len"), self.regexes):
            if l is None:
                return None
            if len_ is None:
                len_ = l
            elif l != len_:
                return None


def RangeRepeated(
    regex: Regex,
    start: Optional[int] = None,
    stop: Optional[int] = None,
    step: Optional[int] = None,
) -> Regex:
    start, stop, step = validate_repetition_args(start, stop, step)
    infinite = stop is None
    multiples = step != 1

    if not multiples:
        if infinite and start == 0:
            return ZeroOrMore(regex)
        elif infinite and start == 1:
            return OneOrMore(regex)
        elif start == 0 and stop == 1:
            return ZeroOrOne(regex)
        elif start == stop:
            return regex * start
        return _RangeRepeating(regex, start, stop)
    else:
        subpattern = regex * step
        if start == 0:
            if infinite:
                return ZeroOrMore(subpattern)
            return _RangeRepeating(subpattern, 0, stop // step)

        init = Repeated(regex, start)
        if infinite:
            return init + ZeroOrMore(subpattern)
        return init + _RangeRepeating(subpattern, 0, (stop - start) // step)


class _SpecialRepeating(_WithOneSubRegex):
    _repetition_symbol = None

    def __init__(self, regex: Regex):
        self._regex = to_regex(regex)

    def partial_regexes(self, debug: bool = False):
        yield from self._regex.partial_regexes(debug)
        yield self

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        return self._regex.pattern_for_quantification(regex) + self._repetition_symbol

    @property
    def len(self):
        # these are all variable-length
        return None


class ZeroOrMore(_SpecialRepeating):
    _repetition_symbol = '*'


class OneOrMore(_SpecialRepeating):
    _repetition_symbol = '+'


class ZeroOrOne(_SpecialRepeating):
    _repetition_symbol = '?'


class _RangeRepeating(_WithOneSubRegex):
    start = None
    stop = None

    def __init__(
        self, regex: Regex, start: Optional[int] = None, stop: Optional[int] = None
    ):
        self._regex = to_regex(regex)
        self.start = start
        self.stop = stop

    def partial_regexes(self, debug: bool = False):
        if self.start not in (0, None):
            yield from Repeated(self._regex, self.start).partial_regexes(debug)
        yield self

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        base = self._regex.pattern_for_quantification(regex)
        return "{}{{{},{}}}".format(base, self.start or 0, self.stop or "")

    @property
    def len(self):
        len_ = self._regex.len
        if len_ is None:
            return None
        if self.start == self.stop:
            return self.start * len_
        return None

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> '_RangeRepeating':
        return type(self)(self._regex.rename(renames), self.start, self.stop)


class Repeated(_WithOneSubRegex):
    def __init__(self, regex: Regex, n: int):
        self.n = validate_positive_int(n, "fixed repetition counts")
        self._regex = to_regex(regex)

    def partial_regexes(self, debug: bool = False):
        rs = list(self._regex.partial_regexes(debug))[:-1]
        yield from rs
        for i in range(1, self.n):
            rep = Repeated(self._regex, i)
            yield rep
            for r in rs:
                yield rep + r
        yield self

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        base = self._regex.pattern_for_quantification(regex)
        return "{}{{{}}}".format(base, self.n)

    def __mul__(self, n: int) -> 'Repeated':
        return Repeated(self._regex, self.n * n)

    @property
    def len(self):
        len_ = self._regex.len
        if len_ is None:
            return None
        return len_ * self.n

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'Repeated':
        return type(self)(self._regex.rename(renames), self.n)


class _CharSetOrRange(_AcceptableInCharClass):
    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return "[{}]".format(self.pattern_in_char_class)


class CharSet(_CharSetOrRange):
    def __init__(self, *chars: str):
        chars = (to_char(c) if isinstance(c, int) else c for c in chars)
        chars = set(itertools.chain.from_iterable(chars))
        special_chars = []

        for c in CHAR_CLASS_RESERVED_CHARS:
            if c in chars:
                chars.remove(c)
                special_chars.append(c)

        self.chars = tuple(sorted(chars))
        self.special_chars = tuple(special_chars)

    def __or__(self, other):
        if isinstance(other, CharSet):
            return CharSet(*self, *other)
        other = to_regex(other)
        if isinstance(other, Literal) and len(other.string) == 1:
            return CharSet(*self, other.string)
        return super().__or__(other)

    def __ror__(self, other):
        other = to_regex(other)
        if isinstance(other, Literal) and len(other.string) == 1:
            return CharSet(*self, other.string)
        return super().__ror__(other)

    @property
    def pattern_in_char_class(self):
        return "".join(map(escape_for_char_class, self))

    def __iter__(self):
        return itertools.chain(self.special_chars, self.chars)

    def __contains__(self, char):
        try:
            c = to_char(char)
        except ValueError:
            raise ValueError(
                "can only check for containment of single character in {}; got {}".format(
                    type(self), char
                )
            )
        except TypeError:
            raise TypeError(
                "can only check for int or single character in {}; got {}".format(
                    type(self), type(char)
                )
            )
        else:
            return c in self.chars or c in self.special_chars


class CharRange(_CharSetOrRange):
    def __init__(self, start, stop):
        start, stop = map(utf_codepoint, (start, stop))
        if start > stop:
            raise ValueError(
                "codepoint {} of start char {} is greater than codepoint {} of end char {}".format(
                    start, chr(start), stop, chr(stop)
                )
            )
        self.start = start
        self.stop = stop

    @property
    def pattern_in_char_class(self):
        return "{}-{}".format(
            escape_for_char_class(chr(self.start)),
            escape_for_char_class(chr(self.stop)),
        )

    def __or__(self, other):
        if (
            isinstance(other, CharRange)
            and ((self.stop + 1) >= other.start)
            or ((other.stop + 1) >= self.start)
        ):
            return CharRange(min(self.start, other.start), max(self.stop, other.stop))
        if (
            isinstance(other, Literal)
            and len(other.string) == 1
            and other.string in self
        ):
            return self
        return super().__or__(other)

    def __ror__(self, other):
        other = to_regex(other)
        if (
            isinstance(other, Literal)
            and len(other.string) == 1
            and other.string in self
        ):
            return self
        return super().__ror__(other)

    def __lt__(self, other):
        if isinstance(other, CharRange):
            return self.start < other.start
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, CharRange):
            return self.start > other.start
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, CharRange):
            return self.start == other.start and self.stop == other.stop
        return False

    def __iter__(self):
        return map(chr, range(self.start, self.stop + 1))

    def __contains__(self, char):
        try:
            o = utf_codepoint(char)
        except ValueError:
            raise ValueError(
                "can only check for containment of single character in {}; got {}".format(
                    type(self), char
                )
            )
        except TypeError:
            raise TypeError(
                "can only check for int or single character in {}; got {}".format(
                    type(self), type(char)
                )
            )
        else:
            return self.start <= o <= self.stop


class CharClassMixin:
    _negated = False

    def __init__(self, *contents):
        contents = [CharSet(c) if isinstance(c, (str, int)) else c for c in contents]
        bad = [c for c in contents if not isinstance(c, _AcceptableInCharClass)]
        if bad:
            raise TypeError(
                "only types {} are acceptable as arguments to CharClass; {} are not".format(
                    ", ".join(
                        c.__name__ for c in _AcceptableInCharClass.__subclasses__()
                    ),
                    tuple(bad),
                )
            )

        specials, ranges, charset = [], [], set()
        for chars in contents:
            if isinstance(chars, CharSet):
                charset.update(chars)
            elif isinstance(chars, CharRange):
                ranges.append(chars)
            elif isinstance(chars, _SpecialClassAcceptableInCharClass):
                specials.append(chars)
            elif isinstance(chars, CharClass):
                charset.update(chars.charset)
                specials.extend(chars.specials)
                ranges.extend(chars.ranges)

        self.charset = CharSet(*charset)
        self.specials = tuple(specials)
        self.ranges = tuple(sorted(ranges, key=operator.attrgetter("start")))

    def pattern_in(self, regex: Regex) -> str:
        template = "[^{}{}]" if self._negated else "[{}{}]"
        return template.format(
            self.charset.pattern_in_char_class,
            "".join(r.pattern_in_char_class for r in itertools.chain(self.specials, self.ranges)),
        )


class CharClass(CharClassMixin, _AcceptableInCharClass):
    def __iter__(self):
        memo = set(self.charset)
        yield from sorted(self.charset)
        for chars in self.ranges:
            for c in chars:
                if c not in memo:
                    yield c
                    memo.add(c)

    def __invert__(self):
        return NegatedCharClass(self)

    def __contains__(self, char: Union[int, str]):
        return char in self.charset or any(char in r for r in self.ranges)


class NegatedCharClass(CharClassMixin, Regex):
    _negated = True

    def __iter__(self):
        in_charclass = functools.partial(CharClass.__contains__, self)
        yield from itertools.filterfalse(
            in_charclass, map(chr, range(0, MAX_UNICODE_CODE_POINT + 1))
        )

    def __invert__(self):
        return CharClass(self.charset, *self.ranges)

    def __contains__(self, char: Union[int, str]) -> bool:
        return not CharClass.__contains__(self, char)


class _BackRef(Regex):
    _require_group_for_quantification = False
    groupref = None

    def group_in(self, regex: Regex) -> Union[int, str]:
        raise NotImplementedError()


class NamedBackref(_BackRef):
    def __init__(self, groupref: str):
        self.groupref = validate_groupref(groupref)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return "(?P={})".format(self.groupref)

    def group_in(self, regex: Regex) -> str:
        return self.groupref

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'NamedBackref':
        rename = to_rename_callable(renames)
        new_name = rename(self.groupref)
        if new_name is None:
            raise ValueError(
                "Can't drop name of group {}; there are named backreferences to it!".format(repr(self.groupref)),
            )
        return type(self)(new_name)


class IntBackref(_BackRef):
    def __init__(self, groupref: int):
        self.groupref = validate_groupref(groupref)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        return r"\{}".format(self.groupref)

    def group_in(self, regex: Regex) -> int:
        return self.groupref


class _LiteralBackref(_BackRef):
    ref_cls = None

    def __init__(self, group: CaptureGroup):
        self.groupref = group

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        if regex is None:
            raise TypeError(
                "backreferences to literal Regex objects only have patterns in the context of a larger "
                "regex containing the groups they reference"
            )
        return self.ref_cls(self.group_in(regex)).pattern

    @property
    def len(self):
        return self.groupref.len

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> '_LiteralBackref':
        # the rename call on groupref is cached - when it is called elsewhere by another referencing liter backref or
        # by the groupref itself, with the same renames it will return the same literal renamed regex object
        return type(self)(self.groupref.rename(renames))


class LiteralUnnamedBackref(_LiteralBackref):
    ref_cls = IntBackref

    def group_in(self, regex: Regex) -> int:
        for i, r in enumerate(regex.capture_groups, 1):
            if r is self.groupref:
                return i
        raise IndexError(
            "the group {} is not present in the regex {} and thus is invalid as a backreference there".format(
                repr(self.groupref), repr(regex)
            )
        )


class LiteralNamedBackref(_LiteralBackref):
    ref_cls = NamedBackref

    def group_in(self, regex: Regex) -> str:
        for r in regex.named_groups:
            if r is self.groupref:
                return r.name
        raise IndexError(
            "the group {} is not present in the regex {} and thus is invalid as a backreference there".format(
                repr(self.groupref), repr(regex)
            )
        )


class Conditional(Regex):
    _require_group_for_quantification = False

    def __init__(
        self,
        if_: Union[int, str, NamedGroup, CaptureGroup, _BackRef],
        then_: Regex,
        else_: Regex = Literal(''),
    ):
        self.backref = BackRef(if_)
        self._then = to_regex(then_)
        self._else = to_regex(else_)

    def pattern_in(self, regex: Optional[Regex] = None) -> str:
        regex = regex or self
        return "(?({}){}|{})".format(
            self.backref.group_in(regex),
            self._then.pattern_in(regex),
            self._else.pattern_in(regex),
        )

    @property
    def subregexes(self):
        yield from (self.backref, self._then, self._else)

    @property
    def len(self):
        thenlen = self._then.len
        if thenlen is None:
            return None
        elselen = self._else.len
        if thenlen == elselen:
            return thenlen
        return None

    def rename(self, renames: Union[Callable[[str], str], Mapping[str, str]]) -> 'Conditional':
        rename = to_rename_callable(renames)
        renamed_ref = self.backref.rename(rename).groupref
        return type(self)(renamed_ref, self._then.rename(rename), self._else.rename(rename))


class If:
    def __init__(self, groupref: Union[int, str, NamedGroup, _BackRef]):
        self.ref = groupref

    def then_(self, regex: Regex) -> '_Then':
        return _Then(self.ref, regex)


class _Then(Conditional):
    def else_(self, else_: Regex) -> Conditional:
        return Conditional(self.backref, self._then, else_)


@functools.singledispatch
def BackRef(capture_group_or_ref: Union[int, str, CaptureGroup]) -> _BackRef:
    raise TypeError(
        "can't form backreference to type {}, only capture groups".format(
            type(capture_group_or_ref)
        )
    )


BackRef.register(CaptureGroup)(LiteralUnnamedBackref)

BackRef.register(NamedGroup)(LiteralNamedBackref)

BackRef.register(int)(IntBackref)

BackRef.register(str)(NamedBackref)

BackRef.register(_BackRef)(identity)


@functools.singledispatch
def to_regex(x) -> Regex:
    raise NotImplementedError("to_regex is not defined for type {}".format(type(x)))


@to_regex.register(str)
def to_regex_literal(s: str) -> Literal:
    return Literal(s)


@to_regex.register(int)
def to_regex_char_from_codepoint(i: int) -> Literal:
    return Literal(chr(i))


to_regex.register(Regex)(identity)


@functools.singledispatch
def _to_charset(x):
    return x


_to_charset.register(int)(CharSet)

_to_charset.register(str)(CharSet)


@_to_charset.register(tuple)
def _to_char_range(start_stop):
    return CharRange(*start_stop)


@functools.singledispatch
def _validate_charclass_arg(arg):
    raise ValueError("Arguments to C[...] must be str, int, slice or previously-constructed "
                     "CharClass/CharSet/CharRange instances; got {}".format(type(arg)))


_validate_charclass_arg.register(int)(identity)

_validate_charclass_arg.register(str)(identity)

_validate_charclass_arg.register(_AcceptableInCharClass)(identity)

_validate_charclass_arg.register(slice)(validate_range_arg)


class _CharClassConstructor:
    def __getitem__(self, item):
        if not isinstance(item, tuple):
            item = (item,)
        args = map(_validate_charclass_arg, item)
        return CharClass(*map(_to_charset, args))


C = _CharClassConstructor()

L = Literal

StartString, WordBoundary, WordInternal, EndString = map(_SpecialClass, "AbBZ")

Digit, NonDigit, Whitespace, NonWhitespace, WordChar, NonWordChar, Tab, Endline, BackSpace, CarriageReturn = map(
    _SpecialClassAcceptableInCharClass, "dDsSwWtnbr"
)

START, END, ANYCHAR = _SpecialSymbol("^", 0), _SpecialSymbol("$", 0), _SpecialSymbol(".", 1)
