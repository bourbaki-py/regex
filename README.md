# Regular expressions made readable

## Introduction

`bourbaki.regex` provides an interface for constructing arbitrarily complex 
regular expressions using standard Python syntax.

The goals of the package are the following:

  - allow the user to be as terse as possible while not sacrificing readability
  - support the full range of constructs available in the standard library regex engine (`re` module)
  - be extensible and modular to support more advanced constructs in the future, 
    as for instance provided by the `regex` module
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
  