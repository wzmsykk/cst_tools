# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['base_win.py'],
             pathex=['C:\\Users\\ykk\\Desktop\\cst_tools'],
             binaries=[],
             datas=[('./data','./data')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['./util'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='base_win',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='base_win')
