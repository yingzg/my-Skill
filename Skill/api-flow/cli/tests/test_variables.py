import pytest
from api_flow.variables import RuntimeVariables, substitute


class TestRuntimeVariables:
    def test_set_and_get(self):
        rv = RuntimeVariables()
        rv.set("@uid", "abc-123")
        assert rv.get("@uid") == "abc-123"

    def test_get_missing_returns_none(self):
        rv = RuntimeVariables()
        assert rv.get("@nonexistent") is None

    def test_inject_auth_token(self):
        rv = RuntimeVariables()
        rv.set_auth_token("bearer-xxx")
        assert rv.get("AUTH_TOKEN") == "bearer-xxx"


class TestSubstitute:
    def test_substitutes_variable_in_string(self):
        rv = RuntimeVariables()
        rv.set("@uid", "abc-123")
        result = substitute("{{@uid}}", rv)
        assert result == "abc-123"

    def test_substitutes_multiple_variables(self):
        rv = RuntimeVariables()
        rv.set("@uid", "abc")
        rv.set("@pid", "xyz")
        result = substitute("user={{@uid}}&product={{@pid}}", rv)
        assert result == "user=abc&product=xyz"

    def test_substitutes_in_dict_values(self):
        rv = RuntimeVariables()
        rv.set("@uid", "abc")
        body = {"userId": "{{@uid}}", "type": "NORMAL"}
        result = substitute(body, rv)
        assert result == {"userId": "abc", "type": "NORMAL"}

    def test_substitutes_in_nested_dict(self):
        rv = RuntimeVariables()
        rv.set("@pid", "xyz")
        body = {"items": [{"productId": "{{@pid}}", "qty": 1}]}
        result = substitute(body, rv)
        assert result == {"items": [{"productId": "xyz", "qty": 1}]}

    def test_substitutes_in_list(self):
        rv = RuntimeVariables()
        rv.set("@uid", "abc")
        lst = ["{{@uid}}", "fixed"]
        result = substitute(lst, rv)
        assert result == ["abc", "fixed"]

    def test_substitutes_auth_token(self):
        rv = RuntimeVariables()
        rv.set_auth_token("Bearer tok123")
        result = substitute("{{AUTH_TOKEN}}", rv)
        assert result == "Bearer tok123"

    def test_unsubstituted_variable_raises(self):
        rv = RuntimeVariables()
        with pytest.raises(KeyError, match="@missing"):
            substitute("{{@missing}}", rv)

    def test_no_variables_returns_unchanged(self):
        rv = RuntimeVariables()
        assert substitute("plain text", rv) == "plain text"
        assert substitute(42, rv) == 42
