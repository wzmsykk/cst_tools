"""Official SDK wire acceptance. Optional SDK dependency; no CST or Runner launch."""
import asyncio
from pathlib import Path
import sys
import pytest
pytest.importorskip('mcp')
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from csttool.mcp_server import create_server
from test.mcp_application_adapter_test import Client as FakeClient
from csttool.mcp_server import MCPApplicationAdapter


def test_official_modern_sdk_dispatch_and_input_errors(tmp_path):
    async def run():
        server=create_server(tmp_path,adapter=MCPApplicationAdapter(tmp_path,client_factory=FakeClient))
        async with Client(server,mode='2026-07-28') as client:
            tools=await client.list_tools()
            assert len(tools.tools)==14
            assert [t.name for t in tools.tools]==sorted(t.name for t in tools.tools)
            assert tools.ttl_ms==0 and tools.cache_scope=='private'
            assert 'create_project' in [t.name for t in tools.tools]
            result=await client.call_tool('get_project_status',{})
            assert result.structured_content==dict(state='IDLE')
            assert result.result_type=='complete'
            result=await client.call_tool('submit_run',dict(control_handle='bad',document_id='doc',definition_revision='a'*64,request_id='one'))
            assert result.is_error
            assert 'CONTROL_HANDLE_INVALID' in result.content[0].text
            result=await client.call_tool('get_project_status',dict(unexpected=True))
            assert result.is_error
            assert all(t.input_schema['additionalProperties'] is False for t in tools.tools)
            result=await client.call_tool('apply_model_changes',dict(control_handle='bad',document_id='doc',
                expected_document_revision='a'*64,request_id='one',changes=[{'op':'arbitrary_vba','code':'Kill x'}]))
            assert result.is_error
            assert 'INVALID_ARGUMENT' in result.content[0].text
            from mcp.shared.exceptions import MCPError
            with pytest.raises(MCPError):await client.list_resources()
    asyncio.run(run())


def test_official_modern_stdio_discovery_and_eof(tmp_path):
    async def run():
        params=StdioServerParameters(command=sys.executable,args=['-m','csttool.mcp_server','--project',str(tmp_path)],cwd=Path(__file__).parents[1])
        async with Client(params,mode='auto',read_timeout_seconds=10) as client:
            assert client.protocol_version=='2026-07-28'
            assert client.server_capabilities.model_dump(exclude_none=True)=={'tools':{}}
            result=await client.list_tools()
            assert {t.name for t in result.tools}=={'connect_project','control_project','submit_run','get_simulation_results','get_project_status','create_project','inspect_model','get_operation_result','list_installations','apply_model_changes','configure_simulation','save_project','close_project','export_simulation_results'}
            result=await client.call_tool('get_project_status',{})
            assert result.is_error  # No existing Runner; a query must not launch one.
        assert not (tmp_path/'control/runner.json').exists()
    asyncio.run(run())


def test_legacy_calls_are_not_business_compatibility(tmp_path):
    async def run():
        server=create_server(tmp_path,adapter=MCPApplicationAdapter(tmp_path,client_factory=FakeClient))
        from mcp.shared.exceptions import MCPError
        with pytest.raises((MCPError,BaseExceptionGroup)):
            async with Client(server,mode='legacy') as client:
                await client.list_tools()
    asyncio.run(run())


@pytest.mark.parametrize('name,arguments', [
    ('get_project_status', {'unexpected': True}),
    ('connect_project', {'client_id': 'caller', 'launch': 'yes'}),
    ('create_project', {'control_handle': 'bad', 'name': 'new', 'installation_ref': 'local',
                        'request_id': 'one', 'executable': 'injected.exe'}),
    ('submit_run', {'control_handle': 'bad', 'document_id': 'doc',
                    'definition_revision': 'a'*64, 'request_id': 'one', 'parameters': {}}),
])
def test_modern_invalid_inputs_are_errors_without_business_dispatch(tmp_path, name, arguments):
    async def run():
        FakeClient.calls = []
        server = create_server(tmp_path, adapter=MCPApplicationAdapter(tmp_path, client_factory=FakeClient))
        async with Client(server, mode='2026-07-28') as client:
            result = await client.call_tool(name, arguments)
            assert result.is_error and result.result_type == 'complete'
            assert FakeClient.calls == []
    asyncio.run(run())


def test_modern_unicode_payload_and_error_do_not_poison_next_call(tmp_path):
    class UnicodePeer(FakeClient):
        def status(self): return {'state': 'IDLE', 'detail': '中文项目\\路径\n下一行'}
    async def run():
        server = create_server(tmp_path, adapter=MCPApplicationAdapter(tmp_path, client_factory=UnicodePeer))
        async with Client(server, mode='2026-07-28') as client:
            before = await client.list_tools()
            error = await client.call_tool('submit_run', dict(control_handle='bad', document_id='doc',
                definition_revision='a'*64, request_id='one'))
            assert error.is_error
            result = await client.call_tool('get_project_status', {})
            assert result.structured_content == {'state': 'IDLE', 'detail': '中文项目\\路径\n下一行'}
            after = await client.list_tools()
            assert [t.name for t in before.tools] == [t.name for t in after.tools]
            assert after.ttl_ms == 0 and after.cache_scope == 'private'
    asyncio.run(run())
