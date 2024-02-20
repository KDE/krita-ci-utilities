import os
import sys
import yaml
from components import CommonUtils, Dependencies


####
# Load the project configuration
####
def loadProjectConfiguration(projectRoot, projectName):
    # This consists of:
    # 0) Global configuration
    configuration = yaml.safe_load( open(os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', 'global.yml')) )

    # 1) Project/branch specific configuration contained within the repository
    localConfigFile = os.path.join( projectRoot, '.kde-ci.yml' )
    if os.path.exists( localConfigFile ):
        localConfig = yaml.safe_load( open(localConfigFile) )
        CommonUtils.recursiveUpdate( configuration, localConfig )

    # 2) Global overrides applied to the project configuration
    projectConfigFile = os.path.join(CommonUtils.scriptsBaseDirectory(), 'config', projectName + '.yml')
    if os.path.exists( projectConfigFile ):
        projectConfig = yaml.safe_load( open(projectConfigFile) )
        CommonUtils.recursiveUpdate( configuration, projectConfig )

    if 'KDECI_GLOBAL_CONFIG_OVERRIDE_PATH' in os.environ:
        overridePath = os.environ['KDECI_GLOBAL_CONFIG_OVERRIDE_PATH']
        if os.path.exists( overridePath ):
            overrideConfig = yaml.safe_load( open(overridePath) )
            CommonUtils.recursiveUpdate( configuration, overrideConfig )
        else:
            print('## Error: $KDECI_GLOBAL_CONFIG_OVERRIDE_PATH({}) is present, but the file doesn\'t exist'.format(overridePath))
            sys.exit(-1)

    return configuration

####
# Prepare to resolve and fetch our project dependencies
####
def prepareDependenciesResolver(platform):
    metadataFolderPath = os.environ.get('KDECI_REPO_METADATA_PATH', os.path.join(CommonUtils.scriptsBaseDirectory(), 'repo-metadata'))

    # Determine where some key resources we need for resolving dependencies will be found...
    projectsMetadataPath = os.path.join( metadataFolderPath, 'projects-invent' )
    branchRulesPath = os.path.join( metadataFolderPath, 'branch-rules.yml' )

    # Bring our dependency resolver online...
    return Dependencies.Resolver( projectsMetadataPath, branchRulesPath, platform )

####
# Lazily retrieve project dependency information either from a local build or
# from the package registry
####
packageRegistry = None
def lazyResolveProjectDeps(workingDirectory, projectId, projectBranch, dependencyResolver):
    exisitingDeps = set()
    projectDirectory = os.path.join(workingDirectory, projectId)

    if not os.path.exists(projectDirectory):
        localCachePath = os.environ['KDECI_CACHE_PATH']
        gitlabInstance = os.environ['KDECI_GITLAB_SERVER']
        packageProject = os.environ['KDECI_PACKAGE_PROJECT']

        if packageRegistry is None:
            packageRegistry = Package.Registry( localCachePath, gitlabInstance, None, packageProject )
        allDependencies = packageRegistry.retrieveDependencies( [projectId], onlyMetadata=True )

        exisitingDeps.update([item[1]['identifier'] for item in allDependencies])
    else:
        configuration = loadProjectConfiguration(projectDirectory, projectId)
        projectBuildDependencies = dependencyResolver.resolve( configuration['Dependencies'], projectBranch )

        for childDep, childBranch in projectBuildDependencies.items():
            exisitingDeps.add(childDep)
            exisitingDeps.update(lazyResolveProjectDeps(workingDirectory, childDep, childBranch, dependencyResolver))

    return exisitingDeps

####
# Generate reverse dependencies mapping, e.g.
#    ext_zlib -> ext_qt
#    ext_qt -> ext_kimageformats
####
def genReverseDeps(workingDirectory, dependencyResolver, branch, debug = False, onlyPlatformDeps = None):
    reverseDeps = {}
    for subdir, dirs, files in os.walk(workingDirectory):
        relative = os.path.relpath(subdir, workingDirectory)
        depth = os.path.normpath(relative).count(os.sep) + 1

        if depth >= 2:
            dirs.clear()

        subDirName = os.path.basename(subdir)

        if subDirName == os.path.basename(workingDirectory):
            continue

        if not subDirName.startswith('ext_'):
            dirs.clear()
            continue

        checkAllowed = lambda name: (name in onlyPlatformDeps) if not onlyPlatformDeps is None else True

        projectName = subDirName

        if not checkAllowed(projectName): continue

        if os.path.exists(os.path.join(subdir, 'CMakeLists.txt')):
            configuration = loadProjectConfiguration(subdir, projectName)
            projectBuildDependencies = list(dependencyResolver.resolve( configuration['Dependencies'], branch ).keys())
            projectBuildDependencies = list(filter(checkAllowed, projectBuildDependencies))

            if debug:
                print ("##  project: {} depends: {}".format(projectName, projectBuildDependencies))

            # found the project, don't check subdirs anymore
            dirs.clear()

            for dep in projectBuildDependencies:
                if dep in reverseDeps:
                    reverseDeps[dep].add(projectName)
                else:
                    reverseDeps[dep] = set([projectName])
    return reverseDeps
