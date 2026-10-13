"""Independent ideal closed-PEC TM110 doublet; not a generic cavity classifier."""
import numpy as np


def tm110_reference(points_m, radius_m, z_bounds_m):
    from scipy.special import j1, jn_zeros
    points = np.asarray(points_m, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('invalid physical points')
    if not np.isfinite(radius_m) or radius_m <= 0 or len(z_bounds_m) != 2 or not np.isfinite(z_bounds_m).all() or z_bounds_m[0] >= z_bounds_m[1]:
        raise ValueError('invalid ideal cylinder geometry')
    chi = float(jn_zeros(1,1)[0])
    radial = np.linalg.norm(points[:,:2],axis=1)
    angular = np.divide(points[:,:2],radial[:,None],out=np.zeros_like(points[:,:2]),where=radial[:,None]>0)
    fields = np.zeros((len(points),3,2),dtype=complex)
    inside = (radial < radius_m) & (points[:,2]>z_bounds_m[0]) & (points[:,2]<z_bounds_m[1])
    fields[inside,2,:] = j1(chi*radial[inside,None]/radius_m)*angular[inside]
    return {'fields':fields,'frequency_hz':299792458*chi/(2*np.pi*radius_m),
            'family':'ideal-TM110','basis':'Ez=J1(chi11*r/R)*(cos(phi),sin(phi)); Ex=Ey=0',
            'geometry':'closed-cylinder-PEC-vacuum','normalization':'arbitrary common amplitude'}
