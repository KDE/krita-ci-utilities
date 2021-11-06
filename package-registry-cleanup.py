#!/usr/bin/python3
import os
import sys
import time
import gitlab
import argparse
import subprocess

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
        
# Now that we have that setup, let's find out what packages our Gitlab package project knows about
for package in remoteRegistry.packages.list( as_list=False ):
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
for key, packageData in knownPackages.items():
    # Print the details
    print("Kept: " + packageData['identifier'] + " - " + packageData['branch'] + " - " + str(packageData['timestamp']))

# All done!
sys.exit(0)
