"""Read-only saved-project preflight and atomic mask registration; never solve."""
import os
import logging
from pathlib import Path
import subprocess

import numpy as np

from .acceptance_session import exclusive_probe, wait_probe
from .configuration import read_json, write_json_atomic
from .cst_process_env import cst_process_environment
from .field_artifacts import SamplingSpec
from .geometry_support import render_material_support, load_material_support
from .physical_domain import common_quadrature
from .result_reconciliation import file_hash


def render_vacuum_preflight(destination):
    path = str(Path(destination)).replace('"', '""')
    if '\n' in path or '\r' in path:
        raise ValueError('invalid probe path')
    return f'''
Sub CSTDOM_Preflight
    Dim f As Integer, i As Long, shape As String, factor As Double
    Dim a As Double,b As Double,c As Double,d As Double,e As Double,g As Double
    f=FreeFile
    Open "{path}" For Output As #f
    Print #f,"background" & vbTab & Material.GetTypeOfBackgroundMaterial
    Print #f,"boundaries" & vbTab & Boundary.GetXmin & vbTab & Boundary.GetXmax & vbTab & Boundary.GetYmin & vbTab & Boundary.GetYmax & vbTab & Boundary.GetZmin & vbTab & Boundary.GetZmax
    Print #f,"symmetry" & vbTab & Boundary.GetXSymmetry & vbTab & Boundary.GetYSymmetry & vbTab & Boundary.GetZSymmetry
    Print #f,"ports" & vbTab & CStr(Port.StartPortNumberIteration)
    factor=Units.GetGeometryUnitToSI
    If factor<=0 Then Err.Raise vbObjectError+2601,"domain","Invalid geometry units"
    For i=0 To Solid.GetNumberOfShapes-1
        shape=Solid.GetNameOfShapeFromIndex(i)
        If Not Solid.IsSolidShape(shape) Then Err.Raise vbObjectError+2602,"domain","Non-volume shape"
        If Not Solid.GetLooseBoundingBoxOfShape(shape,a,b,c,d,e,g) Then Err.Raise vbObjectError+2603,"domain","No solid bounds"
        Print #f,"solid" & vbTab & shape & vbTab & Solid.GetMaterialNameForShape(shape) & vbTab & CStr(a*factor) & vbTab & CStr(b*factor) & vbTab & CStr(c*factor) & vbTab & CStr(d*factor) & vbTab & CStr(e*factor) & vbTab & CStr(g*factor)
    Next i
    Close #f
End Sub
'''


def validate_inventory(path, sampling):
    inventory = {'solids': []}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        parts = line.split('\t')
        if parts[0] == 'solid':
            if len(parts) != 9:
                raise ValueError('invalid solid inventory')
            inventory['solids'].append({'name': parts[1], 'material': parts[2],
                                        'bounds_m': [float(x) for x in parts[3:]]})
        elif parts[0] in inventory:
            raise ValueError('duplicate inventory key')
        else:
            inventory[parts[0]] = parts[1:]
    reasons = []
    if inventory.get('background') != ['PEC']:
        reasons.append('background-not-PEC')
    if inventory.get('boundaries') != ['electric']*6:
        reasons.append('boundaries-not-six-electric')
    if inventory.get('symmetry') != ['none']*3:
        reasons.append('symmetry-not-none')
    if inventory.get('ports') != ['0']:
        reasons.append('ports-present-or-unknown')
    if sampling.scope != 'specified-domain':
        reasons.append('ROI-not-full-domain')
    if not inventory['solids']:
        reasons.append('no-explicit-vacuum-solids')
    names = [s['name'] for s in inventory['solids']]
    if len(set(names)) != len(names):
        reasons.append('duplicate-solid-name')
    for solid in inventory['solids']:
        bounds = solid['bounds_m']
        if solid['material'] != 'Vacuum':
            reasons.append('non-vacuum-solid')
        if not np.isfinite(bounds).all() or any(bounds[2*i]>=bounds[2*i+1] for i in range(3)):
            reasons.append('invalid-volume-bounds')
        if any(sampling.bounds_m[2*i] > bounds[2*i]+1e-9 or
               sampling.bounds_m[2*i+1] < bounds[2*i+1]-1e-9 for i in range(3)):
            reasons.append('sampling-box-does-not-cover-solid')
    return inventory, sorted(set(reasons))


