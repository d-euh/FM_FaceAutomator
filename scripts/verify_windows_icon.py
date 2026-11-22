"""Fail the Windows build if its PE resources do not contain the supplied ICO."""
from pathlib import Path
import struct
import sys


def ico_frames(path):
    data = Path(path).read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if reserved != 0 or kind != 1 or not count:
        raise ValueError("Invalid ICO header")
    frames = []
    for index in range(count):
        entry = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        size, offset = entry[-2:]
        payload = data[offset:offset + size]
        if len(payload) != size or not size:
            raise ValueError("Truncated ICO frame")
        frames.append((entry[:6], payload))
    return frames


def verify_resources(pe, expected):
    resources = {}
    for resource_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        for item in resource_type.directory.entries:
            for language in item.directory.entries:
                location = language.data.struct
                resources[(resource_type.id, item.id, language.id)] = pe.get_data(
                    location.OffsetToData, location.Size,
                )
    for (kind, _, language), group in resources.items():
        if kind != 14:  # RT_GROUP_ICON
            continue
        reserved, image_type, count = struct.unpack_from("<HHH", group)
        if reserved != 0 or image_type != 1 or count != len(expected):
            continue
        actual = []
        for index in range(count):
            entry = struct.unpack_from("<BBBBHHIH", group, 6 + 14 * index)
            payload = resources.get((3, entry[-1], language))  # RT_ICON
            if payload is None or len(payload) != entry[-2]:
                break
            actual.append((entry[:6], payload))
        if actual == expected:
            return
    raise ValueError("The EXE does not contain the expected FFA icon resources")


def main():
    import pefile  # Installed by PyInstaller on Windows.

    executable, icon = map(Path, sys.argv[1:])
    with pefile.PE(str(executable)) as pe:
        verify_resources(pe, ico_frames(icon))
    print(f"Verified FFA icon in: {executable}")
    # Notify Explorer about this specific rebuilt file, without clearing its
    # global cache or restarting the user's desktop.
    if sys.platform == "win32":
        import ctypes
        notify = ctypes.windll.shell32.SHChangeNotify
        notify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        notify.restype = None
        notify(0x2000, 0x0005, ctypes.cast(ctypes.c_wchar_p(str(executable.resolve())), ctypes.c_void_p), None)


if __name__ == "__main__":
    main()
