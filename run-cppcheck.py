#!/usr/bin/python3
import os
import sys
import yaml
import tarfile
import tempfile
import argparse
import subprocess
import multiprocessing
from components import CommonUtils, Dependencies, Package, EnvironmentHandler, TestHandler

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to perform a CI run for a KDE project.')
parser.add_argument('--project', type=str, required=True)
parser.add_argument('--branch', type=str, required=True)
arguments = parser.parse_args()

####
# Load the project configuration
####

# This consists of:
# 0) Global configuration
configuration = yaml.safe_load( open(os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', 'global.yml')) )

# 1) Project/branch specific configuration contained within the repository
if os.path.exists('.kde-ci.yml'):
    localConfig = yaml.safe_load( open('.kde-ci.yml') )
    CommonUtils.recursiveUpdate( configuration, localConfig )

# 2) Global overrides applied to the project configuration
projectConfigFile = os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', arguments.project + '.yml')
if os.path.exists( projectConfigFile ):
    projectConfig = yaml.safe_load( open(projectConfigFile) )
    CommonUtils.recursiveUpdate( configuration, projectConfig )

####
# Determine a number of paths we will need later on
####

# Our sources are assumed to be in the current working directory
sourcesPath = os.getcwd()

# Determine where to locate the project build
buildPath = os.path.join( os.getcwd(), '_build' )
if configuration['Options']['in-source-build']:
    buildPath = os.getcwd()

# Determine where to unpack the dependencies to
installPath = os.path.join( os.getcwd(), '_install' )

####
# Perform final steps needed to get ready to start the build process
####

# Determine what our build environment should be comprised of....
buildEnvironment = EnvironmentHandler.generateFor( installPrefix=installPath )

# Apply any environment changes from our configuration
for key, value in configuration['Environment'].items():
    # Apply each key in turn
    buildEnvironment[ key ] = value

####
# Extract cppcheck results for processing by Gitlab
####

# If we aren't running on Linux then we skip this, as we consider that to be the canonical platform for code coverage...
if configuration['Options']['run-cppcheck']:
    # Determine the cppcheck command we need to run
    # Sometimes projects will want to customise things slightly so we provide for that as well
    ignores = ' '.join(['-i ' + s for s in configuration['Options']['cppcheck-ignore-files']])
    localDefinitions = os.path.join(CommonUtils.scriptsBaseDirectory(), 'resources', 'cppcheck-kde-definitions.cfg')
    commandToRun = 'cppcheck --xml --relative-paths --library=qt --library={localDefinitions} -i _build/ {otherArguments} {ignoreArgs} "{sources}" 2> cppcheck_out.xml'
    commandToRun = commandToRun.format( sources=sourcesPath, otherArguments=configuration['Options']['cppcheck-arguments'], ignoreArgs=ignores, localDefinitions=localDefinitions )

    # Determine the command to run to convert the cppcheck XML report into a CodeClimate format file
    conversionCommand = 'cppcheck-codequality --input-file=cppcheck_out.xml --output-file=cppcheck.json'

    # Now run it!
    # If cppcheck bails we ignore it, as failures to extract cppcheck results shouldn't cause builds to fail.
    try:
        print("## RUNNING: " + commandToRun)
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=buildEnvironment )
    except Exception:
        print("## Failed to run cppcheck over the project")
        sys.exit(1)

    try:
        print("## RUNNING: " + conversionCommand )
        subprocess.check_call( conversionCommand, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=buildEnvironment )
    except Exception:
        print("## Failed to run convert cppcheck data")
        sys.exit(2)

####
# Run complete!
####

print("## Cppcheck run successfully!")
sys.exit(0)
