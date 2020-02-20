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
foobar2named = foobar2 + If(foobar2).then_('baz').else_('')


rename_dict = dict(foo='food', bar='barn')
rename_ordereddict = OrderedDict(rename_dict.items())

def rename_func(name):
    return rename_dict.get(name, name)


@pytest.mark.parametrize('regex', [foo, bar])
@pytest.mark.parametrize("rename", [rename_dict, rename_ordereddict, rename_func])
def test_renames_are_cached(regex, rename):
    renamed1, renamed2 = regex.rename(rename), regex.rename(rename)
    assert renamed1 is renamed2


@pytest.mark.parametrize("regex", [foobar1, foobar2])
@pytest.mark.parametrize("rename", [rename_dict, rename_ordereddict, rename_func])
def test_rename_with_literal_backrefs(regex, rename):
    assert regex.pattern == '(?P<foobar>(?P<foo>foo)(?(foo)(?P<bar>bar)|))'
    renamed = regex.rename(rename)
    assert renamed.pattern == '(?P<foobar>(?P<food>foo)(?(food)(?P<barn>bar)|))'
