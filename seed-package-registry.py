#!/usr/bin/python3
import os
import sys
import copy
import yaml
import argparse
import shutil
import subprocess
from components import CommonUtils, Dependencies, PlatformFlavor, Package, MergeFolders
from components.CiConfigurationUtils import *


# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to seed a Package Registry for use with run-ci-build.py')
parser.add_argument('--seed-file', type=str, required=True)
parser.add_argument('--platform', type=str, required=True)
parser.add_argument('--extra-cmake-args', type=str, nargs='+', action='append', required=False)
parser.add_argument('--skip-dependencies-fetch', default=False, action='store_true')
parser.add_argument('--publish-to-cache', default=False, action='store_true')
parser.add_argument('--missing-only', default=False, action='store_true')
arguments = parser.parse_args()
platform = PlatformFlavor.PlatformFlavor(arguments.platform)

if arguments.missing_only and not arguments.publish_to_cache:
    print ("WARNING: argument --missing-only has no effect without --publish-to-cache")

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

# Bring our dependency resolver online...
dependencyResolver = prepareDependenciesResolver(platform)

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
    projectFolder = os.path.join(workingDirectory, identifier)

    if project['hasrepo']:
        # Construct the URL to clone
        gitUrl = "https://invent.kde.org/{0}.git".format( project['repopath'] )

        # Clone it!
        commandToRun = "git clone {0} --branch={1} {2}/".format( gitUrl, branch, identifier )
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=workingDirectory )
    elif 'reuse-directory' in project:
        if os.path.isdir(projectFolder):
            for item in os.listdir(projectFolder):
                print (f'Trying to remove {item}')
                if not item in ['.kde-ci-override.yml', '.gitignore']:
                    print (f'    removing... {item}')
                    itemPath = os.path.join(projectFolder, item)
                    if os.path.isdir(itemPath):
                        shutil.rmtree()
                    else:
                        os.remove(itemPath)
                    pass

        MergeFolders.merge_folders(os.path.join(workingDirectory, project['reuse-directory']), projectFolder)

        projectConfigFile = os.path.join(projectFolder, '.kde-ci.yml')
        overrideFile = os.path.join(projectFolder, '.kde-ci-override.yml')
        if os.path.isfile(overrideFile):
            if not os.path.isfile(projectConfigFile):
                shutil.copy2(overrideFile, projectConfigFile)
            else:
                with open(projectConfigFile, 'r') as f:
                    localConfig = yaml.safe_load(f)
                with open(overrideFile, 'r') as f:
                    overrideConfig = yaml.safe_load(f)

                CommonUtils.recursiveUpdate( localConfig, overrideConfig )

                with open(projectConfigFile, 'w') as f:
                    yaml.dump(localConfig, f, indent = 2)

    configuration = loadProjectConfiguration(projectFolder, identifier)

    # The Dependency Resolver requires the current working directory to be in the project it is resolving (due to @same)
    # Therefore we need to switch there first
    os.chdir( projectFolder )
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

        localCachePath = os.environ.get('KDECI_CACHE_PATH', None)
        if not localCachePath is None and arguments.publish_to_cache and arguments.missing_only:
            if os.path.exists(os.path.join(localCachePath, '{}-{}.json'.format(identifier, branch))):
                print('## Skipping build of {} since a package exists in the cache'.format(identifier))
                continue

        # Then start the build process - find where the sources are...
        projectSources = os.path.join( workingDirectory, identifier )

        # We need to set CI_COMMIT_SHA in the environment to match the hash of the project we are building
        process = subprocess.Popen("git log --format=%H -1", stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, cwd=projectSources)
        os.environ['CI_COMMIT_SHA'] = process.stdout.readline().strip().decode('utf-8')

        # Prepare the command needed to build the project...
        commandToRun = "{0} -u {1}/run-ci-build.py --project {2} --branch {3} --platform {4} --only-build --fail-on-leaked-stage-files".format(
            sys.executable,
            CommonUtils.scriptsBaseDirectory(),
            identifier,
            branch,
            platform
        )

        if arguments.skip_dependencies_fetch:
            # just forward skip-dependencies-fetch argument to the lower-level tool
            commandToRun += ' --skip-dependencies-fetch'

        if arguments.publish_to_cache:
            # just forward publish-to-cache argument to the lower-level tool
            commandToRun += ' --publish-to-cache'

        if arguments.extra_cmake_args:
            # necessary since we cannot use the 'extend' action for the arguments due to requiring Python < 3.8
            flat_args = [item for sublist in arguments.extra_cmake_args for item in sublist]
            commandToRun += ' ' + ' '.join(['--extra-cmake-args=' + arg for arg in flat_args])

        if 'KDECI_SHARED_INSTALL_PATH' in os.environ:
            existingProjects = {}
            for id, branch in projectBuildDependencies[identifier].items():
                if id in builtProjects:
                    existingProjects[id] = branch

            if existingProjects:
                exisitingDeps = set()

                for projectId in existingProjects.keys():
                    exisitingDeps.update(lazyResolveProjectDeps(workingDirectory, projectId, existingProjects[projectId], dependencyResolver))
                    exisitingDeps.add(projectId)

                commandToRun += ' --skip-deps ' + ' '.join(exisitingDeps)

        print('## Run project build: {}'.format(commandToRun))

        # Then run it!
        try:
            subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=projectSources )
        except:
            print('## Failed building a project: {}'.format(identifier))
            print('## Projects built: \"{}\"'.format((' '.join(builtProjects.keys()))))
            print('## Projects **not** built: \"{}\"'.format(' '.join(projectsToBuild.keys())))
            raise

        # Add it to the list of projects we've built
        builtProjects[ identifier ] = branch


####
# We're done!
####

sys.exit(0)
