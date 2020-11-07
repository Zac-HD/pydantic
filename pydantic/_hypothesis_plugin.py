"""Register Hypothesis strategies for Pydantic custom types.

This enables fully-automatic generation of test data for most Pydantic classes.

Note that this module has *no* runtime impact on Pydantic itself; instead it
is registered as a setuptools entry point and Hypothesis will import it if
Pydantic is installed.  See also:

https://hypothesis.readthedocs.io/en/latest/strategies.html#registering-strategies-via-setuptools-entry-points
https://hypothesis.readthedocs.io/en/latest/data.html#hypothesis.strategies.register_type_strategy
https://hypothesis.readthedocs.io/en/latest/strategies.html#interaction-with-pytest-cov
https://pydantic-docs.helpmanual.io/usage/types/#pydantic-types

Note that because our motivation is to *improve user experience*, the strategies
are always sound (never generate invalid data) but sacrifice completeness for
maintainability (ie may be unable to generate some tricky but valid data).

Finally, this module makes liberal use of `# type: ignore[<code>]` pragmas.
This is because Hypothesis annotates register_type_strategy with
(T, SearchStrategy[T]), but in most cases we register e.g. AnyURL to generate strings,
ConstrainedInt to generate normal ints (which match the constraints), etc.
"""

import ipaddress
import json
import math
from fractions import Fraction
from functools import partial
from typing import cast

import hypothesis.strategies as st

import pydantic
import pydantic.color
from pydantic.networks import ascii_domain_regex, import_email_validator, int_domain_regex

# FilePath and DirectoryPath are explicitly unsupported, as we'd have to create
# them on-disk, and that's unsafe in general without being told *where* to do so.

# Emails
try:
    import_email_validator()
except ImportError:  # pragma: no cover
    pass
else:
    # Note that these strategies deliberately stay away from any tricky Unicode
    # or other encoding issues; we're just trying to generate *something* valid.
    st.register_type_strategy(pydantic.EmailStr, st.emails())  # type: ignore[arg-type]
    st.register_type_strategy(
        pydantic.NameEmail,
        st.builds(
            '{} <{}>'.format,  # type: ignore[arg-type]
            st.from_regex('[A-Za-z0-9_]+( [A-Za-z0-9_]+){0,5}', fullmatch=True),
            st.emails(),
        ),
    )

# PyObject - dotted names, in this case taken from the math module.
st.register_type_strategy(
    pydantic.PyObject,
    st.sampled_from(
        [cast(pydantic.PyObject, f'math.{name}') for name in sorted(vars(math)) if not name.startswith('_')]
    ),
)

# CSS3 Colors; as name, hex, rgb(a) tuples or strings, or hsl strings
_color_regexes = (
    pydantic.color.r_hex_short,
    pydantic.color.r_hex_long,
    pydantic.color.r_rgb,
    pydantic.color.r_rgba,
    pydantic.color.r_hsl,
    pydantic.color.r_hsla,
)
st.register_type_strategy(
    pydantic.color.Color,
    st.one_of(
        st.sampled_from(sorted(pydantic.color.COLORS_BY_NAME)),
        st.tuples(
            st.integers(0, 255),
            st.integers(0, 255),
            st.integers(0, 255),
            st.none() | st.floats(0, 1) | st.floats(0, 100).map('{}%'.format),
        ),
        st.from_regex('|'.join(_color_regexes), fullmatch=True),
    ),
)

# JSON strings, optionally constrained to a particular type.  We have to register
# separate strategies for these cases because they're distinct types at runtime.
st.register_type_strategy(
    pydantic.Json,
    st.builds(
        json.dumps,  # type: ignore[arg-type]
        st.recursive(
            base=st.one_of(
                st.none(),
                st.booleans(),
                st.integers(),
                st.floats(allow_infinity=False, allow_nan=False),
                st.text(),
            ),
            extend=lambda x: st.lists(x) | st.dictionaries(st.text(), x),
        ),
        ensure_ascii=st.booleans(),
        indent=st.none() | st.integers(0, 16),
        sort_keys=st.booleans(),
    ),
)


@partial(st.register_type_strategy, pydantic.JsonWrapper)
def resolve_jsonwrapper(cls):  # type: ignore[no-untyped-def]
    return st.builds(
        json.dumps,
        st.from_type(cls.inner_type),
        ensure_ascii=st.booleans(),
        indent=st.none() | st.integers(0, 16),
        sort_keys=st.booleans(),
    )


# Card numbers, valid according to the Luhn algorithm


