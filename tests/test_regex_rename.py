from collections import OrderedDict
import pytest
from bourbaki.regex import L, If

foo = L("foo").as_("foo")
bar = L("bar").as_("bar")

# named backrefs
foobar1 = (foo + If("foo").then_(bar).else_('')).as_("foobar")
foobarbaz1 = foobar1 + If("foobar").then_('baz').else_('')

# literal backrefs
foobar2 = (foo + If(foo).then_(bar).else_('')).as_("foobar")
foobarbaz2 = foobar2 + If(foobar2).then_('baz').else_('')


rename_dict = dict(foo='food', bar='barn')
rename_ordereddict = OrderedDict(rename_dict.items())

def rename_func(name):
    return rename_dict.get(name, name)


@pytest.mark.parametrize('regex', [foo, bar])
@pytest.mark.parametrize("rename", [rename_dict, rename_ordereddict, rename_func])
def test_capture_group_renames_are_cached(regex, rename):
    renamed1, renamed2 = regex.rename(rename), regex.rename(rename)
    assert renamed1 is renamed2


@pytest.mark.parametrize("regex", [foobar1, foobar2])
@pytest.mark.parametrize("rename", [rename_dict, rename_ordereddict, rename_func])
def test_rename_with_literal_backrefs(regex, rename):
    assert regex.pattern == '(?P<foobar>(?P<foo>foo)(?(foo)(?P<bar>bar)|))'
    renamed = regex.rename(rename)
    assert renamed.pattern == '(?P<foobar>(?P<food>foo)(?(food)(?P<barn>bar)|))'


@pytest.mark.parametrize("regex,pattern", [
    (foobar2, '((foo)(?(2)(bar)|))'),
    (foobarbaz2, '((foo)(?(2)(bar)|))(?(1)baz|)')
])
def test_drop_names_literal_backrefs(regex, pattern):
    unnamed = regex.drop_names()
    assert unnamed.pattern == pattern


@pytest.mark.parametrize("regex", [foobar1, foobarbaz1])
def test_drop_names_named_backrefs_raises(regex):
    with pytest.raises(ValueError):
        _ = regex.drop_names()
