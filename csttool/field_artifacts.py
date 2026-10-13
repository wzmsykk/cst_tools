"""Validated optional HDF5 field artifacts; physical support is explicit."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from .result_reconciliation import file_hash


@dataclass(frozen=True)
class SamplingSpec:
    bounds_m: tuple[float, ...]
    counts: tuple[int, int, int]
    scope: str = "roi-probe"

    def __post_init__(self):
        if len(self.bounds_m)!=6 or not np.isfinite(self.bounds_m).all() or any(
            self.bounds_m[2*i]>=self.bounds_m[2*i+1] for i in range(3)
        ):
            raise ValueError("invalid SI bounds")
        if len(self.counts)!=3 or any(isinstance(n,bool) or not isinstance(n,int) or n<1 for n in self.counts) or np.prod(self.counts)>2_000_000:
            raise ValueError("invalid sampling counts")
        if self.scope not in ("roi-probe","specified-domain"):
            raise ValueError("invalid sampling scope")

    def points(self):
        axes=[lo+(np.arange(n)+0.5)*(hi-lo)/n for lo,hi,n in
              zip(self.bounds_m[::2],self.bounds_m[1::2],self.counts)]
        return np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1).reshape(-1,3)

    def weights(self):
        volume=np.prod(np.array(self.bounds_m[1::2])-np.array(self.bounds_m[::2]))
        return np.full(int(np.prod(self.counts)),volume/np.prod(self.counts))

    @property
    def identity(self):
        return sha256(json.dumps({'bounds_m':self.bounds_m,'counts':self.counts,
            'scope':self.scope,'rule':'uniform-cell-centers-v1','coordinates':'cartesian-SI'},sort_keys=True).encode()).hexdigest()

    def to_mapping(self):
        return {'bounds_m':list(self.bounds_m),'counts':list(self.counts),'scope':self.scope}

    @classmethod
    def from_mapping(cls, value):
        return cls(tuple(value['bounds_m']),tuple(value['counts']),value.get('scope','roi-probe'))


@dataclass(frozen=True)
class FieldArtifact:
    path: Path
    sampling: SamplingSpec
    mode: int
    frequency_hz: float
    field_kind: str
    file_sha256: str
    support_verified: bool
    coordinates_unit: str = "m"
    raw_coordinate_scale_to_m: float = 1.0
    raw_coordinate_unit: str = "m"

    def __post_init__(self):
        if isinstance(self.mode,bool) or not isinstance(self.mode,int) or self.mode<1:
            raise ValueError('invalid mode')
        if not np.isfinite(self.frequency_hz) or self.frequency_hz<=0 or self.field_kind not in ('E','H') or self.coordinates_unit!='m':
            raise ValueError('invalid field identity/units')
        if not self.file_sha256 or not isinstance(self.support_verified,bool):
            raise ValueError('missing field provenance')
        if not np.isfinite(self.raw_coordinate_scale_to_m) or self.raw_coordinate_scale_to_m<=0 or not self.raw_coordinate_unit:
            raise ValueError('invalid raw coordinate units')


def read_field(artifact):
    import h5py  # Optional feature; ordinary worker imports do not require h5py.
    path=Path(artifact.path)
    if file_hash(path)!=artifact.file_sha256:
        raise ValueError('field artifact hash changed')
    with h5py.File(path,'r') as stream:
        count=int(np.prod(artifact.sampling.counts))
        if stream[f'{artifact.field_kind}-Field'].shape!=(count,) or stream['Position'].shape!=(count,):
            raise ValueError('HDF5 point inventory differs')
        raw=stream[f'{artifact.field_kind}-Field'][...]
        positions=stream['Position'][...]
    try:
        xyz=np.column_stack([positions[s] for s in ('x','y','z')])*artifact.raw_coordinate_scale_to_m
        values=np.column_stack([raw[s]['re'].astype(float)+1j*raw[s]['im'].astype(float)
                               for s in ('x','y','z')])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError('missing complex components') from exc
    expected=artifact.sampling.points()
    if xyz.shape!=expected.shape or values.shape!=expected.shape or not np.isfinite(xyz).all() or not np.isfinite(values).all():
        raise ValueError('invalid field inventory or values')
    if not np.allclose(xyz,expected,rtol=1e-12,atol=1e-14):
        raise ValueError('coordinates do not match SI sampling specification')
    if not np.any(values):
        raise ValueError('zero field: no supported diagnostic norm')
    if not artifact.support_verified:
        raise ValueError('field support not verified')
    return values


def read_export_status(path, sampling, mode, field_kind):
    """Optional readout: never turn a successful solve into a failed task."""
    path=Path(path)
    try:
        lines=path.read_text(encoding='utf-8-sig').splitlines()
        if len(lines)!=5 or lines[0]!='SUCCESS' or int(lines[2])!=0:
            raise ValueError('export/point validity not confirmed: ' + ' '.join(lines)[:500])
        hdf=path.with_suffix('.h5')
        artifact=FieldArtifact(hdf,sampling,mode,float(lines[1]),field_kind,file_hash(hdf),True,
                               raw_coordinate_scale_to_m=float(lines[3]),raw_coordinate_unit=lines[4])
        read_field(artifact)
        return {'kind':'field-artifact','status':'available','filename':hdf.name,
                'sha256':artifact.file_sha256,'mode':mode,'frequency_hz':artifact.frequency_hz,
                'field_kind':field_kind,'coordinates_unit':'m','sampling':sampling.to_mapping(),
                'field_unit':'V/m' if field_kind=='E' else 'A/m',
                'sampling_id':sampling.identity,'support_verified':True,
                'support_check':'calculation-box-and-retrieval; material mask not independently verified',
                'raw_coordinate_scale_to_m':artifact.raw_coordinate_scale_to_m,
                'raw_coordinate_unit':artifact.raw_coordinate_unit}
    except Exception as exc:
        return {'kind':'field-artifact','status':'unavailable','reason':f'{type(exc).__name__}: {exc}',
                'status_filename':path.name}


def artifacts_from_result(result_directory, postprocess, *, expected_context=None):
    directory=Path(result_directory).resolve()
    artifacts=[]
    for item in postprocess or []:
        value=item.get('value')
        if not isinstance(value,dict) or value.get('kind')!='field-artifact':
            continue
        if value.get('status')!='available':
            raise ValueError('field export unavailable')
        if expected_context and any(value.get('context',{}).get(key)!=v for key,v in expected_context.items()):
            raise ValueError('field task/session identity mismatch')
        path=(directory/value['filename']).resolve()
        if path.parent!=directory:
            raise ValueError('field path escapes result directory')
        artifacts.append(FieldArtifact(path,SamplingSpec.from_mapping(value['sampling']),
            value['mode'],value['frequency_hz'],value['field_kind'],value['sha256'],
            value['support_verified'],value['coordinates_unit'],value['raw_coordinate_scale_to_m'],
            value['raw_coordinate_unit']))
    if not artifacts:
        raise ValueError('no field artifacts')
    return artifacts