def fix_luhn_digit(card_number: str) -> str:
    # See https://en.wikipedia.org/wiki/Luhn_algorithm
    assert card_number[-1] == 'X', 'expected placeholder check digit'
    for digit in '0123456789':
        try:
            card_number = card_number[:-1] + digit
            pydantic.PaymentCardNumber.validate_luhn_check_digit(card_number)
            return card_number
        except pydantic.ValidationError:
            continue
    raise AssertionError('Should be unreachable')


card_patterns = (
    '4[0-9]{14}X',  # Visa
    '5[12345][0-9]{13}X',  # Mastercard
    '3[47][0-9]{12}X',  # American Express
    '[0-9]{11,18}X',  # other
)
st.register_type_strategy(
    pydantic.PaymentCardNumber,
    st.from_regex('|'.join(card_patterns), fullmatch=True).map(fix_luhn_digit),  # type: ignore[arg-type]
)

# URLs


def resolve_anyurl(cls):  # type: ignore[no-untyped-def]
    domains = st.one_of(
        st.from_regex(ascii_domain_regex(), fullmatch=True),
        st.from_regex(int_domain_regex(), fullmatch=True),
    )
    if cls.tld_required:

        def has_tld(s: str) -> bool:
            assert isinstance(s, str)
            match = ascii_domain_regex().fullmatch(s) or int_domain_regex().fullmatch(s)
            return bool(match and match.group('tld'))

        hosts = domains.filter(has_tld)
    else:
        hosts = domains | st.from_regex(
            r'(?P<ipv4>(?:\d{1,3}\.){3}\d{1,3})' r'|(?P<ipv6>\[[A-F0-9]*:[A-F0-9:]+\])',
            fullmatch=True,
        )

    return st.builds(
        cls.build,
        scheme=(
            st.sampled_from(sorted(cls.allowed_schemes))
            if cls.allowed_schemes
            else st.from_regex(r'(?P<scheme>[a-z][a-z0-9+\-.]+)', fullmatch=True)
        ),
        user=st.one_of(
            st.nothing() if cls.user_required else st.none(),
            st.from_regex(r'(?P<user>[^\s:/]+)', fullmatch=True),
        ),
        password=st.none() | st.from_regex(r'(?P<password>[^\s/]*)', fullmatch=True),
        host=hosts,
        port=st.none() | st.integers(0, 2 ** 16 - 1).map(str),
        path=st.none() | st.from_regex(r'(?P<path>/[^\s?]*)', fullmatch=True),
        query=st.none() | st.from_regex(r'(?P<query>[^\s#]+)', fullmatch=True),
        fragment=st.none() | st.from_regex(r'(?P<fragment>\S+)', fullmatch=True),
    ).filter(lambda url: cls.min_length <= len(url) <= cls.max_length)


st.register_type_strategy(pydantic.AnyUrl, resolve_anyurl)
st.register_type_strategy(pydantic.AnyHttpUrl, resolve_anyurl)
st.register_type_strategy(pydantic.HttpUrl, resolve_anyurl)
st.register_type_strategy(pydantic.PostgresDsn, resolve_anyurl)
st.register_type_strategy(pydantic.RedisDsn, resolve_anyurl)


# UUIDs
st.register_type_strategy(pydantic.UUID1, st.uuids(version=1))  # type: ignore[arg-type]
st.register_type_strategy(pydantic.UUID3, st.uuids(version=3))  # type: ignore[arg-type]
st.register_type_strategy(pydantic.UUID4, st.uuids(version=4))  # type: ignore[arg-type]
st.register_type_strategy(pydantic.UUID5, st.uuids(version=5))  # type: ignore[arg-type]

# Secrets
st.register_type_strategy(pydantic.SecretBytes, st.binary().map(pydantic.SecretBytes))
st.register_type_strategy(pydantic.SecretStr, st.text().map(pydantic.SecretStr))

# IP addresses, networks, and interfaces
st.register_type_strategy(pydantic.IPvAnyAddress, st.ip_addresses())
st.register_type_strategy(
    pydantic.IPvAnyInterface,
    st.from_type(ipaddress.IPv4Interface) | st.from_type(ipaddress.IPv6Interface),
)
st.register_type_strategy(
    pydantic.IPvAnyNetwork,
    st.from_type(ipaddress.IPv4Network) | st.from_type(ipaddress.IPv6Network),
)

# Constrained types
# Because a new type is created at runtime for each new set of constraints,
# we register the *parent* type with a function that takes the child type
# and returns an appropriate strategy.
st.register_type_strategy(pydantic.StrictBool, st.booleans())


