#!/usr/bin/env python3
import os
import sys
import time
import argparse
import gitlab
from components import Package

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to cleanup a Gitlab Package Registry.')
parser.add_argument('--project', type=str, required=True)
arguments = parser.parse_args()

# Retrieve the details of the package registry we will be cleaning up
gitlabInstance = os.environ.pop('KDECI_GITLAB_SERVER')
gitlabToken    = os.environ.pop('KDECI_GITLAB_TOKEN')

# Grab the Gitlab project we will be working on
packageProject = arguments.project

# Connect to Gitlab
gitlabServer = gitlab.Gitlab( gitlabInstance, private_token=gitlabToken )
# Then retrieve our registry project
remoteRegistry = gitlabServer.projects.get( packageProject )

# Start building up a list of known packages
knownPackages = {}
packagesToRemove = []

# Configuration - list of branches to always purge
branchesToRemove = [
    'transition.now/android-35', # has been merged into master 2025-08-26
]

# Configuration - list of Qt 5 package projects...
packageProjectsForQt5 = [
]

# Configuration - list of Qt 6 package projects...
packageProjectsForQt6 = [
]

# Configuration - list of projects whose master is Qt 6 only now
projectsWithQt6OnlyMaster = [
]

# Configuration - list of projects to always remove
projectsToAlwaysRemove = [
    # QtWebKit is no longer supported
    'kdewebkit',
]

normalizedBranchesToRemove = [ Package.Registry._normaliseBranchName(branch) for branch in branchesToRemove ]

# Now that we have that setup, let's find out what packages our Gitlab package project knows about
for package in remoteRegistry.packages.list( iterator=True ):
    # Grab the version (branch+timestamp) and break it out into the corresponding components
    # We use the version snapshotted at the time the package was created to ensure that we agree with the metadata file
    branch, timestamp = package.version.rsplit('-', 1)

    # Create the known package key - this is a combination of the identifier and the branch
    key = "{0}--{1}".format( package.name, branch )

    # Prepare the details we want to keep...
    packageData = {
        'package': package,
        'identifier': package.name,
        'branch': branch,
        'timestamp': int(timestamp)
    }

    # Is this a project we should always be removing?
    if package.name in projectsToAlwaysRemove:
        # Then remove it
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this a stale branch we can let go of?
    if branch in normalizedBranchesToRemove:
        # Then mark it for removal
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this a 'master' package in a Qt 5 repository?
    if arguments.project in packageProjectsForQt5 and package.name in projectsWithQt6OnlyMaster and branch == "master":
        # Then remove it too!
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this a 'kf5' package in a Qt 6 repository?
    if arguments.project in packageProjectsForQt6 and branch == "kf5":
        # Perform the removal
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this the first time we have seen this package key?
    if key not in knownPackages:
        # Then we can assume for now it is the newest version
        # Save it and continue
        knownPackages[ key ] = packageData
        continue

    # Now that we know this is not a unique package we need to determine if this one is newer or not
    # We can do this by comparing timestamps - if the known package is newer then it should be kept and this package removed
    if knownPackages[ key ]['timestamp'] > packageData['timestamp']:
        # This package is older than the known package, clean it up
        packagesToRemove.append( package )
        continue

    # Looks like the currently known package is older
    # We therefore need to clean it up....
    packagesToRemove.append( knownPackages[ key ]['package'] )
    
    # Then register the new known package
    knownPackages[ key ] = packageData

# Actually remove the packages we want to remove
for package in packagesToRemove:
    # Let the user know
    print("Removing: " + package.name + " - " + package.version)
    # Action the removal
    package.delete()
    # Try not to overload Gitlab
    time.sleep(1)

# For good user feedback, print a list of what we are retaining
#for key, packageData in knownPackages.items():
    # Print the details
    #print("Kept: " + packageData['identifier'] + " - " + packageData['branch'] + " - " + str(packageData['timestamp']))

# All done!
sys.exit(0)
