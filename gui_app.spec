# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)


a = Analysis([str(project_root / 'gui_app.py')],
             pathex=[str(project_root)],
             binaries=[],
             datas=[
                 (str(project_root / 'data'), 'data'),
                 (str(project_root / 'config' / 'default.ini'), 'config'),
             ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[
                 'pytest',
                 'sphinx',
                 'IPython',
                 'notebook',
                 'jupyter',
                 'dask',
                 'distributed',
                 'xarray',
                 'pyarrow',
                 'numba',
                 'openpyxl',
                 'botocore',
                 'tables',
                 'sqlalchemy',
                 'black',
                 'panel',
                 'bokeh',
                 'fsspec',
                 'zmq',
                 'cryptography',
                 'bcrypt',
                 'nacl',
                 'tkinter',
                 'cloudpickle',
                 'lz4',
                 'lxml',
                 'chardet',
                 'xyzservices',
             ],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='gui_app',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False )
