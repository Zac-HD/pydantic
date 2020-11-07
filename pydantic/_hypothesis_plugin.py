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
import math
from functools import partial
from typing import cast

import hypothesis.strategies as st

import pydantic
import pydantic.color
from pydantic.networks import import_email_validator

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
