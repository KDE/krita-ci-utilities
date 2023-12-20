#!/usr/bin/python3
import os
import sys
import yaml
import tempfile
import argparse
import subprocess
from components import CommonUtils

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to run builds for multiple projects on CI')
parser.add_argument('-p','--projects', nargs='+', help='Projects to be built', required=True)
parser.add_argument('--branch', type=str, required=True)
parser.add_argument('--platform', type=str, required=True)
arguments = parser.parse_args()

projects = dict.fromkeys(arguments.projects, arguments.branch)
out = [
    {
        'on': ['@all'],
        'require': projects
    }
]
print ("Projects to be generated: {}".format(projects))
print ("Seed file generated:")
print (yaml.dump(out, indent = 2))

seedFile = tempfile.NamedTemporaryFile(delete=False, mode='w')
yaml.dump(out, seedFile, indent = 2)
seedFile.close()

commandToRun = "{0} -u {1}/seed-package-registry.py --seed-file {2} --platform {3}".format(
            sys.executable,
            CommonUtils.scriptsBaseDirectory(),
            seedFile.name,
            arguments.platform
        )

print('## Run the build for the requested projects: {}'.format(commandToRun))

workingDirectory = os.getcwd()

try:
    # Then run it!
    subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=workingDirectory )
except:
    os.remove(seedFile.name)
    raise

os.remove(seedFile.name)