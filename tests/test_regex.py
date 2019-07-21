from functools import reduce
from itertools import chain
import operator

import pytest

from bourbaki.regex import *

# Basic character classes
alpha = C['a':'z']
alpha_any = alpha | C['A':'Z']

num = C['0':'9']
posnum = C['1':'9']

alphanum = alpha | num
alphanum_any = alpha_any | num

hexdigit = num | C['a':'f']
hexdigit_any = hexdigit | C['A':'F']

identifier = (alpha_any | '_') + (alphanum_any | "_")[:]
percent_encoded = "%" + hexdigit_any * 2

user_host_path_chars = C["!$&'()*+,;"]
path_query_fragment_chars = C[":-.@"]
query_fragment_chars = C["?/"]

# scheme
scheme = alpha + (alphanum | C['+.-'])[:]

# user info
user_char = alphanum_any | user_host_path_chars | '.' | percent_encoded
username = user_char[1:]
password = user_char[:]

userinfo = username("username") + (":" + password("password")).optional

# host
hostname_label = alphanum[:63] | (alphanum + (alphanum | '-')[:61] + alphanum)
hostname = (hostname_label("host") + '.').optional + hostname_label("domain") + '.' + hostname_label("top_level_domain")

octet = '0' | (posnum + num.optional) | ('1' + num * 2) | ('2' + C['0':'4'] + num) | ('25' + C['0':'5'])
ipv4address = octet + ('.' + octet) * 3

quibble = hexdigit[1:4]
ipv6address = (reduce(operator.or_,
                      (quibble + (":" + quibble)[:i] + (":" + L("")) + (":" + quibble)[:6 - i] + ":" + quibble for i in
                       range(1, 6))
                      )
               | quibble + (":" + quibble) * 7)

# port
port = ('0' | posnum + num[:3] | C['1':'5'] + num[:4] |
        '6' + C['0':'4'] + num * 3 |
        '65' + C['0':'4'] + num * 2 |
        '655' + C['0':'2'] + num |
        '6553' + C['0':'6'])

# user info + host + port = authority
authority = ((userinfo("userinfo") + "@").optional
             + ((ipv4address("ipv4") | "[" + ipv6address("ipv6") + "]")("ip") | (
                    hostname("hostname") + C["."].optional))
             + (":" + port("port")).optional)

# path
path_char = alphanum_any | user_host_path_chars | path_query_fragment_chars | percent_encoded
path_segment = path_char[:]
nonempty_path_segment = path_char[1:]

# last segment can't be empty if present
path_with_authority = ("/" + path_segment)[:] + L("/").optional
# no leading double slash allowed
path_with_no_authority = (L("/").optional + nonempty_path_segment + path_with_authority) | ""

# query
qchars = alphanum_any | path_query_fragment_chars | query_fragment_chars | C['+*-._'] | percent_encoded
qexpr = qchars[:]
qparam = qexpr + "=" + qexpr

query = qparam + (C["&;"] + qparam)[:]

# fragment
fragment_chars = alphanum_any | path_query_fragment_chars | query_fragment_chars | '=' | percent_encoded
fragment = fragment_chars[:]

# full uri
uri = (START +
       (scheme("scheme") + ":").optional
       + (If("scheme").then_("//").else_("") + authority("authority")).optional
       + (If("authority").then_(path_with_authority).else_(path_with_no_authority) + Literal('/').optional)("path")
       + ("?" + query("query")).optional
       + ("#" + fragment("fragment")).optional
       + END)

wikipedia_examples = [
    "https://john.doe@www.example.com:123/forum/questions/?tag=networking&order=newest#top",
    "ldap://[2001:db8::7]/path%3f?param=value;p=v",
    "news:comp.infosystems.www.servers.unix",
    "mailto://John.Doe@example.com",
    "mailto:John.Doe@example.com",
    "tel:+1-816-555-1212",
    "telnet://192.0.2.16:80/",
    "urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
]

parses = [
    dict(scheme="https", username="john.doe", hostname="www.example.com",
         host="www", domain="example", top_level_domain="com", port="123",
         path="/forum/questions/", query="tag=networking&order=newest", fragment="top"),
    dict(scheme="ldap", ipv6="2001:db8::7", path="/path%3f", query="param=value;p=v"),
    dict(scheme="news", path="comp.infosystems.www.servers.unix"),
    dict(scheme="mailto", username="John.Doe", domain="example", top_level_domain="com"),
    dict(scheme="mailto", path="John.Doe@example.com"),
    dict(scheme="tel", path="+1-816-555-1212"),
    dict(scheme="telnet", ipv4="192.0.2.16", port="80", path="/"),
    dict(scheme="urn", path="oasis:names:specification:docbook:dtd:xml:4.1.2")
]


def validate_uri_parse(uri_, groupdict, ignore=('authority', 'userinfo', 'ip', 'hostname'), defaults=dict(path='')):
    match = uri.fullmatch(uri_)

    if match is None:
        print("No match: {}".format(uri_))
        return False

    gd = match.groupdict()
    groupdict = {**defaults, **groupdict}

    print("'{}' :".format(uri_))
    print_ = lambda s: print("\t", s)
    bad = False
    for k, v in gd.items():
        if k in ignore:
            continue
        if v is None:
            if groupdict.get(k) is not None:
                print_("group name '{}' should have matched '{}' but wasn't matched".format(k, groupdict[k]))
                bad = True
        else:
            if k not in groupdict:
                print_("group name '{}' was matched to '{}' but shouldn't have".format(k, v))
                bad = True
            elif v != groupdict[k]:
                print_("group name '{}' was matched to '{}' but should have matched '{}'".format(k, v, groupdict[k]))
                bad = True

    return not bad


foo, bar, baz = map(L, "foo bar baz".split())
foo_ = foo()
conditional_regex = foo_.optional + If(foo_).then_(bar).else_(baz)


@pytest.mark.parametrize("s, match", [("foobar", True), ("baz", True), ("foo", False), ("bar", False)])
def test_conditional_pattern(s, match, pattern=conditional_regex):
    if match:
        assert pattern.match(s)
    else:
        assert not pattern.match(s)


@pytest.mark.parametrize("s, match", [("foobar", True), ("baz", True), ("foo", False), ("bar", False)])
def test_negated_pattern(s, match, pattern=conditional_regex):
    if match:
        assert not (~pattern).match(s)
    else:
        assert (~pattern).match(s)


@pytest.mark.parametrize("o", map(str, chain(range(1, 2 ** 8, 11), [255])))
def test_octet_pattern(o):
    assert octet.fullmatch(o)


@pytest.mark.parametrize("uri,parse", zip(wikipedia_examples, parses))
def test_uri_parse(uri, parse):
    validate_uri_parse(uri, parse)
