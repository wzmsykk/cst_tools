from csttool.cst_process_env import cst_process_environment


def test_cst_environment_preserves_parent_and_unrelated_settings(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('CST_LICENSE_TEST', 'unchanged')
    import os
    result = cst_process_environment()
    assert 'QT_QPA_PLATFORM' not in result
    assert result['CST_LICENSE_TEST'] == 'unchanged'
    assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'


def test_plugin_paths_are_removed_case_insensitively():
    source = {'qt_plugin_path': 'python-plugin', 'QT_QPA_PLATFORM_PLUGIN_PATH': 'python-qpa',
              'PATH': 'keep', 'QT_SCALE_FACTOR': '1'}
    assert cst_process_environment(source) == {'PATH': 'keep', 'QT_SCALE_FACTOR': '1'}
    assert 'qt_plugin_path' in source
