import argparse
import os.path
from os import environ
import pefile
import subprocess
import sys
from components import CommonUtils

def has_certificate_entry(filePath):
    # NOTE: we do **not** verify the signature itself here,
    # we just check if the entry is present in the PE-structure
    with pefile.PE(filePath, fast_load=True) as pe:
        address = pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]
        return pe.OPTIONAL_HEADER.DATA_DIRECTORY[address].Size > 0

# command-line args parsing
parser = argparse.ArgumentParser()
parser.add_argument("pkg_root", nargs="?", default=None, help="Specify the package root (will use INSTALL_ROOT if missing)")
args = parser.parse_args()
pkg_root = args.pkg_root

if "KDECI_SIGN_BINARIES" in os.environ:
    shouldSign = CommonUtils.boolFromEnv(os.environ['KDECI_SIGN_BINARIES'])
    if not shouldSign:
        print(f"INFO: KDECI_SIGN_BINARIES is set to false, signing is skipped...")
        sys.exit(0)
else:
    print(f"INFO: KDECI_SIGN_BINARIES is missign, signing is skipped...")
    sys.exit(0)

shouldForceReSign = False
if "KDECI_FORCE_RESIGN_BINARIES" in os.environ:
    shouldForceReSign = CommonUtils.boolFromEnv(os.environ.get('KDECI_FORCE_RESIGN_BINARIES', 'False'))
    print(f"INFO: KDECI_FORCE_RESIGN_BINARIES is present, set to: {shouldForceReSign}")

if pkg_root is None:
    pkg_root = os.environ["INSTALL_ROOT"]
    print(f"INFO: Using package location from INSTALL_ROOT env: {pkg_root}")

release_package_naming = False
if 'KRITACI_RELEASE_PACKAGE_NAMING' in os.environ:
    release_package_naming = CommonUtils.boolFromEnv(os.environ['KRITACI_RELEASE_PACKAGE_NAMING'])

print(f"Signing binaries in {pkg_root}")
if not os.path.isdir(pkg_root):
    print(f"ERROR: No packaging dir {pkg_root}")
    sys.exit(1)

KRITACI_WINDOWS_SIGN_CONFIG = environ.get('KRITACI_WINDOWS_SIGN_CONFIG')
if not KRITACI_WINDOWS_SIGN_CONFIG:
    print("ERROR: %KRITACI_WINDOWS_SIGN_CONFIG% not set")
    sys.exit(1)
if not os.path.isfile(KRITACI_WINDOWS_SIGN_CONFIG):
    print(f"ERROR: No signing config file found: {KRITACI_WINDOWS_SIGN_CONFIG}")
    sys.exit(1)

hasSomethingToSign = False
with open("files-to-sign.txt", 'w') as toSign:
    for rootPath, dirs, files in os.walk(pkg_root):
        for fileName in files:
            if fileName.endswith(('.exe', '.com', '.dll', '.pyd')):
                filePath = os.path.join(rootPath, fileName)

                shouldSignThisFile = True

                if has_certificate_entry(filePath):
                    if not shouldForceReSign:
                        print(f"INFO: skip signing for {filePath} (already signed!)")
                        shouldSignThisFile = False
                    else:
                        print(f"INFO: force resigning {filePath} (even though already signed!)")

                if shouldSignThisFile:
                    print(filePath, file=toSign)
                    hasSomethingToSign = True

if hasSomethingToSign:
    signWindowsBinariesScript = os.path.join(os.path.dirname(__file__), "..", "ci-notary-service", "signwindowsbinaries.py")
    if not os.path.exists(signWindowsBinariesScript):
        signWindowsBinariesScript = os.path.join(os.path.dirname(__file__), "..", "..", "ci-notary-service", "signwindowsbinaries.py")

    commandToRun = [sys.executable,
                    "-u",
                    signWindowsBinariesScript,
                    "--config", KRITACI_WINDOWS_SIGN_CONFIG,
                    "--files-from", "files-to-sign.txt"
                    ]
    subprocess.check_call(commandToRun)
else:
    print(f"INFO: nothing to sign, skip requesting notary service...")

if release_package_naming:
    print(f"Verify that all executables have a signature in {pkg_root}")
    # The `-s` argument will be passed via `KDECI_SIGN_BINARIES` environment
    # variable, which is guaranteed to be set at this point
    commandToRun = [sys.executable,
                    "-u",
                    os.path.join(os.path.dirname(__file__), "verify-release-binaries.py"),
                    "-d", pkg_root
                    ]
    subprocess.check_call(commandToRun)



