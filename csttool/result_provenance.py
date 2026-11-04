"""Freeze the actual single-mode operator context before dispatch."""
import hashlib
from pathlib import Path
import shutil
from .configuration import write_json_atomic
from .saved_project_source import read_saved_source
from .settings_projection import project_saved_settings


def freeze_postprocess_provenance(definition_path, axis, worker, directory, postprocess,*,geometry_spec=None,geometry_proof=None):
    directory=Path(directory)
    source=read_saved_source(definition_path,scope='root')
    if geometry_spec is not None:
        from .managed_history import verify_saved_program
        verify_saved_program(source,geometry_spec)
        if (not isinstance(geometry_proof,dict) or geometry_proof.get('status')!='verified'
                or geometry_proof.get('source_sha256')!=source.sha256 or len(geometry_proof.get('observations',[]))!=2):
            raise ValueError('GEO integration domain requires saved/reopened native proof')
        box=geometry_proof['observations'][-1]['geometry']['calculation_bounds_mm']
        bounds=[box[axis+'min'],box[axis+'max']]
        import math
        if not all(math.isfinite(v) for v in bounds) or bounds[0]>=bounds[1]:raise ValueError('invalid GEO integration extent')
    else:
        projection=project_saved_settings(source)
        bounds=projection.fields['geometry.cylinder.'+axis+'range']
    endpoints=[]
    for value in bounds:
        point=[0.,0.,0.];point['xyz'.index(axis)]=value;endpoints.append(point)
    algorithm=Path(__file__).resolve().parents[1]/'data/postprocess/EigenResult_Complex.vb'
    raw=algorithm.read_bytes()
    saved=directory/'rq-algorithm.vb';saved.write_bytes(raw)
    macro=getattr(worker,'macro_path',None)
    macro_ref=None
    if macro is not None:
        macro=Path(macro)
        target=directory/'execution-worker.bas';shutil.copyfile(macro,target)
        macro_ref=dict(path=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    record=dict(schema_version=1,mode_index=1,source_sha256=source.sha256,requested_postprocess=postprocess,
        frequency=dict(method='Frequency',native_call='GetModeFrequencyInHz',unit='MHz',scale_from_hz=1e-6),
        r_over_q=dict(method='R_over_Q',implementation='EigenResult_Complex',unit='ohm',
            integration_line=dict(axis=axis,offset_mm=[0.,0.,0.],endpoints_mm=endpoints,beta=1.,range='full'),
            voltage='complex line integral with transit phase',energy='QFactor.GetTotalEnergy',
            formula='abs(V)^2/(omega*W)',algorithm=dict(path=saved.name,sha256=hashlib.sha256(raw).hexdigest())),
        generated_macro=macro_ref,generated_macro_evidence='archived' if macro_ref else 'unavailable')
    write_json_atomic(directory/'postprocess-provenance.json',record)
    return hashlib.sha256((directory/'postprocess-provenance.json').read_bytes()).hexdigest()


def read_postprocess_provenance(directory,expected_sha256):
    from .application_service import ServiceError
    from .configuration import read_json
    directory=Path(directory);path=directory/'postprocess-provenance.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha256:
        raise ServiceError('RESULT_INVALID','frozen postprocess context changed')
    record=read_json(path)
    for ref in (record['r_over_q']['algorithm'],record.get('generated_macro')):
        if ref is None:continue
        artifact=(directory/ref['path']).resolve()
        if not artifact.is_relative_to(directory.resolve()) or hashlib.sha256(artifact.read_bytes()).hexdigest()!=ref['sha256']:
            raise ServiceError('RESULT_INVALID','postprocess algorithm artifact changed')
    return record
