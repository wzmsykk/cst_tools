"""Validate the modern JSON envelope before the pinned SDK normalizes it.

The official SDK remains the message-model validator, dispatcher and writer.
The narrow input guard rejects malformed/invalid IDs, missing modern metadata
and duplicate active IDs before SDK era selection or correlation can be changed.
"""


async def run_stdio(server):
    import anyio
    import json
    import sys
    import mcp_types as types
    from pydantic import ValidationError
    from mcp.server.stdio import stdio_server
    from mcp.shared.message import SessionMessage

    ready=anyio.Event();writer=[];pending=set()
    async def error(code,message,identity=None):
        await writer[0].send(SessionMessage(types.JSONRPCError(jsonrpc='2.0',id=identity,
            error=types.ErrorData(code=code,message=message))))
    class ValidatedLines:
        def __aiter__(self):return self.lines()
        async def lines(self):
            await ready.wait()
            while True:
                raw=await anyio.to_thread.run_sync(sys.stdin.buffer.readline,abandon_on_cancel=True)
                if not raw:return
                try:
                    line=raw.decode('utf-8')
                    def invalid(value):raise ValueError('nonfinite JSON constant')
                    envelope=json.loads(line,parse_constant=invalid)
                except (UnicodeError,ValueError):
                    await error(-32700,'Parse error');continue
                # The SDK's permissive notification union drops an invalid id.
                if isinstance(envelope,dict) and 'id' in envelope and type(envelope['id']) not in (int,str):
                    await error(-32600,'Invalid Request');continue
                if (isinstance(envelope,dict) and envelope.get('jsonrpc')=='2.0'
                        and isinstance(envelope.get('method'),str) and 'id' in envelope
                        and envelope['method']!='server/discover'):
                    identity=envelope['id']
                    if envelope['method']=='initialize':
                        await error(-32022,'This service requires protocol 2026-07-28',identity);continue
                    params=envelope.get('params')
                    meta=params.get('_meta') if isinstance(params,dict) else None
                    if not isinstance(meta,dict) or 'io.modelcontextprotocol/protocolVersion' not in meta:
                        await error(-32602,'Per-request protocolVersion is required',identity);continue
                    if meta['io.modelcontextprotocol/protocolVersion']!='2026-07-28':
                        await error(-32022,'Unsupported protocol version',identity);continue
                yield line
    async with stdio_server(stdin=ValidatedLines()) as (incoming,outgoing):
        writer.append(outgoing);ready.set()
        class CheckedInput:
            def __getattr__(self,name):return getattr(incoming,name)
            async def __aenter__(self):
                await incoming.__aenter__();return self
            async def __aexit__(self,*args):return await incoming.__aexit__(*args)
            def __aiter__(self):return self
            async def __anext__(self):
                try:return await self.receive()
                except anyio.EndOfStream:raise StopAsyncIteration
            async def receive(self):
                while True:
                    item=await incoming.receive()
                    if not isinstance(item,Exception):
                        message=item.message
                        if isinstance(message,types.JSONRPCRequest):
                            if message.id in pending:
                                await error(-32600,'Duplicate request id',message.id);continue
                            pending.add(message.id)
                        if isinstance(message,types.JSONRPCNotification) and message.method=='notifications/cancelled':
                            identity=(message.params or {}).get('requestId')
                            if type(identity) in (int,str):pending.discard(identity)
                        return item
                    if not isinstance(item,ValidationError):raise item
                    parse=any(e['type']=='json_invalid' for e in item.errors())
                    code,message=(-32700,'Parse error') if parse else (-32600,'Invalid Request')
                    await error(code,message)
        class CheckedOutput:
            def __getattr__(self,name):return getattr(outgoing,name)
            async def __aenter__(self):
                await outgoing.__aenter__();return self
            async def __aexit__(self,*args):return await outgoing.__aexit__(*args)
            async def send(self,item):
                if isinstance(item.message,(types.JSONRPCResponse,types.JSONRPCError)):
                    pending.discard(item.message.id)
                await outgoing.send(item)
        await server._lowlevel_server.run(CheckedInput(),CheckedOutput(),
            server._lowlevel_server.create_initialization_options())
