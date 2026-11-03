"""Raw modern stdio messages, bounded transport waits; no Runner/CST launch."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import pytest

pytest.importorskip('mcp')
META = {'io.modelcontextprotocol/protocolVersion':'2026-07-28',
        'io.modelcontextprotocol/clientCapabilities':{}}


@pytest.fixture
def wire(tmp_path):
    errors = (tmp_path/'stderr.log').open('wb')
    child = subprocess.Popen([sys.executable, '-m', 'csttool.mcp_server', '--project', str(tmp_path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, cwd=Path(__file__).parents[1])
    rows = queue.Queue()
    def reader():
        for line in child.stdout: rows.put(json.loads(line))
    thread=threading.Thread(target=reader,daemon=True);thread.start()
    def call(method, *, params=None, identity=1):
        message={'jsonrpc':'2.0','id':identity,'method':method,'params':{'_meta':META,**(params or {})}}
        child.stdin.write((json.dumps(message,ensure_ascii=False)+'\n').encode('utf-8'));child.stdin.flush()
        return rows.get(timeout=10)
    def notify(method, params):
        child.stdin.write((json.dumps({'jsonrpc':'2.0','method':method,'params':params})+'\n').encode('utf-8'))
        child.stdin.flush()
    call.notify = notify
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
