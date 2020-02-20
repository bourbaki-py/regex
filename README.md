[![Coverage Status](https://coveralls.io/repos/github/bourbaki-py/regex/badge.svg?branch=master)](https://coveralls.io/github/bourbaki-py/regex?branch=master)
[![Build Status](https://travis-ci.org/bourbaki-py/regex.svg?branch=master)](https://travis-ci.org/bourbaki-py/regex)

# Regular expressions made readable

## Introduction

`bourbaki.regex` provides an interface for constructing arbitrarily complex 
regular expressions using standard Python syntax.

The goals of the package are the following:

  - allow the user to be as terse as possible while not sacrificing readability
  
  - support the full range of constructs available in the standard library regex engine (`re` module)
  
  - be extensible and modular to support more advanced constructs in the future, 
    as for instance provided by the [`regex`](https://pypi.org/project/regex/) module
  
  - treat python string literals as literal strings to be matched wherever possible, obviating the need for special 
    constructors
  
  - handle tedious minutiae such escaping special characters in literals and inferring the correct group index for  
    backreferences, allowing the user to specify them as literal references to previously constructed 
    `bourbaki.regex.Regex` objects
  
  - raise meaningful errors at compile time, such as named group collisions, nonexistent
    backreferences, and lookbehind assertions that are not fixed-length


#### Basic regex constructors

There are a few base constructors from which all expression patterns can be built.
Each of them, and all expressions involving them in the sections below, result in instances of `bourbaki.regex.Regex`,
which has the usual methods of a compiled python regex - `.match`, `.search`, `.fullmatch`, `.findall`, `.finditer`, 
`.sub`, `.subn`, `.split` - as well as the attribute `.pattern`.

To compile a pattern with regex flags (i.e. `re.IGNORECASE`), pass them to the `.compile` method.
The result will be a usual python regex.

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
constructed patterns, as detailed below.


#### Repetition

The `*` (multiplication) operator expresses a fixed number of repetitions of a pattern.
This deviates from raw regex syntax but the multiplication operator matches python string semantics.

The `[]` (`__getitem__`) construct is also used to express repetition over a range of copies.
This construct closely resembles its raw regex curly-brace counterpart, while adding some functionality 
and matching the python slice semantics in expressing numeric ranges (though the upper bound is always included, as in 
raw regex).

Common repetition requirements are expressible via the `.one_or_more`, `.zero_or_more`, and `.optional` attributes.

  - `L("foo") * 3` will match `"foofoofoo"`.
  
  - `L("foo")[1:2]` will match `"foo"` or `"foofoo"`.
  
  - `L("foo")[:]` is equivalent to `L("foo").zero_or_more` and matches any number of copies of "foo", including 
    the empty string.
    
  - `L("foo")[1:]` is equivalent to `L("foo").one_or_more` and matches any number of copies of "foo", requiring at 
    least one.
    
  - `L("foo")[:1]` is equivalent to `L("foo").optional` and matches `"foo"` or the empty string.
  
  - `L("foo")[1:5:2]` will match 1, 3 or 5 copies of `"foo"` (note that this makes what would otherwise be a somewhat 
    complex regex very simple.


#### Alternation

The `|` (pipe/bitwise or) operator is used to express alternation, as it is in raw regex.

  - `L("foo") | "bar"` will match `"foo"` or `"bar"`.
  
  - When both sides of the operator are character classes, the pipe operator results in another character class matching 
    the union of thier contents. This is semantically the same as alternation in a regex, but results in a more concise 
    compiled pattern. For example, `C['a-z'] | C['0':'9']` compiles to the pattern `'[a-z0-9]'` rather than `'[a-z]|[0-9]'`


#### Concatenation

The binary `+` (addition) operator is used to express concatenation of patterns.
This breaks with raw regex syntax (where concatenation is implicit in adjacent patterns) but captures the usual python 
string semantics.

  - `L("foo") + "bar"` will match `"foobar"` (note that the raw string `"bar"` is taken implicitly as a literal).


#### Capture groups

`bourbaki.regex` will only construct capture groups when explicitly asked to.
Function call syntax may be used to create capture groups, taking a single string argument as the name
(motivated by the mnemonic that a group is _called_ by a name).
Alternately, omitting the name results in an unnamed capture group, i.e. in raw regex we put parentheses on either side 
of a pattern to indicate capture, and in `bourbaki.regex`, we place an empty pair at the end of a pattern. 
The `.as_` method and `.captured` attribute may also be used for this purpose.

  - `C['0':'9'].as_("a_numeral")` will result in a regex matching a single digit for whose matches calling the 
    `.groupdict()` method will yield a `dict` with the key `"a_numeral"`, i.e. this is a named group.
    This is equivalent to `C['0':'9']("a_numeral")`, using the function call syntax.
  
  - `C['0':'9'].captured` is as above, but the group isn't named. It will get a number in the resulting compiled
    pattern, and will be accessible by calling `.groups()` on any match object.
    This is equivalent to `C['0':'9']()`, using the function call syntax.

Regexes and all of their named capture groups may be renamed in one call with the `.rename` method:

```python
> regex = (Literal("foo").as_("foo") + literal("bar").as_("bar")).as_("foobar")
> regex.pattern
'(?P<foobar>(?P<baz>foo)(?P<bar>bar))'
> # rename the group foo to baz and drop the global capture group name foobar
> regex.rename({'foo': 'baz', 'foobar': None}).pattern
'((?P<baz>foo)(?P<bar>bar))'
```

You may also use callables for renaming:

```python
> regex.rename(lambda name: 'foobarbaz' if name == 'foobar' else None).pattern
'(?P<foobarbaz>(foo)(bar))'
```

And all named capture groups may be converted to unnamed capture groups with `.drop_names`:

```python
> regex.drop_names().pattern
'((foo)(bar))'
```

  
#### Lookahead and Lookbehind assertions
  
Lookahead and lookbehind assertions can be constructed with the `>>` and `<<` operators respectively.
The pattern which is matched "points to" the lookahead or lookbehind assertion.

The `-` _unary_ operator (negation) is used to express a _negative assertion_.

  - For example, `L("foo") >> "bar"` will match `"foo"`, but only in a string where it is followed by `"bar'`

  - Similarly, `L("foo") << "bar"` will match `"bar"`, but only in a string where it is preceded by `"foo"`.
  
  - `"foo" >> -L("bar")` will match `"foo"`, but only if _not_ followed by `"bar"`.
  
  - `-L("foo") << "bar"` will match `"bar"`, but only if _not_ preceded by `"foo"`.
  
  
#### Comments in compiled patterns

The `//` operator may take a raw string on the right which serves as a comment.
It has no effect on the match behavior of the resulting pattern but will be present as a comment in the 
compiled pattern.

  - `L("foo") // "foo, the usual placeholder name"` compiles to the pattern 
    `"(?#foo, the usual placeholder name)foo"`


Note:
Python's standard library regex engine does not support variable-length lookbehind assertions. 
If you attempt to use a pattern which matches variable-length strings as a lookbehind assertion, you will get a useful error.
To use `regex` or another conforming to python's `re` module API, but supporting variable length lookbehind 
assertions, simply `import bourbaki.regex.base as bre`, and set 
`bre.REQUIRE_FIX_LEN_LOOKBEHIND = False; bre.re = <your preferred regex module>`.


#### Atomic groups

The unary `+` (positive) operator is used to construct [_atomic groups_](https://www.regular-expressions.info/atomic.html).
This means that once the regex engine matches the atomic pattern, it will never backtrack to before the match.
The `.atomic` attribute may also be used.

Python's standard library regex engine does not support this feature natively, but other modules such as 
[`regex`](https://pypi.org/project/regex/) do.
Thus, by default, `bourbaki.regex` constructs a standard python regex which _behaves_ as if it were atomic by using a 
backreference to accomplish the same goal.
To use `regex` or another conforming to python's `re` module API, but supporting 
atomic groups natively, simply `import bourbaki.regex.base as bre`, and set 
`bre.ATOMIC_GROUP_SUPPORT = True; bre.re = <your preferred regex module>`.

  - For example, `"a" + (L("bc") | "b").atomic + "c"` will match `"abcc"` but not `"abc"`, since both strings cause the 
    atomic group in the middle of the pattern to be consumed as soon as `"bc"` is matched, leaving a `"c"` still to be 
    matched.
