import typing
import pydantic
from hypothesis import given, strategies as st


class Model(pydantic.BaseModel):
    redis: pydantic.RedisDsn
    users: typing.List[pydantic.EmailStr]
    probability: pydantic.confloat(ge=0, lt=1)


@given(st.builds(Model))
def test_property(instance):
    # Hypothesis calls this test function many times with varied Models,
    # so you can write a test that should pass given *any* instance.
    assert instance.redis.startswith('redis://')
    assert all('@' in email for email in instance.users)
    assert isinstance(instance.probability, float)
    assert 0 <= instance.probability < 1


@given(st.builds(Model, probability=st.floats(0, 0.2)))
def test_unlucky_users(instance):
    # This test shows how you can override specific fields,
    # and let Hypothesis fill in any you don't care about.
    assert instance.probability <= 0.2
