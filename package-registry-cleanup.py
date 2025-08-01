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

# Configuration - list of Qt 5 package projects...
packageProjectsForQt5 = [
    'teams/ci-artifacts/suse-qt5.15',
    'teams/ci-artifacts/suse-qt5.15-static',
    'teams/ci-artifacts/freebsd-qt5.15',
    'teams/ci-artifacts/android-qt5.15',
    'teams/ci-artifacts/windows-qt5.15',
    'teams/ci-artifacts/windows-qt5.15-static',
]

# Configuration - list of projects whose master is Qt 6 only now
projectsWithQt6OnlyMaster = [
    # Frameworks
    'attica', 'baloo', 'bluez-qt', 'breeze-icons', 'extra-cmake-modules', 'frameworkintegration', 'kactivities', 'kactivities-stats',
    'kapidox', 'karchive', 'kauth', 'kbookmarks', 'kcalendarcore', 'kcmutils', 'kcodecs', 'kcompletion', 'kconfig', 'kconfigwidgets', 
    'kcontacts', 'kcoreaddons', 'kcrash', 'kdav', 'kdbusaddons', 'kdeclarative', 'kded', 'kdelibs4support', 'kdesignerplugin', 'kdesu',
    'kdewebkit', 'kdnssd', 'kdoctools', 'kemoticons', 'kfilemetadata', 'kglobalaccel', 'kguiaddons', 'kholidays', 'khtml', 'ki18n',
    'kiconthemes', 'kidletime', 'kimageformats', 'kinit', 'kio', 'kirigami', 'kitemmodels', 'kitemviews', 'kjobwidgets', 'kjs', 'kjsembed',
    'kmediaplayer', 'knewstuff', 'knotifications', 'knotifyconfig', 'kpackage', 'kparts', 'kpeople', 'kplotting', 'kpty', 'kquickcharts',
    'kross', 'krunner', 'kservice', 'ktexteditor', 'ktextwidgets', 'kunitconversion', 'kwallet', 'kwayland', 'kwidgetsaddons', 'kwindowsystem',
    'kxmlgui', 'kxmlrpcclient', 'modemmanager-qt', 'networkmanager-qt', 'oxygen-icons5', 'plasma-framework', 'prison', 'purpose', 'qqc2-desktop-style',
    'solid', 'sonnet', 'syndication', 'syntax-highlighting', 'threadweaver',
]

# Configuration - list of projects to always remove
projectsToAlwaysRemove = [
    # QtWebKit is no longer supported
    'kdewebkit',
]
        
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

    # Is this a project we should always be removing?
    if package.name in projectsToAlwaysRemove:
        # Then remove it
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this a stale branch we can let go of?
    if branch in ['release-21.08', 'release-21.12', 'release-22.04', 'release-22.08', 'release-22.12', 'Plasma-5.24', 'Plasma-5.25', 'Plasma-5.26']:
        # Then mark it for removal
        packagesToRemove.append( packageData['package'] )
        continue

    # Is this a 'master' Framework package in a Qt 5 repository
    if arguments.project in packageProjectsForQt5 and package.name in projectsWithQt6OnlyMaster and branch == "master":
        # Then remove it too!
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