@partial(st.register_type_strategy, pydantic.ConstrainedBytes)
def resolve_conbytes(cls):  # type: ignore[no-untyped-def]  # pragma: no cover
    min_size = cls.min_length or 0
    max_size = cls.max_length
    if not cls.strip_whitespace:
        return st.binary(min_size=min_size, max_size=max_size)
    # Fun with regex to ensure we neither start nor end with whitespace
    repeats = '{{{},{}}}'.format(
        min_size - 2 if min_size > 2 else 0,
        max_size - 2 if (max_size or 0) > 2 else '',
    )
    if min_size >= 2:
        pattern = rf'\W.{repeats}\W'
    elif min_size == 1:
        pattern = rf'\W(.{repeats}\W)?'
    else:
        assert min_size == 0
        pattern = rf'(\W(.{repeats}\W)?)?'
    return st.from_regex(pattern.encode(), fullmatch=True)


@partial(st.register_type_strategy, pydantic.ConstrainedDecimal)
def resolve_condecimal(cls):  # type: ignore[no-untyped-def]
    min_value = cls.ge
    max_value = cls.le
    if cls.gt is not None:
        assert min_value is None, 'Set `gt` or `ge`, but not both'
        min_value = cls.gt
    if cls.lt is not None:
        assert max_value is None, 'Set `lt` or `le`, but not both'
        max_value = cls.lt
    # max_digits, decimal_places, and multiple_of are handled via the filter
    return st.decimals(min_value, max_value, allow_nan=False).filter(cls.validate)


@partial(st.register_type_strategy, pydantic.ConstrainedFloat)
def resolve_confloat(cls):  # type: ignore[no-untyped-def]
    min_value = cls.ge
    max_value = cls.le
    exclude_min = False
    exclude_max = False
    if cls.gt is not None:
        assert min_value is None, 'Set `gt` or `ge`, but not both'
        min_value = cls.gt
        exclude_min = True
    if cls.lt is not None:
        assert max_value is None, 'Set `lt` or `le`, but not both'
        max_value = cls.lt
        exclude_max = True
    # multiple_of is handled via the filter
    return st.floats(
        min_value,
        max_value,
        exclude_min=exclude_min,
        exclude_max=exclude_max,
        allow_nan=False,
    ).filter(cls.validate)


@partial(st.register_type_strategy, pydantic.ConstrainedInt)
def resolve_conint(cls):  # type: ignore[no-untyped-def]
    min_value = cls.ge
    max_value = cls.le
    if cls.gt is not None:
        assert min_value is None, 'Set `gt` or `ge`, but not both'
        min_value = cls.gt + 1
    if cls.lt is not None:
        assert max_value is None, 'Set `lt` or `le`, but not both'
        max_value = cls.lt - 1

    if cls.multiple_of is None or cls.multiple_of == 1:
        return st.integers(min_value, max_value)

    # These adjustments and the .map handle integer-valued multiples, while the
    # .filter handles trickier cases as for confloat.
    if min_value is not None:
        min_value = math.ceil(Fraction(min_value) / Fraction(cls.multiple_of))
    if max_value is not None:
        max_value = math.floor(Fraction(max_value) / Fraction(cls.multiple_of))
    return st.integers(min_value, max_value).map(lambda x: x * cls.multiple_of).filter(cls.validate)


@partial(st.register_type_strategy, pydantic.ConstrainedList)
def resolve_conlist(cls):  # type: ignore[no-untyped-def]
    return st.lists(
        st.from_type(cls.item_type),
        min_size=cls.min_items,
        max_size=cls.max_items,
    )


@partial(st.register_type_strategy, pydantic.ConstrainedSet)
def resolve_conset(cls):  # type: ignore[no-untyped-def]
    return st.sets(
        st.from_type(cls.item_type),
        min_size=cls.min_items,
        max_size=cls.max_items,
    )


@partial(st.register_type_strategy, pydantic.ConstrainedStr)
def resolve_constr(cls):  # type: ignore[no-untyped-def]  # pragma: no cover
    min_size = cls.min_length or 0
    max_size = cls.max_length

    if cls.regex is None and not cls.strip_whitespace:
        return st.text(min_size=min_size, max_size=max_size)

    if cls.regex is not None:
        strategy = st.from_regex(cls.regex)
        if cls.strip_whitespace:
            strategy = strategy.filter(lambda s: s == s.strip())
    elif cls.strip_whitespace:
        repeats = '{{{},{}}}'.format(
            min_size - 2 if min_size > 2 else 0,
            max_size - 2 if (max_size or 0) > 2 else '',
        )
        if min_size >= 2:
            strategy = st.from_regex(rf'\W.{repeats}\W')
        elif min_size == 1:
            strategy = st.from_regex(rf'\W(.{repeats}\W)?')
        else:
            assert min_size == 0
            strategy = st.from_regex(rf'(\W(.{repeats}\W)?)?')

    if min_size == 0 and max_size is None:
        return strategy
    elif max_size is None:
        return strategy.filter(lambda s: min_size <= len(s))
    return strategy.filter(lambda s: min_size <= len(s) <= max_size)
