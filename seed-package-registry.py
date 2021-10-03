#!/usr/bin/python3
import os
import sys
import copy
import yaml
import argparse
import subprocess
from components import CommonUtils, Dependencies

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to seed a Package Registry for use with run-ci-build.py')
parser.add_argument('--seed-file', type=str, required=True)
parser.add_argument('--platform', type=str, required=True)
arguments = parser.parse_args()

####
# Prepare to work
####

# Make sure if we are running under Gitlab CI that there are no variables around that will interfere in things
if 'CI_REPOSITORY_URL' in os.environ:
    del os.environ['CI_REPOSITORY_URL']

# Because we are a seed job it is assumed we are building a release branch
os.environ['CI_COMMIT_REF_PROTECTED'] = "true"

# Load the seed file
# This file will contain a list of definitions of projects we should be building
seedConfiguration = yaml.safe_load( open( arguments.seed_file ) )

# Determine where we will be working
workingDirectory = os.getcwd()

# Determine where some key resources we need for resolving dependencies will be found...
projectsMetadataPath = os.path.join( CommonUtils.scriptsBaseDirectory(), 'repo-metadata', 'projects-invent' )
branchRulesPath = os.path.join( CommonUtils.scriptsBaseDirectory(), 'repo-metadata', 'branch-rules.yml' )

# Bring our dependency resolver online...
dependencyResolver = Dependencies.Resolver( projectsMetadataPath, branchRulesPath, arguments.platform )
# And use it to determine the projects we will be building
# The seed file uses the same definition format as the project dependencies, so we can reuse that logic
# In this case the branch name is only used to resolve @same and that is unsupported in a seed file, so a dummy value of None is sufficient here
projectsToBuild = dependencyResolver.resolve( seedConfiguration, None )

####
# Fetch the projects we will be building and resolve their dependencies
####

# Setup a place to store the information
projectBuildDependencies = {}

# Go over all the projects we will be building
for identifier, branch in projectsToBuild.items():
    # Retrieve the full details from the Dependencies project database
    project = dependencyResolver.projectsByIdentifier[ identifier ]

    # Construct the URL to clone
    gitUrl = "https://invent.kde.org/{0}.git".format( project['repopath'] )

    # Clone it!
    commandToRun = "git clone {0} --branch={1} {2}/".format( gitUrl, branch, identifier )
    subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=workingDirectory )

    # This consists of:
    # 0) Global configuration
    configuration = yaml.safe_load( open(os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', 'global.yml')) )

    # 1) Project/branch specific configuration contained within the repository
    localConfigFile = os.path.join( workingDirectory, identifier, '.kde-ci.yml' )
    if os.path.exists( localConfigFile ):
        localConfig = yaml.safe_load( open(localConfigFile) )
        CommonUtils.recursiveUpdate( configuration, localConfig )

    # 2) Global overrides applied to the project configuration
    projectConfigFile = os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', identifier + '.yml')
    if os.path.exists( projectConfigFile ):
        projectConfig = yaml.safe_load( open(projectConfigFile) )
        CommonUtils.recursiveUpdate( configuration, projectConfig )

    # The Dependency Resolver requires the current working directory to be in the project it is resolving (due to @same)
    # Therefore we need to switch there first
    os.chdir( os.path.join( workingDirectory, identifier ) )
    # Resolve the dependencies for this project now
    dependencies = dependencyResolver.resolve( configuration['Dependencies'], branch )
    # And save them to our list...
    projectBuildDependencies[ identifier ] = dependencies
    # Now that we are done we can change back
    os.chdir( workingDirectory )

####
# Now we can start to build these projects
####

builtProjects = {}

while len(projectsToBuild) != 0:
    # Make a copy to work on...
    workingProjectsList = copy.deepcopy(projectsToBuild)
    # Go over all the products in our list
    for identifier, branch in workingProjectsList.items():
        # Grab the products dependencies
        projectDeps = projectBuildDependencies[ identifier ]
        # Eliminate from this any dependencies this seed file is not building
        # For those dependencies we simply assume another seed job has built them
        # This also has the nice side effect of telling us if there is anything left we are still waiting to build
        remainingDependencies = list( set(projectDeps).intersection(projectsToBuild) )

        # Do we have anything left?
        if len(remainingDependencies) > 0:
            # Not it's turn unfortunately
            continue

        # We have a winner!
        # Remove it from the list of projects to build....
        del projectsToBuild[ identifier ]

        # Then start the build process - find where the sources are...
        projectSources = os.path.join( workingDirectory, identifier )

        # We need to set CI_COMMIT_SHA in the environment to match the hash of the project we are building
        process = subprocess.Popen("git log --format=%H -1", stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, cwd=projectSources)
        os.environ['CI_COMMIT_SHA'] = process.stdout.readline().strip().decode('utf-8')

        # Prepare the command needed to build the project...
        commandToRun = "{0} -u {1}/run-ci-build.py --project {2} --branch {3} --platform {4} --only-build".format(
            sys.executable,
            CommonUtils.scriptsBaseDirectory(),
            identifier,
            branch,
            arguments.platform
        )

        # Then run it!
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=projectSources )

        # Add it to the list of projects we've built
        builtProjects[ identifier ] = branch

####
# We're done!
####

sys.exit(0)
