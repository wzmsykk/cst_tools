"""Strict managed Model.mod projection on the shared immutable CST source reader."""
import re
from dataclasses import replace
from types import MappingProxyType
from .settings_projection import (HISTORY,PARAMETERS,GEOMETRY_PROFILE,Projection,project_geometry_history,
                                  project_history,_statements)
from .winwrap_emitter import GeneratedCodeError

GEO_SIM_PROFILE='cst-geo-eigenmode-history-v1'


def extract_program(source):
    """Only owned caption/version syntax; never fold arbitrary imported history."""
    text=source.text(HISTORY)
    if text is None or len(text.encode('utf-8'))>2*1024*1024:raise GeneratedCodeError('managed history missing/too large')
    blocks=[];caption=None;body=[]
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith("'@ "):
            if caption is not None:blocks.append(dict(caption=caption,history='\n'.join(body).strip()))
            caption=stripped[3:];body=[]
            if not caption.startswith(('CST Tools GEO ','CST Tools A1 ','CST Tools SIM ')):
                raise GeneratedCodeError('unmanaged history caption')
        elif not stripped or stripped.startswith("'[VERSION]"):continue
        elif caption is None:
            if not stripped.startswith("'#"):raise GeneratedCodeError('unmanaged history preamble')
        elif stripped.startswith("'"):raise GeneratedCodeError('unexpected managed block annotation')
        else:body.append(line)
    if caption is not None:blocks.append(dict(caption=caption,history='\n'.join(body).strip()))
    if not blocks or len(blocks)>560:raise GeneratedCodeError('managed block budget')
    if len({b['caption'] for b in blocks})!=len(blocks):raise GeneratedCodeError('duplicate saved block identity')
    return tuple(blocks)


def _canonical(text):
    # Ignore native whitespace/case outside string literals only. This never
    # substitutes evaluated values for expressions or rewrites symbolic inputs.
    return tuple(''.join(part if i%2 else re.sub(r'\s+','',part).lower()
                        for i,part in enumerate(re.split(r'("(?:[^"]|"")*")',statement)))
                 for statement,*_ in _statements(text))


def verify_saved_program(source,spec):
    from .history_program import partition,validate,logical_geometry
    actual=extract_program(source);expected=partition(spec)
    if len(actual)!=len(expected) or any(a['caption']!=b['caption'] or _canonical(a['history'])!=_canonical(b['history'])
                                       for a,b in zip(actual,expected)):
        raise GeneratedCodeError('saved block order/body/symbolic expressions differ from current declaration')
    validate(actual,spec)
    parameters=source.json(PARAMETERS)
    rows=parameters.get('parameters') if isinstance(parameters,dict) else None
    if not isinstance(rows,list):raise GeneratedCodeError('managed parameters missing')
    wanted={name:(r['expression'],r['description']) for name,r in spec['parameters'].items()}
    if (len(rows)!=len(wanted) or any(not isinstance(r,dict) for r in rows)
            or {r.get('name'):(r.get('expr'),r.get('descr')) for r in rows}!=wanted):
        raise GeneratedCodeError('saved parameter expressions/descriptions differ')
    if 'geometry' not in spec:
        return project_history('\n'.join(b['history'] for b in actual),rows,scope=source.scope,
            available_scopes=source.scopes,source_hash=source.sha256,member_hash=source.member_hashes[HISTORY],require_identity=True)
    geometry=tuple(b for b in actual if not b['caption'].startswith('CST Tools SIM '))
    report=project_geometry_history(logical_geometry(geometry),rows,scope=source.scope,available_scopes=source.scopes,source_hash=source.sha256)
    if report.status!='resolved' or report.missing_fields:raise GeneratedCodeError('saved GEO history unresolved')
    if 'simulation' not in spec:return report
    settings=[b['history'] for b in actual if b['caption'] in ('CST Tools GEO units','CST Tools GEO wcs') or b['caption'].startswith('CST Tools SIM ')]
    simulation=project_history('\n'.join(settings),rows,scope=source.scope,available_scopes=source.scopes,
        source_hash=source.sha256,member_hash=source.member_hashes[HISTORY],require_identity=True)
    if simulation.status!='resolved':raise GeneratedCodeError('saved simulation settings unresolved')
    return replace(report,parser_profile=GEO_SIM_PROFILE,
        fields=MappingProxyType({**report.fields,**simulation.fields}),
        origins=MappingProxyType({**report.origins,**simulation.origins}),
        exact_values=MappingProxyType({**report.exact_values,**simulation.exact_values}))
