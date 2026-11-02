from pathlib import Path
import pytest
from csttool.native_definition_builder import verify_new_com_identity,WRAPPER,render_identity_probe


class Process:
    def __init__(self,pid,name,created,path,parents=()):
        self.pid=pid;self._name=name;self.created=created;self.path=str(path);self._parents=parents
    def name(self):return self._name
    def create_time(self):return self.created
    def exe(self):return self.path
    def parents(self):return self._parents


@pytest.mark.parametrize('fault',[None,'preexisting','old','installation','parent'])
def test_only_new_selected_installation_com_ancestry_can_authorize_modelling(tmp_path,monkeypatch,fault):
    install=tmp_path/'CST2022';exe=install/'CST DESIGN ENVIRONMENT.exe'
    de=Process(100,'CST DESIGN ENVIRONMENT_AMD64.exe',10,install/'AMD64/de.exe')
    modeler=Process(101,'modeler_AMD64.exe',11,install/'AMD64/modeler.exe',[de])
    baseline=set()
    if fault=='preexisting':baseline.add((de.pid,de.created))
    if fault=='old':de.created=1
    if fault=='installation':de.path=str(tmp_path/'other/de.exe')
    if fault=='parent':modeler._parents=[]
    monkeypatch.setattr('csttool.native_definition_builder.psutil.Process',lambda pid:modeler)
    if fault:
        with pytest.raises(ValueError):verify_new_com_identity(101,exe,10,baseline)
    else:assert verify_new_com_identity(101,exe,10,baseline)==(modeler,de)


def test_wrapper_binds_before_changes_and_has_no_openfile_or_global_selection(tmp_path):
    assert WRAPPER.count('RunScript(')==1
    assert 'if ($bound) {' in WRAPPER and '$studio.Quit()' in WRAPPER
    assert 'Active3D' not in WRAPPER and 'OpenFile' not in WRAPPER
    macro=render_identity_probe(tmp_path,'a'*32)
    assert 'GetCurrentProcessId' in macro and 'StoreParameter' not in macro and 'Save' not in macro
    assert 'CSTToolsBindNewProject' in macro and 'For tick = 1 To 600' in macro
    assert 'quiet-ready.json' in macro
    assert WRAPPER.index('if ($value.nonce -eq $Nonce)') < WRAPPER.index('$studio.SetQuietMode($true)')
    assert WRAPPER.index('$studio.SetQuietMode($true)') < WRAPPER.index("$ready = Join-Path $Directory 'quiet-ready.json'")
