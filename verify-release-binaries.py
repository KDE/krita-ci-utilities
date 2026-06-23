#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Dmitry Kazakov <dimula73@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import argparse
import os
import subprocess
import warnings
import sys
from components import PlatformFlavor

has_pefile = False

try:
    import pefile
    has_pefile = True
except:
    pass

parser = argparse.ArgumentParser(description=f'Searches for binary files with DEBUG section present.')
parser.add_argument('-d', '--directory', default=None, help='Directory to search (default: current directory)')
parser.add_argument('-f', '--file', default=None, help='Executable file to check')
parser.add_argument('-p', '--platform', default=None, help='Platform the package is built for (will use KDECI_TARGET_PLATFORM if missing)')
if has_pefile:
    parser.add_argument('-s', '--signature', action='store_true', default=None, help='Verify that all modules in the directory has signature entry (no signature validation happens)')
args = parser.parse_args()

if args.directory is None and args.file is None:
    if "INSTALL_ROOT" in os.environ:
        args.directory = os.environ["INSTALL_ROOT"]
    else:
        args.directory = os.getcwd()

if args.platform is None:
    if "KDECI_TARGET_PLATFORM" in os.environ:
        args.platform = os.environ["KDECI_TARGET_PLATFORM"]
    else:
        raise Exception("No target platform is provided")

if has_pefile and args.signature is None:
    if "KDECI_SIGN_BINARIES" in os.environ:
        args.signature = os.environ["KDECI_SIGN_BINARIES"].lower() in ['true', '1', 't', 'y', 'yes']
        print(f"INFO: signature verification is set by KDECI_SIGN_BINARIES: {args.signature}")
    else:
        args.signature = False

platform = PlatformFlavor.PlatformFlavor(args.platform)

if has_pefile and args.signature and not platform.matches(['Windows']):
    warnings.warn(f"WARNING: signature verification for a non-Windows platform is not supported")

glob_patterns = ()
if platform.matches(['Windows']):
    glob_patterns = ('*.exe', '*.com', '*.dll', '*.pyd')
elif platform.matches(['Linux']):
    glob_patterns = ('*.so', '*.so.[0-9]*', 'krita', 'kritarunner', 'ffmpeg', 'ffprobe')
elif platform.matches(['MacOS', 'Android']):
    raise Exception(f"Platform '{platform}' is currently not supported for debug splitting")
else:
    raise Exception(f"Unknown platform '{platform}'")

def find_files(directory):
    for root, _, files in os.walk(directory):
        for pattern in glob_patterns:
            for fname in files:
                if fname.lower().endswith(pattern[1:]):
                    yield os.path.join(root, fname)

def has_debug_section(objdumpOutput):
    for line in objdumpOutput.splitlines():
        if '.debug_' in line:
            return True
    return False

def has_certificate_entry(filePath):
    # NOTE: we do **not** verify the signature itself here,
    # we just check if the entry is present in the PE-structure
    pe = pefile.PE(filePath, fast_load=True)
    address = pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]
    return pe.OPTIONAL_HEADER.DATA_DIRECTORY[address].Size > 0

OBJDUMP = False
for arg in ("objdump", "llvm-objdump"):
    try:
        ret = subprocess.call([arg, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ret != 1:
            OBJDUMP = arg
    except FileNotFoundError:
        pass

if not OBJDUMP:
    warnings.warn("ERROR: objdump is not working.")
    sys.exit(1)

anyLibsWithDebugFound = False
anyUnsignedFound = False

def verify_one_file(file):
    global anyLibsWithDebugFound
    global anyUnsignedFound
    try:
        if has_pefile and args.signature:
            if not has_certificate_entry(file):
              anyUnsignedFound = True
              print(f"File is not signed: {file}")
        result = subprocess.run([OBJDUMP, '-h', file], capture_output=True, text=True, check=True)
        if has_debug_section(result.stdout):
            anyLibsWithDebugFound = True
            print(result.stdout)
    except Exception as e:
        warnings.warn(f"ERROR: Failed to parse: {file}")
        raise e

if args.directory is not None:
    for file in find_files(args.directory):
        verify_one_file(file)

if args.file is not None:
    verify_one_file(args.file)

if anyLibsWithDebugFound or anyUnsignedFound:
    sys.exit(2)