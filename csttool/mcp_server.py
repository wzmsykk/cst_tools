"""Optional modern MCP stdio adapter; all execution remains in the Runner.

Only implemented operations are advertised. No Qt, worker or CST object belongs
in this process. EOF closes the adapter, not an independent run.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import threading
from .runner_client import RunnerClient


def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):
        raise ValueError('INVALID_ARGUMENT: invalid identity')
    return value


class MCPApplicationAdapter:
    """Small transport adapter; client handles do not replace Runner leases."""
    def __init__(self,project,*,client_factory=RunnerClient):
        self.project=Path(project).resolve()
        self.client_factory=client_factory
        self.handles={}
        self.lock=threading.Lock()

    def connect_project(self,client_id,*,launch=False):
        client_id=_identifier(client_id)
        with self.lock:
            if client_id not in self.handles:
                if len(self.handles)>=64:
                    raise ValueError('RESOURCE_LIMIT: at most 64 caller handles per adapter')
                self.handles[client_id]=(secrets.token_urlsafe(32),self.client_factory(self.project,client_id=client_id))
            handle,client=self.handles[client_id]
        status=client.connect(launch=launch)
        return dict(control_handle=handle,status=status)

    def _client(self,handle):
        _identifier(handle)
        with self.lock:
            for known,client in self.handles.values():
                if secrets.compare_digest(known,handle):return client
        raise ValueError('CONTROL_HANDLE_INVALID: reconnect explicitly')

    def get_status(self):
        return self.client_factory(self.project).status()  # Never launch on query.

    def control(self,handle,operation,request_id,run_id=None):
        if operation not in ('claim','release','stop','recover','shutdown'):
            raise ValueError('INVALID_ARGUMENT: unsupported control operation')
        return self._client(handle).command(operation,request_id=_identifier(request_id),
                                           run_id=_identifier(run_id) if run_id is not None else None)

    def submit_run(self,handle,document_id,definition_revision,request_id):
        return self._client(handle).command('start',dict(kind='simulation',
            document_id=_identifier(document_id),definition_revision=_identifier(definition_revision)),
            request_id=_identifier(request_id))

    def create_project(self,handle,name,installation_ref,request_id):
        return self._client(handle).command('start',dict(kind='definition',operation='create_project',
            name=_identifier(name),installation_ref=_identifier(installation_ref),module='mws',
            units={'length':'mm','frequency':'MHz'}),request_id=_identifier(request_id))

    def edit_model(self,handle,operation,arguments,request_id):
        from .definition_editing import validate_edit
        payload=dict(kind='definition',operation=operation,**arguments)
        validate_edit(payload)
        return self._client(handle).command('start',payload,request_id=_identifier(request_id))

    def export_results(self,handle,run_id,result_revision,formats,request_id):
        return self._client(handle).command('export_simulation_results',dict(run_id=_identifier(run_id),
            result_revision=_identifier(result_revision),formats=formats),request_id=_identifier(request_id))

    def inspect_model(self,document_id,document_revision):
        return self.client_factory(self.project).inspect_model(_identifier(document_id),_identifier(document_revision))

    def operation_result(self,run_id):
        return self.client_factory(self.project).definition_result(_identifier(run_id))

    def installations(self):return self.client_factory(self.project).installations()

    def results(self,run_id,result_revision=None):
        return self.client_factory(self.project).simulation_results(_identifier(run_id),
            _identifier(result_revision) if result_revision is not None else None)


def create_server(project,*,adapter=None):
    # Optional dependency; importing ordinary GUI/Runner never imports the SDK.
    from mcp.server import MCPServer
    from mcp_types import ToolAnnotations
    from typing import Literal
    class StrictServer(MCPServer):
        async def run_stdio_async(self):
            from .mcp_stdio import run_stdio
            await run_stdio(self)
        async def list_tools(self):
            tools=await super().list_tools()
            from copy import deepcopy
            from .definition_editing import SCHEMA,EDIT_OPERATIONS
            for tool in tools:
                tool.input_schema['additionalProperties']=False
                if tool.name in EDIT_OPERATIONS:
                    arguments=deepcopy(SCHEMA['$defs'][tool.name])
                    tool.input_schema['properties'].update(arguments['properties'])
                    tool.input_schema['$defs']=deepcopy(SCHEMA['$defs'])
                    tool.input_schema['required']=list(dict.fromkeys(tool.input_schema.get('required',[])+arguments['required']))
            return sorted(tools,key=lambda tool:tool.name)

        async def call_tool(self,name,arguments,context=None):
            from jsonschema import Draft202012Validator
            from mcp.shared.exceptions import MCPError
            from mcp.server.mcpserver.exceptions import ToolError
            for tool in await self.list_tools():
                if tool.name==name:
                    error=next(Draft202012Validator(tool.input_schema).iter_errors(arguments),None)
                    if error is not None:
                        raise ToolError('INVALID_ARGUMENT: tool input does not match schema')
                    break
            else:
                raise MCPError(-32602,'Unknown tool: '+name)
            try:
                return await super().call_tool(name,arguments,context)
            except ValueError as error:
                raise ToolError(str(error)) from None

    async def modern_only(context,call_next):
        from mcp.shared.exceptions import MCPError
        if context.method not in ('server/discover','initialize'):
            meta=(context.params or {}).get('_meta',{})
            if not isinstance(meta,dict) or 'io.modelcontextprotocol/protocolVersion' not in meta:
                raise MCPError(-32602,'Per-request protocolVersion is required')
        if context.method!='server/discover' and context.protocol_version!='2026-07-28':
            raise MCPError(-32022,'Unsupported protocol version; requires 2026-07-28')
        if context.method not in ('server/discover','tools/list','tools/call'):
            raise MCPError(-32601,'Method not supported by this tools-only service')
        result=await call_next(context)
        if context.method=='server/discover':
            return {**result,'supportedVersions':['2026-07-28'],'capabilities':{'tools':{}}}
        return result

    server=StrictServer('CST Tools',middleware=[modern_only])
    application=adapter or MCPApplicationAdapter(project)
    inflight=threading.BoundedSemaphore(8)

    def invoke(function,*args,**kwargs):
        from mcp.server.mcpserver.exceptions import ToolError
        from .runner_client import RunnerRejected
        if not inflight.acquire(blocking=False):raise ToolError('RATE_LIMITED: adapter request capacity exceeded')
        try:
            result=function(*args,**kwargs)
            try:
                if not isinstance(result,dict):raise TypeError('output must be an object')
                json.dumps(result,allow_nan=False)
            except (TypeError,ValueError,OverflowError,RecursionError):
                raise ToolError('INVALID_OUTPUT: backend result must be a finite JSON object; inspect Runner diagnostics') from None
            return result
        except ToolError:raise
        except (ValueError,RunnerRejected) as error:
            raise ToolError(str(error)) from None
        except (OSError,RuntimeError) as error:
            raise ToolError('RUNNER_UNAVAILABLE: '+str(error)) from None
        finally:inflight.release()

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_project_status() -> dict[str, object]:
        """Read existing Runner status. Does not launch Runner or CST."""
        return invoke(application.get_status)

    @server.tool()
    def connect_project(client_id:str,launch:bool=False) -> dict[str, object]:
        """Explicitly connect a caller; launch=True may start the independent Runner."""
        return invoke(application.connect_project,client_id,launch=launch)

    @server.tool()
    def control_project(control_handle:str,operation:Literal['claim','release','stop','recover','shutdown'],
                        request_id:str,run_id:str|None=None) -> dict[str, object]:
        """Control through Runner ownership/lease checks; recover never repeats a solve."""
        return invoke(application.control,control_handle,operation,request_id,run_id)

    @server.tool()
    def submit_run(control_handle:str,document_id:str,definition_revision:str,request_id:str) -> dict[str, object]:
        """Submit one verified immutable simulation definition. Reuse request_id after response loss."""
        return invoke(application.submit_run,control_handle,document_id,definition_revision,request_id)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_simulation_results(run_id:str,result_revision:str|None=None) -> dict[str, object]:
        """Read adopted frequency/RQ with provenance. No compute or artifact adoption."""
        return invoke(application.results,run_id,result_revision)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_installations() -> dict[str, object]:
        """List server-authorized opaque CST installation references; no CST launch."""
        return invoke(application.installations)

    @server.tool()
    def create_project(control_handle:str,name:str,installation_ref:str,request_id:str) -> dict[str, object]:
        """Create a new empty MWS project (mm/MHz) in the Runner slot. Poll status and get_operation_result."""
        return invoke(application.create_project,control_handle,name,installation_ref,request_id)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_operation_result(run_id:str) -> dict[str, object]:
        """Read a completed definition operation, not a simulation result."""
        return invoke(application.operation_result,run_id)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def inspect_model(document_id:str,document_revision:str) -> dict[str, object]:
        """Read immutable saved document identity and hash. Does not open CST."""
        return invoke(application.inspect_model,document_id,document_revision)

    @server.tool()
    def apply_model_changes(control_handle:str,document_id:str,expected_document_revision:str,
                            changes:list[dict[str,object]],request_id:str,invalidate_results:bool=False,
                            geometry_profile:Literal['geometry-v1']|None=None) -> dict[str,object]:
        """Commit a typed immutable draft. No CST opens; saved results remain immutable."""
        arguments=dict(document_id=document_id,expected_document_revision=expected_document_revision,
                       changes=changes,invalidate_results=invalidate_results)
        if geometry_profile is not None:arguments['geometry_profile']=geometry_profile
        return invoke(application.edit_model,control_handle,'apply_model_changes',arguments,request_id)

    @server.tool()
    def configure_simulation(control_handle:str,document_id:str,expected_document_revision:str,
                             simulation:dict[str,object],postprocess:list[dict[str,object]],request_id:str) -> dict[str,object]:
        """Configure supported A1/GEO Tet/Default single-mode Frequency/RQ settings."""
        return invoke(application.edit_model,control_handle,'configure_simulation',dict(document_id=document_id,
            expected_document_revision=expected_document_revision,simulation=simulation,postprocess=postprocess),request_id)

    @server.tool()
    def save_project(control_handle:str,document_id:str,expected_document_revision:str,request_id:str,verify_reopen:bool=True,
                     validation_target:Literal['geometry','simulation']|None=None) -> dict[str,object]:
        """Build a copy and verify saved/reopened settings through G03. Never solves."""
        arguments=dict(document_id=document_id,expected_document_revision=expected_document_revision,verify_reopen=verify_reopen)
        if validation_target is not None:arguments['validation_target']=validation_target
        return invoke(application.edit_model,control_handle,'save_project',arguments,request_id)

    @server.tool()
    def close_project(control_handle:str,document_id:str,expected_document_revision:str,
                      disposition:Literal['save','discard_candidate'],request_id:str) -> dict[str,object]:
        """Close the logical document; native sessions are already closed per operation."""
        return invoke(application.edit_model,control_handle,'close_project',dict(document_id=document_id,
            expected_document_revision=expected_document_revision,disposition=disposition),request_id)

    @server.tool()
    def export_simulation_results(control_handle:str,run_id:str,result_revision:str,
                                   formats:list[Literal['json','csv']],request_id:str) -> dict[str,object]:
        """Export adopted results with hashes. Deterministic retry, no CST launch."""
        return invoke(application.export_results,control_handle,run_id,result_revision,formats,request_id)

    return server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True,type=Path)
    args=parser.parse_args()
    create_server(args.project).run(transport='stdio')

if __name__=='__main__':main()
