import pytest
import re
from bourbaki.regex import L


foobar = L("foobar")


@pytest.mark.parametrize('options,pattern', [
    (re.ASCII, '(?a:foobar)'),
    (re.IGNORECASE | re.UNICODE, '(?iu:foobar)'),
    ((re.IGNORECASE, re.UNICODE), '(?iu:foobar)'),
    ('IGNORECASE', '(?i:foobar)'),
    (['IGNORECASE', 'ASCII'], '(?ai:foobar)'),
])
def test_with_options(options, pattern):
    with_options = foobar & options
    assert with_options.pattern == pattern

    with_options_explicit = foobar.with_options(options)
    assert with_options_explicit.pattern == pattern

    if isinstance(options, (list, tuple, set)):
        with_options_explicit_splat = foobar.with_options(*options)
        assert with_options_explicit_splat.pattern == pattern


@pytest.mark.parametrize('options,pattern', [
    (re.S, '(?-s:foobar)'),
    (re.IGNORECASE | re.MULTILINE, '(?-im:foobar)'),
    ((re.IGNORECASE, re.MULTILINE), '(?-im:foobar)'),
    ('IGNORECASE', '(?-i:foobar)'),
    (['IGNORECASE', 'VERBOSE'], '(?-ix:foobar)'),
])
def test_without_options(options, pattern):
    without_options = foobar - options
    assert without_options.pattern == pattern

    without_options_explicit = foobar.without_options(options)
    assert without_options_explicit.pattern == pattern

    if isinstance(options, (list, tuple, set)):
        without_options_explicit_splat = foobar.without_options(*options)
        assert without_options_explicit_splat.pattern == pattern


@pytest.mark.parametrize('bad_option', [
    re.ASCII,
    re.UNICODE,
    re.LOCALE,
    re.ASCII | re.UNICODE,
    [re.ASCII, re.LOCALE],
    'ASCII',
    'UNICODE',
    ('ASCII', 'UNICODE'),
])
def test_without_non_negatable_options_raises(bad_option):
    with pytest.raises(ValueError):
        _ = foobar.without_options(bad_option)

    with pytest.raises(ValueError):
        _ = foobar - bad_option

    if isinstance(bad_option, (list, tuple, set)):
        with pytest.raises(ValueError):
            _ = foobar.without_options(*bad_option)


@pytest.mark.parametrize('bad_option', [
    re.ASCII | re.UNICODE,
    [re.ASCII, re.LOCALE],
    ('UNICODE', 'LOCALE'),
])
def test_with_mutually_exclusive_options_raises(bad_option):
    with pytest.raises(ValueError):
        _ = foobar.with_options(bad_option)

    with pytest.raises(ValueError):
        _ = foobar & bad_option

    if isinstance(bad_option, (list, tuple, set)):
        with pytest.raises(ValueError):
            _ = foobar.with_options(*bad_option)


@pytest.mark.parametrize('pos_options,neg_options,pattern', [
    (re.A, re.S, '(?a-s:foobar)'),
    (re.VERBOSE | re.IGNORECASE, 'MULTILINE', '(?ix-m:foobar)'),
    ((re.IGNORECASE, re.MULTILINE), re.MULTILINE, '(?i:foobar)'),
    (('VERBOSE', 'ASCII'), re.VERBOSE | re.MULTILINE, '(?a-m:foobar)'),
    (['IGNORECASE', re.UNICODE], [], '(?iu:foobar)'),
    ([re.U, 'IGNORECASE'], [re.I], '(?u:foobar)'),
])
def test_with_and_without_options(pos_options, neg_options, pattern):
    with_options = (foobar - neg_options) & pos_options
    assert with_options.pattern == pattern

    with_options = (foobar & pos_options) - neg_options
    assert with_options.pattern == pattern

    with_options_explicit = foobar.with_options(pos_options).without_options(neg_options)
    assert with_options_explicit.pattern == pattern

    with_options_explicit = foobar.without_options(neg_options).with_options(pos_options)
    assert with_options_explicit.pattern == pattern

    pos_splattable, neg_splattable = isinstance(pos_options, (list, tuple, set)), isinstance(neg_options, (list, tuple, set))
    if pos_splattable:
        with_options_explicit_splat = foobar.with_options(*pos_options)
        if neg_splattable:
            with_options_explicit_splat = with_options_explicit_splat.without_options(*neg_options)
        else:
            with_options_explicit_splat -= neg_options
    elif neg_splattable:
        with_options_explicit_splat = foobar.without_options(*neg_options)
        with_options_explicit_splat &= pos_options

    if pos_splattable or neg_splattable:
        assert with_options_explicit_splat.pattern == pattern
