from test.cst_integration_support import force_cleanup


def test_failed_constructor_cleanup_preserves_error_and_other_sessions(monkeypatch):
    def unexpected(*args):
        raise AssertionError('must not enumerate or kill unrelated sessions')
    monkeypatch.setattr('test.cst_integration_support.new_cst_processes', unexpected)
    assert force_cleanup(None, {}) == {}
