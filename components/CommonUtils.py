import os
import sys
import hashlib
import collections

# Returns the absolute path to the base directory of the CI Tooling checkout we are running from
def scriptsBaseDirectory():
    # Where is this file located?
    fileLocation = os.path.dirname( os.path.realpath(__file__) )

    # We are at /components, therefore the relative location of the base directory is ../
    relativeLocation = '../'

    # Finally we can deduce the absolute path to the base directory
    return os.path.realpath( os.path.join(fileLocation, relativeLocation) )

# Determines where the build directory should be located
# This is done based on the provided source directory and the definition of whether this should be an in or out of source build
def buildDirectoryForSources( sources, inSourceBuild ):
    # If we are an in source build, then the build and source directories are the same
    if inSourceBuild:
        return sources

    # Otherwise, it is a folder named 'build' within the source tree
    return os.path.join( sources, 'build' )

# Determines which of the given files exists first in the specified directory
def firstPresentFile( searchRoot, filesToFind ):
    # Let's start searching....
    availableFiles = [ filename for filename in filesToFind if os.path.isfile(os.path.join(searchRoot, filename)) ]
    # Return the first hit we found, returning an empty string if none were found
    return next( iter(availableFiles), '' )

# Determines where the first of a given set of files is in a given set of directories
def firstPresentFileInPaths( searchRoots, filesToFind ):
    # Start searching...
    validPaths = []
    for rootPath in searchRoots:
        # Look in this directory
        foundFile = firstPresentFile( rootPath, filesToFind )
        # If we found something, we're finished
        if foundFile != '':
            # Make a usable path and return it
            return os.path.join( rootPath, foundFile )

    # If we failed to find anything, return blank
    return ''

def recursiveDirectoryCopy(sourceDirectory, destinationDirectory):
    # Copy a directory structure overwriting existing files
    for root, dirs, files in os.walk(sourceDirectory):
        # Ensure we have a relative path for root as we'll need it quite a bit shortly
        currentDirectory = os.path.relpath( root, sourceDirectory )

        # Make sure the directory exists in our destination
        currentDestination = os.path.join( destinationDirectory, currentDirectory )
        if not os.path.isdir(currentDestination):
            os.makedirs(currentDestination)

        # Now we can copy the various files within in turn
        for fileToCopy in files:
            # Determine the full path to the source file
            fileSource = os.path.join(root, fileToCopy)
            # Determine where to copy the file to
            fileDestination = os.path.join(currentDestination, fileToCopy)
            # Copy it!
            shutil.copyfile( fileSource, fileDestination )

# Converts a path to a relative one, to allow for it to be passed to os.path.join
# This is primarily relevant on Windows, where full paths have the drive letter, and thus can be simply joined together as you can on Unix systems
def makePathRelative(path):
    # If we're on Windows, chop the drive letter off...
    if sys.platform == "win32":
        return path[3:]

    # Otherwise we just drop the starting slash off
    return path[1:]

# Convenience function to generate the SHA-256 hash of a given file
# We read files in small chunks, to ensure we can handle large files if needed
def generateFileChecksum( filenameToHash ):
    # Grab our hasher
    hasher = hashlib.sha256()
    # Open the file
    with open(filenameToHash, 'rb') as fileToHash:
        # Read chunks until there are no more, passing them to the hasher as we go
        fileChunk = fileToHash.read(65336)
        while len(fileChunk) > 0:
            hasher.update(fileChunk)
            fileChunk = fileToHash.read(65336)

    # All done, return the generated hash
    return hasher.hexdigest()

# Convenience function to recursively merge Python dictionaries
# This is of particular importance to the configuration loading code
def recursiveUpdate(d, u):
    # Start by going over all the items in the dictionary that is being merged in
    for key, value in u.items():
        # If our value contains a mapping (dict, list, etc) then recurse into it
        # Otherwise just update the value
        if isinstance(value, collections.abc.Mapping):
            d[key] = recursiveUpdate( d.get(key, {}), value )
        else:
            d[key] = value

    # Return the merged values
    return d
