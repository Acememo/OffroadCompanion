# PyInstaller runtime hook of OffroadCompanion.exe (tools/build_exe.py): under Wine / Proton only, shutil copies files
# without Windows' CopyFile2, which Wine 9 does not have (Python 3.12's shutil.copy2 calls it: the app stopped on the
# first file it copied). Nothing changes on Windows.
def _wine():
    try:
        import ctypes
        return hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")
    except Exception:
        return False


if _wine():
    try:
        import _winapi
        if hasattr(_winapi, "CopyFile2"):
            del _winapi.CopyFile2
    except Exception:
        pass
