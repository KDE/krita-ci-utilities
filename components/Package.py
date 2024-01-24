import os
import sys
import copy
import json
import gitlab
import shutil
import tempfile
import packaging.version

class Registry(object):

    # Record all the details we need for later use
    def __init__(self, localCachePath, gitlabInstance, gitlabToken, gitlabPackageProject):
        # Store all the details we have been given for later use
        self.localCachePath = localCachePath

        # First prepare to gather details from both the cache and the remote registry
        self.cachedPackages = []
        self.remotePackages = []

        # Make sure the local cache path exists
        if not os.path.exists( self.localCachePath ):
            os.makedirs( self.localCachePath )

        # Determine what we have locally first
        cacheContents = os.listdir( self.localCachePath )
        for filename in cacheContents:
            # Make sure we are dealing with a metadata *.json file here
            if not filename.endswith('.json'):
                continue
            
            # Construct the full path to the file, then load it's contents
            fullPath = os.path.join( self.localCachePath, filename )
            packageMetadata = json.load( open(fullPath) )
            
            # Determine which package we have here and add it to our list of known packages
            self.cachedPackages.append( packageMetadata )
        
        # Now we reach out to the remote registry...
        # First establish a connection to Gitlab
        # For reasons unknown using the native OAuth token support in python-gitlab doesn't work here, but oauth:token as a HTTP password does
        if gitlabToken is not None:
            gitlabServer = gitlab.Gitlab( gitlabInstance, private_token=gitlabToken )
        else:
            gitlabServer = gitlab.Gitlab( gitlabInstance )

        # Then retrieve our registry project
        self.remoteRegistry = gitlabServer.projects.get( gitlabPackageProject )
        
        # Now that we have that setup, let's find out what packages our Gitlab package project knows about
        for package in self.remoteRegistry.packages.list( as_list=False, iterator=True ):
            # Grab the version (branch+timestamp) and break it out into the corresponding components
            # We use the version snapshotted at the time the package was created to ensure that we agree with the metadata file
            branch, timestamp = package.version.rsplit('-', 1)

            # Create the details we will be saving
            packageMetadata = {
                'identifier': package.name,
                'version': package.version,
                'branch': branch,
                'timestamp': int(timestamp),
            }

            # Save it to the list and move on to the next one
            self.remotePackages.append( packageMetadata )

    # Convert a branch name into a standardised form
    def _normaliseBranchName( self, branch ):
        # Cleanup a Git branch name for use in our Package Registry
        return branch.replace('/', '-')

    # Choose between two branches to determine which one is "newer"
    def _selectNewerBranch( self, firstBranch, secondBranch ):
        # First we need to check whether either of these are 'master'
        # If they are, then we don't need to do anything further as master always wins
        if firstBranch == 'master' or secondBranch == 'master':
            return 'master'

        # Otherwise we do a version comparison...
        if packaging.version.parse( firstBranch ) > packaging.version.parse( secondBranch ):
            # Then the first branch is newer
            return firstBranch

        # Otherwise we can assume the second branch wins
        return secondBranch
            
    # Retrieve a package matching the supplied parameters
    # Returns a tuple containing a handle to the package archive and a dictionary of metadata surrounding the package
    def retrieve(self, identifier, branch, onlyMetadata = False):
        # Get ready to search
        remotePackage = None
        cachedPackage = None

        # Prepare a normalised branch name
        normalisedBranch = self._normaliseBranchName( branch )

        # We start this process by searching through our remote details
        for entry in self.remotePackages + self.cachedPackages:
            # If the identifier and branch don't match then skip over to the next one
            # We have to use the normalised branch name when doing the comparison, as the entries returned from Gitlab's API will be normalised
            if entry['identifier'] != identifier or entry['branch'] != normalisedBranch:
                continue

            # Do we have an existing match?
            if remotePackage is None:
                remotePackage = entry

            # Is this match newer than our previous match?
            if entry['timestamp'] > remotePackage['timestamp']:
                remotePackage = entry

        # Before we continue, did we find something?
        # If we found nothing, bow out gracefully here...
        if remotePackage is None:
            return ( None, None )

        # Determine the name we use for the files in the cache as well as the path to the files
        packageName = "{0}-{1}".format( remotePackage['identifier'], remotePackage['branch'] )
        localContentsPath = os.path.join( self.localCachePath, packageName + ".tar" )
        localMetadataPath = os.path.join( self.localCachePath, packageName + ".json" )

        # Next we check to see if we have a local cache entry
        # If we do, then we can rely on that rather than retrieving a fresh copy from the remote archive
        for entry in self.cachedPackages:
            # Make sure the identifier, branch and timestamp all agree
            # If they do, then we have found the package in the cache
            # (By definition the package cannot be newer as we have the latest remote version - if it is then something is seriously wrong)
            if entry['identifier'] == identifier and entry['branch'] == branch and entry['timestamp'] == remotePackage['timestamp']:
                cachedPackage = entry

        # If we have a cachedPackage entry then we can assume we have a cache hit and we should use that
        if cachedPackage:
            # Return the contents file and the corresponding metadata
            return ( localContentsPath, cachedPackage )

        # Let's retrieve the file if we need to now...
        # First we need to formulate the original version string
        # Download the metadata first...
        response = self.remoteRegistry.generic_packages.download( 
            package_name=remotePackage['identifier'],
            package_version=remotePackage['version'],
            file_name="metadata.json"
        )

        if onlyMetadata:
            return ( None, json.loads(response) )

        latestMetadata = tempfile.NamedTemporaryFile(delete=False, mode='wb', dir=self.localCachePath)
        latestMetadata.write( response )
        latestMetadata.close()

        extraDownloadArgs = {}

        if os.environ.get('KDECI_COMPRESS_PACKAGES_ON_DOWNLOAD', '0') in ['1', 'True', 'true']:
            extraDownloadArgs = {
                'headers' : {'Accept-Encoding': 'gzip, deflate'}
            }

        # Now the metadata...
        response = self.remoteRegistry.generic_packages.download(
            package_name=remotePackage['identifier'], 
            package_version=remotePackage['version'],
            file_name="archive.tar",
            **extraDownloadArgs
        )
        latestContent = tempfile.NamedTemporaryFile(delete=False, mode='wb', dir=self.localCachePath)
        latestContent.write( response )
        latestContent.close()

        # Move both to the cache for future use
        shutil.move( latestContent.name, localContentsPath )
        shutil.move( latestMetadata.name, localMetadataPath )

        # All done, we can return a tuple of the archive and metadata now
        localContentsPath = localContentsPath
        localMetadataFile = json.load( open(localMetadataPath) )
        return ( localContentsPath, localMetadataFile )

    # Takes a dict of projects (with values being the branches), and fetches them and any dependencies they have
    # Returns the complete list for further processing
    def retrieveDependencies(self, dependenciesToFetch, runtime=False, onlyMetadata = False):
        # Prepare a list of the details we need to keep
        fetchedPackages = {}
        packageBranches = {}

        # Create the list of dependencies we will need to resolve
        dependenciesToResolve = copy.deepcopy( dependenciesToFetch )

        # Go over the list of dependencies we need to process
        # As we go we will add the dependencies of that package to the list, so we just check to see if it is empty
        while len(dependenciesToResolve) > 0:
            # Grab the first one from the list...
            identifier, branch = dependenciesToResolve.popitem()

            # First, have we already encountered this package?
            # If so there is nothing to do
            if identifier in fetchedPackages:
                continue

            # Given we have not previously fetched this dependency, we should do so...
            try:
                fetchedPackages[ identifier ] = self.retrieve( identifier, branch, onlyMetadata=onlyMetadata )
            except Exception:
                raise Exception("Unable to locate requested dependency in the registry: {} (branch: {})".format( identifier, branch ))

            # We should also register the branch we have fetched
            packageBranches[ identifier ] = branch

            # Pull the metadata out...
            packageContents, packageMetadata = fetchedPackages[ identifier ]

            # Make sure we have received a usable package
            # Otherwise throw an exception and bail
            if packageMetadata is None:
                raise Exception("Unable to locate requested dependency in the registry: {} (branch: {})".format( identifier, branch ))

            # Go over all the dependencies this package has and build a list to examine
            # If we have been asked to include runtime dependencies, we need to capture them as well
            packageDependencies = {}
            packageDependencies.update( packageMetadata['dependencies'] )
            if runtime and 'runtime-dependencies' in packageMetadata:
                packageDependencies.update( packageMetadata['runtime-dependencies'] )

            # Go over all the dependencies this package has
            # If we haven't fetched it already, then we should add it to the list to process
            for dependency, dependencyBranch in packageDependencies.items():
                # Is this package one we have seen before?
                # and if it is, then is the branch the same?
                if dependency in packageBranches and packageBranches[ dependency ] == dependencyBranch:
                    # Then there is nothing for us to do here - this package has been seen already
                    # We don't need to worry about it any further, as it's dependencies will have been resolved already :)
                    continue

                # However, if we have seen it before and the branch isn't the same then we have a problem!
                # This means a project wants two different versions of the same bit of software, which is not going to work
                if dependency in packageBranches:
                    # To work around this, we simply assume the newer version is what we should provide
                    # This is not ideal, but the Developer can hold the broken pieces if this does not work out
                    dependenciesToResolve[ dependency ] = self._selectNewerBranch( packageBranches[ dependency ], dependencyBranch )
                    continue
                
                # Then we know we are safe to add it to the list
                dependenciesToResolve[ dependency ] = dependencyBranch

        # Processing complete!
        return list( fetchedPackages.values() )

    def generateMetadata(self, archivePath, identifier, branch, gitRevision, additionalMetadata = {}):
        # Formulate the remote version number
        # While Git branches may contain slashes, the Gitlab generic package registry does not allow this so we need to normalise it first
        normalisedBranch = self._normaliseBranchName( branch )

        # Make sure that the archive path we have been given exists
        if not os.path.exists( archivePath ):
            return None

        # With the branch name normalised, we can now generate the version string to provide to Gitlab's package registry
        packageTimestamp = int( os.path.getmtime( archivePath ) )
        versionForGitlab = "{0}-{1}".format( normalisedBranch, packageTimestamp )

        # Prepare the metadata, ensuring that the minimum bits of information are being included
        packageMetadata = {
            'identifier': identifier,
            'branch': branch,
            'version': versionForGitlab,
            'timestamp': packageTimestamp,
            'gitRevision': gitRevision,
            'dependencies': {},
            'runtime-dependencies': {},
        }
        # Include the additional information we have been provided
        packageMetadata.update( additionalMetadata )

        return packageMetadata

    def upload(self, archivePath, identifier, branch, gitRevision, additionalMetadata = {}):
        # Make sure that the archive path we have been given exists
        if not os.path.exists( archivePath ):
            return False

        # Prepare the metadata, ensuring that the minimum bits of information are being included
        packageMetadata = self.generateMetadata(archivePath, identifier, branch, gitRevision, additionalMetadata)

        if packageMetadata is None:
            return False

        # With the branch name normalised, we can now generate the version string to provide to Gitlab's package registry
        versionForGitlab = packageMetadata['version']

        # Turn this into a file for upload
        latestMetadata = tempfile.NamedTemporaryFile(delete=False, mode='w')
        json.dump( packageMetadata, latestMetadata, indent = 4 )
        latestMetadata.close()

        # Start by uploading the archive to Gitlab
        # For the Tarball we cannot use the python-gitlab method as it reads the whole thing into memory
        # We therefore reach into the innards of python-gitlab and do it ourselves directly - bit of a pity that it tries to read it into memory as in theory it should work fine if it did not
        tarballFile = open( archivePath, 'rb' )
        tarballUploadUrl = f"{self.remoteRegistry.generic_packages._computed_path}/{identifier}/{versionForGitlab}/archive.tar"
        package = self.remoteRegistry.manager.gitlab.http_put(tarballUploadUrl, post_data=tarballFile, raw=True)

        # Then upload the metadata
        package = self.remoteRegistry.generic_packages.upload(
            package_name=identifier,
            package_version=versionForGitlab,
            file_name="metadata.json",
            path=latestMetadata.name
        )

        # Cleanup!
        os.remove( latestMetadata.name )

        # All done now!
        return True
