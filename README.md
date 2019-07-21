# Regular expressions made readable

## Introduction

`bourbaki.regex` provides an interface for constructing arbitrarily complex 
regular expressions using standard Python syntax.

The goals of the package are the following:

  - allow the user to be as terse as possible while not sacrificing readability
  - support the full range of constructs available in the standard library regex engine (`re` module)
  - be extensible and modular to support more advanced constructs in the future, 
    as for instance provided by the [`regex`](https://pypi.org/project/regex/) module
  - handle minutiae such as handling backreferences (inferring the correct group index)
  - raise meaningful errors at compile time, such as named group collisions, nonexistent
    backreferences, and lookbehind assertions that are not fixed-length.

## Usage

There are a few base constructors from which all expression patterns can be built:

  - `bourbaki.regex.C`: Character class constructor.
    `C['a':'z', 'A-Z', '0':'9']` for instance is equivalent to the raw regular expression `r'[a-zA-Z0-9]`
  - `bourbaki.regex.L/Literal`: Literal string match.  This handles escaping special characters that are reserved for 
    regular expression syntax.
    For example `L('*foo[bar]*')` is equivalent to the raw regular expression `r'\*foo\[bar\]\*'`
    (note the '\' escapes)
  - `bourbaki.regex.If`: for construction of conditional patterns.
    For example, 
    ```python
    foo = L("foo")
    bar = L("bar")
    foobar = foo.optional + If(foo).then_(bar).else_("baz")
    ```
    `foobar` will now match `"foobar"` or `"baz"`, but not `"foo"`, since the pattern requires `"bar"` to follow 
    when `"foo"` is matched.
  - Special symbols, including:
    `START, END, ANYCHAR, StartString, EndString, Tab, Endline, BackSpace, CarriageReturn`
    `WordBoundary, WordInternal, WordChar, NonWordChar, Digit, NonDigit, Whitespace, NonWhitespace`,
    which are self-describing.
    
All other kinds of pattern can be constructed by the use of operators, method calls, or attribute accesses on previously 
constructed patterns.
`bourbaki.regex` tries to match python syntax to regex syntax as much as possible.
For example:

  - `L("foo") * 3` will match `"foofoofoo"`
  - `L("foo") + "bar"` will match `"foobar"` (note that the raw string `"bar"` is taken implicitly as a literal)
  - `L("foo")[1:2]` will match `"foo"` or `"foofoo"`
  - `L("foo")[1:3:2]` will match `"foo"` or `"foofoofoo"` (note that this makes what would otherwise be a somewhat 
    complex regex very simple
  - `L("foo") | "bar"` will match `"foo"` or `"bar"`
  - `C['0':'9']("a_numeral")` will result in a regex for whose matches calling the `.groupdict()` method 
    will yield a `dict` with the key `"a_numeral"`, i.e. this is a named group.
  - `C['0':'9']()` is as above, but the group isn't named. It will get a number in the resulting compiled
    pattern, and will be accessible by calling `.groups()` on any match object.
  - `L("foo").optional` matches `"foo"` or the empty string.  It is equivalent to `L("foo")[:1]`.
  - Lookaround assertions can be constructed with the `<<` and `>>` operators.
    The pattern which is matched "points to" the lookahead or lookbehind assertion.
  - For example, `L("foo") << "bar"` will match `"bar"`, but only in a string where it is preceded by `"foo"`.
  - Similarly, `L("foo") >> "bar"` will match `"foo"`, but only in a string where it is followed by `"bar'`
  - The `//` operator may take a raw string on the right which serves as a comment.
    It has no effect on the match behavior of the resulting pattern but will be present as a comment in the 
    compiled pattern.
  - `+ L("foo")` is an _atomic_ group. This means that once the regex engine matches it,
    it will never backtrack to before the match. Python's standard library regex engine does not 
    support this feature natively, but other modules such as [`regex`](https://pypi.org/project/regex/) do.
    `bourbaki.regex` constructs a standard python regex which _behaves_ as if it were atomic by using a backreference to 
    accomplish the same goal.
    To use `regex` or another conforming to python's `re` module API, but supporting 
    atomic groups natively, simply `import bourbaki.regex.base as bre`, and set 
    `bre.ATOMIC_GROUP_SUPPORT = True; bre.re = <your preferred regex module>`.
