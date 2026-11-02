import pytest
from csttool.mcp_server import MCPApplicationAdapter


class Client:
    calls=[]
    def __init__(self,project,client_id=None):self.client_id=client_id
    def connect(self,*,launch):self.calls.append(('connect',launch));return dict(state='IDLE')
    def status(self):self.calls.append(('status',));return dict(state='IDLE')
    def command(self,*args,**kwargs):self.calls.append((args,kwargs));return dict(accepted=True)
    def simulation_results(self,*args):self.calls.append(('results',args));return dict(status='success')


def test_transport_delegates_without_launching_on_reads(tmp_path):
    Client.calls=[]
    service=MCPApplicationAdapter(tmp_path,client_factory=Client)
    service.get_status();service.results('run-one')
    assert all(c[0]!='connect' for c in Client.calls)
    connection=service.connect_project('caller-a')
    assert Client.calls[-1]==('connect',False)
    service.submit_run(connection['control_handle'],'doc','a'*64,'req-one')
    args,kw=Client.calls[-1]
    assert args==('start',dict(kind='simulation',document_id='doc',definition_revision='a'*64))
    assert kw['request_id']=='req-one'
    with pytest.raises(ValueError,match='CONTROL_HANDLE_INVALID'):
        service.control('bad','stop','req-two')
    with pytest.raises(ValueError):service.control(connection['control_handle'],'start','req-two')


def test_explicit_handle_lost_on_adapter_restart(tmp_path):
    service=MCPApplicationAdapter(tmp_path,client_factory=Client)
    old=service.connect_project('caller-a')['control_handle']
    restarted=MCPApplicationAdapter(tmp_path,client_factory=Client)
    with pytest.raises(ValueError):restarted.submit_run(old,'doc','a'*64,'request')


def test_caller_handles_have_a_bound(tmp_path):
    service=MCPApplicationAdapter(tmp_path,client_factory=Client)
    for i in range(64):service.connect_project('caller-'+str(i))
    with pytest.raises(ValueError,match='RESOURCE_LIMIT'):service.connect_project('caller-overflow')
