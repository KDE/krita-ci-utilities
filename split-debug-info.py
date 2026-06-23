#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Dmitry Kazakov <dimula73@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import subprocess
import logging
import sys
import os
import shutil
import argparse
import fnmatch
from components import PlatformFlavor

def detect_objdump():
    for arg in ("objdump", "llvm-objdump"):
        commandToRun = f"{arg} --version"
        ret = subprocess.call(commandToRun, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        if ret != 1:
            return arg
    return None

def has_debug_section(objdumpOutput):
    for line in objdumpOutput.splitlines():
        if '.debug_' in line:
            return True
    return False

def split_debug(rootDir, relativeFileName, logger, objdumpBinary):
    logger.debug(f"Start debug split for file: {relativeFileName}")
    fileName = os.path.join(rootDir, relativeFileName) if rootDir else relativeFileName

    # The objcopy implementation included in llvm-21 and later has some weird
    # implementation of --only-keep-debug, it manages to strip binaries, even
    # when they have no .debug sections, which makes these binaries invalid for
    # signtool. The problem might also be related to the fact that these
    # binaries are built with MSVC (python3.dll, dbgcore.dll, d3dcompiler_47.dll
    # and the like).
    #
    # That is why we manually check if the libraries have any `.debug` sections
    # included and strip them only in case such sections are found
    result = subprocess.run([objdumpBinary, "-h", fileName], capture_output=True, text=True, check=True)
    if not has_debug_section(result.stdout):
        logger.info(f"Skip stripping {relativeFileName}: has no debug sections")
        return

    commandToRun = ["objcopy", "--only-keep-debug", fileName, f"{fileName}.debug"]
    logger.debug(f"Running {' '.join(commandToRun)}")
    subprocess.check_call(commandToRun)

    # If the debug file is small enough then consider there being no debug info.
    # Discard these files since they somehow make gdb crash.
    if os.path.getsize(f"{fileName}.debug") <= 2048:
        logger.info(f"Discarding {relativeFileName}.debug")
        os.remove(f"{fileName}.debug")
        return

    debugDir = os.path.join(os.path.dirname(fileName), ".debug")
    if not os.path.isdir(debugDir):
        os.mkdir(debugDir)

    shutil.move(f"{fileName}.debug", debugDir + os.path.sep)

    commandToRun = ["strip", "--strip-debug", fileName]
    logger.debug(f"Running {' '.join(commandToRun)}")
    subprocess.check_call(commandToRun)

    # Add debuglink
    # FIXME: There is a problem with gdb that cause it to output this warning
    # FIXME: "warning: section .gnu_debuglink not found in xxx.debug"
    # FIXME: I tried adding a link to itself but this kills drmingw :(
    commandToRun = ["objcopy",
                    f"--add-gnu-debuglink={os.path.join('.debug', os.path.basename(fileName))}.debug",
                    fileName]
    logger.debug(f"Running {' '.join(commandToRun)}")
    subprocess.check_call(commandToRun)

def split_debug_in_folder(rootDir, platform, logger, objdumpBinary):
    patterns = ()
    if platform.matches(['Windows']):
        patterns = ('*.exe', '*.com', '*.dll', '*.pyd')
    elif platform.matches(['Linux']):
        patterns = ('*.so', '*.so.[0-9]*', 'krita', 'kritarunner', 'ffmpeg', 'ffprobe')
    elif platform.matches(['MacOS', 'Android']):
        raise Exception(f"Platform '{platform}' is currently not supported for debug splitting")
    else:
        raise Exception(f"Unknown platform '{platform}'")

    for currentRoot, dirs, files in os.walk(rootDir):
        if ".debug" in dirs:
            dirs.remove(".debug")
        for fileName in files:
            filePath = os.path.join(currentRoot, fileName)
            if os.path.isfile(filePath) and \
                not os.path.islink(filePath) and \
                    any(fnmatch.fnmatch(fileName, p) for p in patterns):

                relFilePath = os.path.relpath(filePath, rootDir)
                split_debug(rootDir, relFilePath, logger=logger, objdumpBinary=objdumpBinary)

if __name__ == "__main__":

    useVerbosePackagingLog = (os.environ.get('KRITACI_VERBOSE_PACKAGING', '0').lower() in ['true', '1', 't', 'y', 'yes'])

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    fileFormatter = logging.Formatter("## %(asctime)s %(levelname)s: %(message)s")

    fileHandler = logging.FileHandler(f"{os.path.basename(__file__)}.log", mode='w')
    fileHandler.setLevel(logging.DEBUG)
    fileHandler.setFormatter(fileFormatter)

    stdoutFormatter = logging.Formatter("## %(levelname)s: %(message)s")

    stdoutHandler = logging.StreamHandler(sys.stdout)
    stdoutHandler.setLevel(logging.DEBUG if useVerbosePackagingLog else logging.INFO)
    stdoutHandler.setFormatter(stdoutFormatter)

    logger.addHandler(fileHandler)
    logger.addHandler(stdoutHandler)


    OBJDUMP = detect_objdump()

    if not OBJDUMP:
        logger.error("objdump is not working.")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("pkg_root", nargs="?", default=None, help="Specify the package root (will use INSTALL_ROOT if missing)")
    parser.add_argument('-p', '--platform', default=None, help='Platform the package is built for')
    args = parser.parse_args()
    pkg_root = args.pkg_root

    if pkg_root is None:
        pkg_root = os.environ["INSTALL_ROOT"]
        logger.info(f"Using package location from INSTALL_ROOT env: {pkg_root}")

    if args.platform is None:
        if "KDECI_TARGET_PLATFORM" in os.environ:
            args.platform = os.environ["KDECI_TARGET_PLATFORM"]
        else:
            raise Exception("No target platform is provided")

    platform = PlatformFlavor.PlatformFlavor(args.platform)

    split_debug_in_folder(pkg_root, platform, logger, OBJDUMP)
