#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Minimal libretro frontend probe, executed by target Python under QEMU."""
import ctypes
import json
import os
import sys


class SystemInfo(ctypes.Structure):
    _fields_ = [('library_name', ctypes.c_char_p), ('library_version', ctypes.c_char_p),
                ('valid_extensions', ctypes.c_char_p), ('need_fullpath', ctypes.c_bool),
                ('block_extract', ctypes.c_bool)]


directory = os.fsencode(os.environ['HOME'])
events = []
Environment = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)


@Environment
def environment(command, data):
    events.append(command)
    if command in (9, 30, 31):  # system, core assets, save directories
        ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = directory
        return True
    if command == 3:  # frontend supports duplicate frames
        ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
        return True
    if command == 17:  # core variables have not changed
        ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
        return True
    if command in (10, 11, 16, 18, 32):  # pixel/input/options/descriptors
        return True
    return False


core = ctypes.CDLL(sys.argv[1], mode=ctypes.RTLD_LOCAL)
core.retro_api_version.restype = ctypes.c_uint
core.retro_get_system_info.argtypes = [ctypes.POINTER(SystemInfo)]
core.retro_get_system_info.restype = None
core.retro_set_environment.argtypes = [Environment]
core.retro_set_environment.restype = None
core.retro_init.restype = None
core.retro_deinit.restype = None
info = SystemInfo()
core.retro_get_system_info(ctypes.byref(info))
core.retro_set_environment(environment)
core.retro_init()
core.retro_deinit()
print('LIBRETRO_PROBE=' + json.dumps({
    'core': os.path.basename(sys.argv[1]), 'api': core.retro_api_version(),
    'name': info.library_name.decode(), 'version': info.library_version.decode(),
    'extensions': info.valid_extensions.decode(),
    'init_deinit': 'PASS', 'environment_commands': sorted(set(events))
}))
