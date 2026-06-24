import argparse
import os.path
from os import environ
import subprocess
import sys
from components import CommonUtils

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

with open("files-to-sign.txt", 'w') as toSign:
    for rootPath, dirs, files in os.walk(pkg_root):
        for fileName in files:
            if fileName.endswith(('.exe', '.com', '.dll', '.pyd')):
                filePath = os.path.join(rootPath, fileName)
                print(filePath, file=toSign)

commandToRun = [sys.executable,
                "-u",
                os.path.join(os.path.dirname(__file__), "..", "ci-notary-service", "signwindowsbinaries.py"),
                "--config", KRITACI_WINDOWS_SIGN_CONFIG,
                "--files-from", "files-to-sign.txt"
                ]
subprocess.check_call(commandToRun)

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



