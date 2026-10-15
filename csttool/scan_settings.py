"""Pure HOM configuration defaults, independent of execution and Qt."""


def default_hom_settings():
    return dict(fmin=700, fmax=800, endfreq=2500, mesh_cells_per_wavelength=20,
                mesh_convergence_enabled=False, mesh_convergence_start=10,
                mesh_convergence_stop=30, mesh_convergence_step=5,
                mesh_convergence_tolerance=0.01)


def validate_hom_settings(values):
    from .mesh_convergence import MeshConvergenceSettings
    settings = {**default_hom_settings(), **values}
    if int(settings['mesh_cells_per_wavelength']) < 1:
        raise ValueError('mesh_cells_per_wavelength must be positive')
    MeshConvergenceSettings(bool(settings['mesh_convergence_enabled']),
        int(settings['mesh_convergence_start']), int(settings['mesh_convergence_stop']),
        int(settings['mesh_convergence_step']), float(settings['mesh_convergence_tolerance']))
    return settings