def register_vacuum_domain(executable, source, destination, sampling, *, geometry_id):
    """Fresh isolated probe; rejected projects get a report, never a valid mask."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source.suffix.lower() != '.cst' or not source.is_file() or not geometry_id:
        raise ValueError('CST source and explicit fixed geometry identity required')
    if destination.exists():
        raise FileExistsError('use a fresh domain registration directory')
    destination.mkdir(parents=True)
    before = file_hash(source)
    report = {'schema_version': 1, 'status': 'incomplete', 'source': str(source),
              'source_sha256': before, 'geometry_id': geometry_id,
              'sampling': sampling.to_mapping(), 'sampling_id': sampling.identity,
              'solver_run': False, 'sampling_convergence_confirmed': False}
    q = lambda value: str(value).replace('"', '""')
    macro = f'''\n'#Language "WWB-COM"
Option Explicit
Sub Main
    Dim f As Integer,message As String
    On Error GoTo Failed
    OpenFile "{q(source)}"
    SaveAs "{q(destination/'copy.cst')}",True
    CSTDOM_Preflight
    CSTDOM_WriteSupport
    f=FreeFile
    Open "{q(destination/'completed.txt')}" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    Exit Sub
Failed:
    message=CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
    f=FreeFile
    Open "{q(destination/'failed.txt')}" For Output As #f
    Print #f,message
    Close #f
End Sub
{render_vacuum_preflight(destination/'inventory.tsv')}
{render_material_support(sampling,destination/'support.tsv')}
'''
    path = destination/'domain.bas'
    path.write_text(macro.lstrip(), encoding='utf-8')
    try:
        with exclusive_probe(Path(__file__).resolve().parents[1]):
            options = {}
            if os.name == 'nt':
                info = subprocess.STARTUPINFO()
                info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                info.wShowWindow = 7
                options = {'startupinfo': info, 'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
            with (destination/'cst.log').open('wb') as log:
                process = subprocess.Popen([str(executable), '-m', str(path)],
                    env=cst_process_environment(), stdout=log, stderr=subprocess.STDOUT, **options)
                report['session'] = wait_probe(process, destination)
            report['exit_code'] = process.returncode
        report['source_unchanged'] = file_hash(source) == before
        marker = destination/'completed.txt'
        if (process.returncode != 0 or not marker.is_file() or marker.read_text().strip() != 'SUCCESS'
                or (destination/'failed.txt').exists() or not report['session']['exit_confirmed']):
            raise ValueError('native domain query failed; inspect macro/failed.txt/session-status.json')
        inventory, reasons = validate_inventory(destination/'inventory.tsv', sampling)
        report['inventory'], report['rejection_reasons'] = inventory, reasons
        if not report['source_unchanged'] or report['session']['foreign_processes']:
            raise ValueError('source/process identity not preserved')
        if reasons:
            report['status'] = 'rejected'
        else:
            support = load_material_support(sampling,destination/'support.tsv',
                expected_sha256=file_hash(destination/'support.tsv'), geometry_id=geometry_id)
            report.update(status='registered', support_file='support.tsv',
                support_sha256=file_hash(destination/'support.tsv'), support_id=support.identity,
                inventory_sha256=file_hash(destination/'inventory.tsv'),
                quadrature=common_quadrature([support],['Vacuum']).to_mapping())
    except Exception as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['source_unchanged'] = file_hash(source) == before
        write_json_atomic(destination/'domain-registration.json', report)
        logging.getLogger(__name__).info(
            '真空工程前提预检 | status=%s source=%s sampling=%s reasons=%s report=%s',
            report['status'], source, sampling.identity,
            report.get('rejection_reasons',report.get('failure','none')),destination/'domain-registration.json',
            extra={'event':'VACUUM_DOMAIN_PREFLIGHT','phase':'field-analysis',
                   'source_sha256':before,'sampling_id':sampling.identity,
                   'artifacts':{'registration':str(destination/'domain-registration.json')}})
    return report


def load_registered_support(registration_path, *, source_sha256, sampling, geometry_id):
    path = Path(registration_path).resolve()
    report = read_json(path)
    if (report['status'] != 'registered' or report['source_sha256'] != source_sha256
            or report['sampling_id'] != sampling.identity or report['geometry_id'] != geometry_id
            or report.get('source_unchanged') is not True):
        raise ValueError('domain registration is rejected or belongs to another source/domain')
    inventory_path = path.parent/'inventory.tsv'
    if file_hash(inventory_path) != report['inventory_sha256']:
        raise ValueError('domain inventory changed')
    _, reasons = validate_inventory(inventory_path, sampling)
    if reasons:
        raise ValueError('registered project violates vacuum preconditions')
    support_path = (path.parent/report['support_file']).resolve()
    if support_path.parent != path.parent:
        raise ValueError('support path escapes registration directory')
    support = load_material_support(sampling,support_path,
                                   expected_sha256=report['support_sha256'],geometry_id=geometry_id)
    if support.identity != report['support_id']:
        raise ValueError('support identity changed')
    common_quadrature([support],['Vacuum'])
    return support


def export_registered_vacuum_fields(executable, source, destination, settings, *, geometry_id):
    """Opt-in production entry: preflight/register first, then export or refuse.

    Separate serial native sessions avoid nesting the exclusive CST lease.
    """
    from .saved_field_export import export_saved_fields
    destination = Path(destination).resolve()
    if not settings or any(s.get('method') != 'ExportModeField' or
                          s.get('params', {}).get('field_kind') != 'E' for s in settings):
        raise ValueError('registered vacuum export requires explicit E-field steps')
    sampling = SamplingSpec.from_mapping(settings[0]['params']['sampling'])
    if any(SamplingSpec.from_mapping(s['params']['sampling']).identity != sampling.identity for s in settings):
        raise ValueError('all fields need one common point set')
    report = register_vacuum_domain(executable,source,destination/'domain',sampling,geometry_id=geometry_id)
    if report['status'] != 'registered':
        raise ValueError('vacuum project preflight rejected: ' + ','.join(report['rejection_reasons']))
    export = export_saved_fields(executable,source,destination/'fields',settings)
    if export['status'] != 'complete':
        raise ValueError('registered domain field export incomplete; inspect export-result.json')
    if export['source_sha256'] != report['source_sha256'] or not export['source_unchanged']:
        raise ValueError('source changed between registration and field export')
    descriptor = {'snapshot_id': report['source_sha256'],
                  'result_file': str(destination/'fields/export-result.json'),
                  'registration_file': str(destination/'domain/domain-registration.json')}
    write_json_atomic(destination/'tracking-input.json', descriptor)
    return {'registration': report, 'export': export, 'tracking_input': descriptor}
