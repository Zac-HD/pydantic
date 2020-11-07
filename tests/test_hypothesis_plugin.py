import pytest
from hypothesis import given, settings, strategies as st

import pydantic
from pydantic.networks import import_email_validator


class MiscModel(pydantic.BaseModel):
    # Each of these models contains a few related fields; the idea is that
    # if there's a bug we have neither too many fields to dig through nor
    # too many models to read.
    obj: pydantic.PyObject
    color: pydantic.color.Color


class StringsModel(pydantic.BaseModel):
    uuid1: pydantic.UUID1
    uuid3: pydantic.UUID3
    uuid4: pydantic.UUID4
    uuid5: pydantic.UUID5
    secbytes: pydantic.SecretBytes
    secstr: pydantic.SecretStr


class IPvAnyAddress(pydantic.BaseModel):
    address: pydantic.IPvAnyAddress


class IPvAnyInterface(pydantic.BaseModel):
    interface: pydantic.IPvAnyInterface


class IPvAnyNetwork(pydantic.BaseModel):
    network: pydantic.IPvAnyNetwork


class StrictNumbersModel(pydantic.BaseModel):
    strictbool: pydantic.StrictBool
    strictint: pydantic.StrictInt
    strictfloat: pydantic.StrictFloat
    strictstr: pydantic.StrictStr


class ConBytesModel(pydantic.BaseModel):
    # This and the strings model aim to exercise all the length- and regex-based
    # special cases in our implementation, including Hypothesis' special handling
    # for bytestrings of fixed length.
    b00_false = pydantic.conbytes(min_length=0, max_length=0, strip_whitespace=False)
    b33_false = pydantic.conbytes(min_length=3, max_length=3, strip_whitespace=False)
    b04_false = pydantic.conbytes(min_length=0, max_length=4, strip_whitespace=False)
    b14_false = pydantic.conbytes(min_length=1, max_length=4, strip_whitespace=False)
    b24_false = pydantic.conbytes(min_length=2, max_length=4, strip_whitespace=False)
    b34_false = pydantic.conbytes(min_length=3, max_length=4, strip_whitespace=False)
    b00_true = pydantic.conbytes(min_length=0, max_length=0, strip_whitespace=True)
    b33_true = pydantic.conbytes(min_length=3, max_length=3, strip_whitespace=True)
    b04_true = pydantic.conbytes(min_length=0, max_length=4, strip_whitespace=True)
    b14_true = pydantic.conbytes(min_length=1, max_length=4, strip_whitespace=True)
    b24_true = pydantic.conbytes(min_length=2, max_length=4, strip_whitespace=True)
    b34_true = pydantic.conbytes(min_length=3, max_length=4, strip_whitespace=True)


class ConStringsModel(pydantic.BaseModel):
    s00_false = pydantic.constr(min_length=0, max_length=0, strip_whitespace=False)
    s33_false = pydantic.constr(min_length=3, max_length=3, strip_whitespace=False)
    s04_false = pydantic.constr(min_length=0, max_length=4, strip_whitespace=False)
    s14_false = pydantic.constr(min_length=1, max_length=4, strip_whitespace=False)
    s24_false = pydantic.constr(min_length=2, max_length=4, strip_whitespace=False)
    s34_false = pydantic.constr(min_length=3, max_length=4, strip_whitespace=False)
    s00_true = pydantic.constr(min_length=0, max_length=0, strip_whitespace=True)
    s33_true = pydantic.constr(min_length=3, max_length=3, strip_whitespace=True)
    s04_true = pydantic.constr(min_length=0, max_length=4, strip_whitespace=True)
    s14_true = pydantic.constr(min_length=1, max_length=4, strip_whitespace=True)
    s24_true = pydantic.constr(min_length=2, max_length=4, strip_whitespace=True)
    s34_true = pydantic.constr(min_length=3, max_length=4, strip_whitespace=True)


try:
    import_email_validator()
except ImportError:

    class EmailsModel:
        # Our emails strategies are only registered if the email validator is installed
        pass


else:

    class EmailsModel(pydantic.BaseModel):
        email: pydantic.EmailStr
        name_email: pydantic.NameEmail


@pytest.mark.parametrize(
    """model""",
    [
        EmailsModel,
        MiscModel,
        StringsModel,
        IPvAnyAddress,
        IPvAnyInterface,
        IPvAnyNetwork,
        StrictNumbersModel,
        ConBytesModel,
        ConStringsModel,
    ],
)
@settings(max_examples=20)
@given(data=st.data())
def test_can_construct_models_with_all_fields(data, model):
    # We take successful creation of an instance to demonstrate that Hypothesis
    # knows how to provide valid values for each field, so we don't need any
    # additional assertions.
    instance = data.draw(st.from_type(model))
    assert isinstance(instance, model)
