# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

block_cipher = None

# Function to collect Tcl/Tk data files
def collect_tcl_tk_files():
    """Collect Tcl/Tk files needed for tkinter to work in PyInstaller bundle"""
    tcl_tk_files = []
    
    # Method 1: Try to find Tcl/Tk in Python installation directory (most reliable on Windows)
    try:
        python_dir = Path(sys.executable).parent
        tcl_dir = python_dir / 'tcl'
        
        if tcl_dir.exists():
            for item in tcl_dir.iterdir():
                if item.is_dir():
                    if item.name.startswith('tcl8.'):
                        # Bundle to _tcl_data folder that PyInstaller expects
                        tcl_tk_files.append((str(item), '_tcl_data/' + item.name))
                    elif item.name.startswith('tk8.'):
                        # Bundle to _tcl_data folder that PyInstaller expects
                        tcl_tk_files.append((str(item), '_tcl_data/' + item.name))
    except Exception as e:
        print(f"Warning: Could not find Tcl/Tk in Python directory: {e}")
    
    # Method 2: Try to get paths from tkinter (if available)
    if not tcl_tk_files:
        try:
            import tkinter
            # Get the Tcl/Tk library directory
            root = tkinter.Tk()
            tcl_dir = root.tk.exprstring('$tcl_library')
            tk_dir = root.tk.exprstring('$tk_library')
            root.destroy()
            
            # Convert to Path objects
            tcl_path = Path(tcl_dir)
            tk_path = Path(tk_dir)
            
            # Add Tcl library files to _tcl_data
            if tcl_path.exists():
                tcl_tk_files.append((str(tcl_path), '_tcl_data/tcl'))
            
            # Add Tk library files to _tcl_data
            if tk_path.exists():
                tcl_tk_files.append((str(tk_path), '_tcl_data/tk'))
        except Exception as e:
            print(f"Warning: Could not get Tcl/Tk paths from tkinter: {e}")
    
    return tcl_tk_files

# Collect Tcl/Tk files
tcl_tk_data = collect_tcl_tk_files()
print(f"Collected Tcl/Tk files: {tcl_tk_data}")

a = Analysis(
    ['fantome_repath_gui.py'],
    pathex=['.'],  # Add current directory to path
    binaries=[],
    datas=[
        # Bundle placeholder texture files
        ('invis.dds', '.'),
        ('invis.tex', '.'),
        # Bundle icon for window
        ('Untitled.ico', '.'),
        # Bundle example image for skin ID reference
        ('example.png', '.'),
        # IMPORTANT: Bundle local pyRitoFile (League Mod Repather/pyRitoFile)
        # This ensures the modified pyRitoFile with DuplicatePreservingMap is used
        ('pyRitoFile', 'pyRitoFile'),  # Bundle entire pyRitoFile directory
    ] + tcl_tk_data,  # Add Tcl/Tk files
    hiddenimports=[
        'ttkbootstrap',
        'requests',  # Needed for downloading hashes
        'pyRitoFile',  # Explicitly include pyRitoFile
        'pyRitoFile.bin',  # Include bin module with DuplicatePreservingMap
        'pyRitoFile.wad',
        'pyRitoFile.tex',
        'pyRitoFile.stream',
        'pyRitoFile.helper',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_tkinter_fix.py'],  # Fix Tcl/Tk paths at runtime
    excludes=[
        # Exclude project root pyRitoFile to ensure we use local one
        # (PyInstaller might auto-detect the project root one if it's in sys.path)
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LeagueModRepather',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # No console window needed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Untitled.ico',  # Application icon
)

