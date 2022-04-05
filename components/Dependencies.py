import os
import yaml
import fnmatch
import subprocess

# Class to handle resolving dependencies for projects
class Resolver(object):

    # Set ourselves up
    # This should receive the path to the projects metadata
    # as well as the path to a YAML file containing the magic branches resolution information
    def __init__( self, projectsMetadata, branchRules, platform ):
        # Start by initialising a data store for all of the projects
        self.projects = {}
        self.projectsByIdentifier = {}
        # Store our platform for future use
        self.platform = platform

        # Start reading in the metadata tree
        for currentPath, subdirectories, filesInFolder in os.walk( projectsMetadata, topdown=False, followlinks=False ):
            # Do we have a metadata.yaml file?
            if 'metadata.yaml' not in filesInFolder:
                # We're not interested then....
                continue

            # Now that we know we have something to work with....
            # Lets load the current metadata up
            metadataPath = os.path.join( currentPath, 'metadata.yaml' )
            metadataFile = open( metadataPath, 'r' )
            metadata = yaml.safe_load( metadataFile )
            
            # Extract the repository path, then save the details on the project we have found
            repositoryPath = metadata['repopath']
            self.projects[ repositoryPath ] = metadata

            # We also store an equivalent using the project identifier (used by seed-package-registry.py)
            identifier = metadata['identifier']
            self.projectsByIdentifier[ identifier ] = metadata

        # Now read in the magic branches resolution information
        branchRulesFile = open( branchRules, 'r' )
        self.branchRules = yaml.safe_load( branchRulesFile )

    # Determine the correct branch to use for this project
    def _resolveDependencyBranch( self, dependency, branchRule, projectBranch ):
        # First we check to see if this is a "magic" branch rule requiring additional resolution
        # If not, we can skip all of this...
        # Magic branch rules always start with '@'
        if not branchRule.startswith('@'):
            return branchRule

        # Are we dealing with @same?
        if branchRule == '@same':
            # Then we need to perform some normalization to the branch...
            return self._resolveSameBranch( projectBranch )

        # Is this a known form of "magic" branch rule?
        # If it isn't then there is not much we can do - best we can do is assume this is a false positive and we shouldn't be here
        if branchRule not in self.branchRules:
            return branchRule

        # Now that we have that sorted, next thing to do is see if this project has a specific rule just for itself
        if dependency['repopath'] in self.branchRules[ branchRule ]:
            # Return the branch specified by that rule
            dependencyPath = dependency['repopath']
            return self.branchRules[ branchRule ][ dependencyPath ]

        # Final check to do is to go over each of the rules and see if they match as a glob pattern
        # This allows for rules like frameworks/* to be specified
        for repositoryRule, branch in self.branchRules[ branchRule ].items():
            # Check if it matches...
            if fnmatch.fnmatch(dependency['repopath'], repositoryRule):
                return branch

        # Finally if we found no match, just return the branch rule back as it is the best we can do...
        return branchRule

    # Resolve an @same branch for this project
    # This needs special handling as we need to turn the current branch name (if it is work/* or refs/merge_request/*) into something reasonable
    def _resolveSameBranch( self, projectBranch ):
        # First thing we do is see if we need to do anything to this branch name
        # We know it is okay if this is a protected branch (ie. we're on master or a release branch - being any branch matching the *.* convention)
        if 'CI_COMMIT_REF_PROTECTED' in os.environ and os.environ['CI_COMMIT_REF_PROTECTED'] == "true":
            return projectBranch

        # Otherwise it looks like we need to do something to resolve the branch here
        # Doing this involves some Git voodoo combined with some assumptions on how KDE projects name their branches
        # Unless we are on a merge request of course....
        if 'CI_MERGE_REQUEST_TARGET_BRANCH_NAME' in os.environ:
            # If we are then we assume the target is reasonable and try to use that
            return os.environ['CI_MERGE_REQUEST_TARGET_BRANCH_NAME']

        # To do this we need to first get a list of commits that are in the branch we are building (HEAD) which aren't in any mainline branch
        # This is done by asking Git to print a list of all refs it knows of, prefixed by the negate operator (^)
        # We then reduce that to just mainline branches prior to passing it to git rev-list
        # Finally, we run git rev-list in reverse mode so it puts the oldest commit at the top (whose parent commit will be on a release branch)
        command = 'git for-each-ref --format="^%(refname)" | grep -E "refs/heads/master|refs/heads/.*[0-9]\.[0-9]+" | git rev-list --stdin --reverse HEAD | head -n1'
        process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        firstBranchCommit = process.stdout.readline().strip().decode('utf-8')

        # Make sure we ended up with a valid 'first branch commit'
        # If we are on a newly formed branch or tag that is identical in commit structure to an existing protected branch then the above will return nothing
        if firstBranchCommit == "":
            # Fallback to HEAD
            firstBranchCommit = "HEAD"

        # With the first branch commit now being known, we can do the second phase of this
        # This involves asking Git to print a list of all references that contain the given commit
        # Once again, we also filter this to only leave behind release branches - as that is what we are trying to resolve to
        command = 'git for-each-ref --contains {0}^ --format="%(refname)" | grep -E "refs/heads/master|refs/heads/.*[0-9]\.[0-9]+" | sort -r -n'.format( firstBranchCommit )
        process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        rawPotentialBranches = process.stdout.readlines()

        # The output we receive from git for-each-ref will need some cleanup before we can start examining it
        cleanedBranches = [entry.strip().decode('utf-8').replace('refs/heads/', '') for entry in rawPotentialBranches]

        # Did we get anything back?
        # If not (which can only happen in very rare edge cases) fallback to 'master'
        if len(cleanedBranches) == 0:
            return 'master'

        # Do we have master present?
        # We always prefer master if it is present on the assumption that developers are normally targeting the latest branch, not stable
        if 'master' in cleanedBranches:
            return 'master'

        # Otherwise we prefer the branch that was at the top of the list
        # We can rely on this as reverse natural sorting will put the largest number at the top
        return cleanedBranches[0]

    # Resolve the dependency rules we have been provided
    def resolve( self, rules, currentBranch ):
        # Prepare to start resolution
        foundDependencies = {}

        # Start processing a given ruleset
        for dependencyRuleset in rules:
            # Check to make sure our platform is covered by this ruleset
            # Our platform is covered if it is mentioned specifically or if '@all' is mentioned as a platform to cover
            if '@all' not in dependencyRuleset['on'] and '@everything' not in dependencyRuleset['on'] and self.platform not in dependencyRuleset['on']:
                continue
        
            # Now that we have that sorted, start going over the actual project specifications...
            for requirement, requirementBranch in dependencyRuleset['require'].items():
                # Find the projects that match the specification we have been given
                matchingProjects = [ project for repositoryPath, project in self.projects.items() if fnmatch.fnmatch(repositoryPath, requirement) ]
                # Next we need to resolve the branch for each of the dependencies we have found
                # This will be needed later to fetch the appropriate build
                for requirementProject in matchingProjects:
                    # Determine the branch to use
                    resolvedBranch = self._resolveDependencyBranch( requirementProject, requirementBranch, currentBranch )
                    # Extract the project identifier...
                    identifier = requirementProject['identifier']
                    # Add it to the list of found dependencies
                    foundDependencies[ identifier ] = resolvedBranch

        # With the rulesets all processed, we now have the immediate dependencies of this project - our job is therefore done here
        return foundDependencies
