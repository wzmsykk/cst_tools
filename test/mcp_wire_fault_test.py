"""Raw modern stdio messages, bounded transport waits; no Runner/CST launch."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import pytest

pytest.importorskip('mcp')
META = {'io.modelcontextprotocol/protocolVersion':'2026-07-28',
        'io.modelcontextprotocol/clientCapabilities':{}}


@pytest.fixture
def wire(tmp_path,request):
    errors = (tmp_path/'stderr.log').open('wb')
    command=[sys.executable, '-m', 'csttool.mcp_server', '--project', str(tmp_path)]
    if getattr(request,'param',False) is True:
        script=tmp_path/'slow_peer.py'
        script.write_text('import sys,time\nfrom pathlib import Path\n'
            +f'sys.path.insert(0,{str(Path(__file__).parents[1])!r})\n'
            +'from csttool.mcp_server import create_server\n'
            +f'root=Path({str(tmp_path)!r})\n'
            +'class Peer:\n def get_status(self):\n'
            +'  with (root/"calls.txt").open("a") as f:f.write("call\\n")\n'
            +'  (root/"entered").touch()\n  time.sleep(1.5)\n  return {"state":"IDLE"}\n'
            +'create_server(root,adapter=Peer()).run(transport="stdio")\n',encoding='utf-8')
        command=[sys.executable,str(script)]
    if getattr(request,'param',False)=='output':
        script=tmp_path/'output_peer.py'
        script.write_text('import sys\nfrom pathlib import Path\n'
            +f'sys.path.insert(0,{str(Path(__file__).parents[1])!r})\n'
            +'from csttool.mcp_server import create_server\n'
            +'class Peer:\n count=0\n def get_status(self):\n'
            +'  self.count+=1\n  return {"value":float("nan")} if self.count==1 else {"state":"中文\\n结果"}\n'
            +'create_server(Path.cwd(),adapter=Peer()).run(transport="stdio")\n',encoding='utf-8')
        command=[sys.executable,str(script)]
    child = subprocess.Popen(command,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, cwd=Path(__file__).parents[1])
    rows = queue.Queue()
    def reject_nonfinite(value):
        raise ValueError("nonfinite JSON output: "+value)
    def reader():
        for line in child.stdout:
            try:
                rows.put(json.loads(line,parse_constant=reject_nonfinite))
            except Exception as error:
                rows.put(error)
    def receive(timeout=10):
        value=rows.get(timeout=timeout)
        if isinstance(value,Exception):raise value
        return value
    thread=threading.Thread(target=reader,daemon=True);thread.start()
    def call(method, *, params=None, identity=1):
        message={'jsonrpc':'2.0','id':identity,'method':method,'params':{'_meta':META,**(params or {})}}
        child.stdin.write((json.dumps(message,ensure_ascii=False)+'\n').encode('utf-8'));child.stdin.flush()
        return receive()
    def notify(method, params):
        child.stdin.write((json.dumps({'jsonrpc':'2.0','method':method,'params':params})+'\n').encode('utf-8'))
        child.stdin.flush()
    call.notify = notify
    def raw(value):
        child.stdin.write((value+'\n').encode('utf-8'));child.stdin.flush()
        return receive()
    call.raw = raw
    call.send_raw=lambda value:(child.stdin.write((value+'\n').encode('utf-8')),child.stdin.flush())
    call.receive=receive
    call.directory=tmp_path
    try: yield call
    finally:
        child.stdin.close()
        try: child.wait(timeout=10)
        finally:
            errors.close(); child.stdout.close()
        assert child.returncode==0
        assert not (tmp_path/'control/runner.json').exists()


def test_discover_without_initialize_and_error_does_not_poison_wire(wire):
    discovered=wire('server/discover')
    assert '2026-07-28' in discovered['result']['supportedVersions']
    error=wire('resources/list',identity=2)
    assert error['id']==2 and error['error']['code']==-32601
    tools=wire('tools/list',identity=3)
    assert tools['id']==3 and tools['result']['cacheScope']=='private'
    assert len(tools['result']['tools'])==14


@pytest.mark.parametrize('version',['2025-03-26','2099-01-01'])
def test_unknown_or_legacy_version_is_rejected_per_request(wire,version):
    wrong={**META,'io.modelcontextprotocol/protocolVersion':version}
    error=wire('tools/list',params={'_meta':wrong})
    assert error['error']['code']==-32022
    assert 'result' in wire('tools/list',identity=2)


def test_wire_input_error_and_unicode_are_valid_single_line_responses(wire):
    result=wire('tools/call',params={'name':'connect_project','arguments':{'client_id':'非法 客户'}})
    assert result['result']['isError'] is True
    assert result['result']['resultType']=='complete'
    assert 'result' in wire('tools/list',identity=2)


def test_unknown_cancellation_notification_has_no_reply_or_next_request_interference(wire):
    wire.notify('notifications/cancelled', {'requestId':'not-active','reason':'test only'})
    result=wire('tools/list',identity=42)
    assert result['id']==42 and 'result' in result


@pytest.mark.parametrize('message,code', [('{broken',-32700),('[]',-32600),
    ('{"jsonrpc":"2.0","id":null,"method":"tools/list"}',-32600),
    ('{"jsonrpc":"2.0","id":true,"method":"tools/list"}',-32600),
    ('{"jsonrpc":"1.0","id":1,"method":"tools/list"}',-32600)])
def test_invalid_wire_has_error_without_dispatch_and_next_request_survives(wire,message,code):
    result=wire.raw(message)
    assert result['error']['code']==code and result['id'] is None
    assert 'result' in wire('tools/list',identity=99)


@pytest.mark.parametrize('meta',[{}, {'io.modelcontextprotocol/protocolVersion':'2026-07-28'}])
def test_missing_required_per_request_metadata_is_invalid_params(wire,meta):
    result=wire('tools/list',params={'_meta':meta})
    assert result['error']['code']==-32602
    assert 'result' in wire('tools/list',identity=2)


def slow_request(wire):
    wire.send_raw(json.dumps(dict(jsonrpc='2.0',id=1,method='tools/call',
        params={'_meta':META,'name':'get_project_status','arguments':{}})))
    deadline=time.monotonic()+10
    while not (wire.directory/'entered').exists():
        assert time.monotonic()<deadline
        time.sleep(.01)


@pytest.mark.parametrize('wire',[True],indirect=True)
def test_duplicate_inflight_id_does_not_replace_first_handler_or_dispatch_twice(wire):
    slow_request(wire)
    wire.send_raw(json.dumps(dict(jsonrpc='2.0',id=1,method='tools/call',
        params={'_meta':META,'name':'get_project_status','arguments':{}})))
    rejected=wire.receive(timeout=10)
    assert rejected['error']['code']==-32600 and rejected['id']==1
    original=wire.receive(timeout=10)
    assert original['id']==1 and original['result']['structuredContent']=={'state':'IDLE'}
    assert (wire.directory/'calls.txt').read_text().splitlines()==['call']
    assert 'result' in wire('tools/list',identity=2)


@pytest.mark.parametrize('wire',[True],indirect=True)
def test_active_cancel_sends_no_late_response_and_next_request_survives(wire):
    slow_request(wire)
    wire.notify('notifications/cancelled',{'requestId':1,'reason':'test'})
    result=wire('tools/list',identity=2)
    assert result['id']==2 and 'result' in result
    time.sleep(2)
    with pytest.raises(queue.Empty):wire.receive(timeout=.2)
    assert (wire.directory/'calls.txt').read_text().splitlines()==['call']


def test_unknown_tool_is_a_protocol_error_and_next_request_survives(wire):
    result=wire('tools/call',params={'name':'unknown_tool','arguments':{}})
    assert result['error']['code']==-32602
    assert 'result' not in result
    assert len(wire('tools/list',identity=2)['result']['tools'])==14


@pytest.mark.parametrize('wire',['output'],indirect=True)
def test_invalid_output_is_rejected_and_valid_unicode_survives_on_wire(wire):
    result=wire('tools/call',params={'name':'get_project_status','arguments':{}})['result']
    assert result['isError'] is True
    assert 'INVALID_OUTPUT' in str(result['content'])
    good=wire('tools/call',params={'name':'get_project_status','arguments':{}},identity=2)['result']
    assert good['structuredContent']=={'state':'中文\n结果'}
    assert not good.get('isError',False)
