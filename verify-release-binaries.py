#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Dmitry Kazakov <dimula73@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import argparse
import os
import subprocess
import warnings
import sys
import fnmatch
from components import PlatformFlavor, CommonUtils

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
        args.signature = CommonUtils.boolFromEnv(os.environ["KDECI_SIGN_BINARIES"])
        print(f"INFO: signature verification is set by KDECI_SIGN_BINARIES: {args.signature}")
    else:
        args.signature = False

platform = PlatformFlavor.PlatformFlavor(args.platform)

if has_pefile and args.signature and not platform.matches(['Windows']):
    warnings.warn(f"WARNING: signature verification for a non-Windows platform is not supported")

glob_patterns = CommonUtils.globPatternsForBinaries(platform)

def find_files(directory):
    for root, dirs, files in os.walk(directory):
        if ".debug" in dirs:
            dirs.remove(".debug")
        for fname in files:
            if any(fnmatch.fnmatch(fname, p) for p in glob_patterns):
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

OBJDUMP = CommonUtils.detectObjdump()
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