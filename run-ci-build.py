#!/usr/bin/python3
import os
import sys
import yaml
import tarfile
import tempfile
import argparse
import subprocess
import multiprocessing
from components import CommonUtils, Package, EnvironmentHandler, TestHandler, PlatformFlavor, EnvFileUtils, MergeFolders
from components.CiConfigurationUtils import *
import shutil
import copy
import time
import datetime
import json

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Utility to perform a CI run for a KDE project.')
parser.add_argument('--project', type=str, required=True)
parser.add_argument('--branch', type=str, required=True)
parser.add_argument('--platform', type=str, required=True)
parser.add_argument('--only-build', default=False, action='store_true')
parser.add_argument('--only-deps', default=False, action='store_true')
parser.add_argument('-e', '--env', type=str, help='The name of the environment initialization file; relative paths are resolved relative to the workdir')
parser.add_argument('--only-env', action='store_true', help='Fetch deps, generate environment file and exit')
parser.add_argument('--extra-cmake-args', type=str, nargs='+', action='append', required=False)
parser.add_argument('--skip-publishing', default=False, action='store_true')
parser.add_argument('--publish-to-cache', default=False, action='store_true')
parser.add_argument('--skip-dependencies-fetch', default=False, action='store_true')
parser.add_argument('--fail-on-leaked-stage-files', default=False, action='store_true')
parser.add_argument('-s','--skip-deps', nargs='+', help='A space-separated list of dependencies to skip fetching', required=False)
arguments = parser.parse_args()
platform = PlatformFlavor.PlatformFlavor(arguments.platform)

if arguments.only_deps:
    if arguments.only_build:
        print ("WARNING: argument --only-build is ignored, since --only-deps is preset")
    if arguments.extra_cmake_args:
        print ("WARNING: argument --extra-cmake-args is ignored, since --only-deps is preset")
    if arguments.skip_publishing:
        print ("WARNING: argument --skip-publishing is ignored, since --only-deps is preset")
    if arguments.fail_on_leaked_stage_files:
        print ("WARNING: argument --fail-on-leaked-stage-files is ignored, since --only-deps is preset")
    if arguments.skip_dependencies_fetch:
        print ("ERROR: argument --skip-dependencies-fetch conflicts with --only-deps")

if arguments.only_env:
    if arguments.only_build:
        print ("WARNING: argument --only-build is ignored, since --only-env is preset")
    if arguments.extra_cmake_args:
        print ("WARNING: argument --extra-cmake-args is ignored, since --only-env is preset")
    if arguments.skip_publishing:
        print ("WARNING: argument --skip-publishing is ignored, since --only-env is preset")
    if arguments.fail_on_leaked_stage_files:
        print ("WARNING: argument --fail-on-leaked-stage-files is ignored, since --only-env is preset")

if 'KDECI_ONLY_BUILD' in os.environ:
    arguments.only_build = (os.environ['KDECI_ONLY_BUILD'].lower() in ['true', '1', 't', 'y', 'yes'])
    print ('## Overriding --only-build from environment: {}'.format(arguments.only_build))

skipECMAndroidToolchain = False

if 'KDECI_SKIP_ECM_ANDROID_TOOLCHAIN' in os.environ:
    skipECMAndroidToolchain = (os.environ['KDECI_SKIP_ECM_ANDROID_TOOLCHAIN'].lower() in ['true', '1', 't', 'y', 'yes'])
    print ('## Disable ECM\'s Android toolchain file: {}'.format(skipECMAndroidToolchain))

removeInstallFoldersAfterBuild = False

if 'KDECI_REMOVE_INSTALL_FOLDERS_AFTER_BUILD' in os.environ:
    removeInstallFoldersAfterBuild = (os.environ['KDECI_REMOVE_INSTALL_FOLDERS_AFTER_BUILD'].lower() in ['true', '1', 't', 'y', 'yes'])
    print ('## Enable "remove install folder after build": {}'.format(removeInstallFoldersAfterBuild))

####
# Load the project configuration
####

configuration = loadProjectConfiguration('', arguments.project)

# Determine whether we will be running tests
# This is only done if they're enabled for this project and we haven't been asked to just build the project
run_tests = configuration['Options']['run-tests'] and configuration['Options']['build-tests'] and not arguments.only_build
# We also Can't run tests in cross compilation environments, so don't run tests there either
if platform.os in ['Android']:
    run_tests = False

####
# Determine a number of paths we will need later on
####

# Our sources are assumed to be in the current working directory
sourcesPath = os.getcwd()

baseWorkDirectoryPath = os.getcwd()

if 'KDECI_WORKDIR_PATH' in os.environ:
    baseWorkDirectoryPath = os.path.join(os.environ['KDECI_WORKDIR_PATH'], arguments.project)
    potentialBuildFolder = os.path.join(baseWorkDirectoryPath, '_build')
    if os.path.isdir(potentialBuildFolder):
        print('## WARNING: workdir already contains _build folder: {}'.format(potentialBuildFolder))

# Determine where to locate the project build
buildPath = os.path.join( baseWorkDirectoryPath, '_build' )
if configuration['Options']['in-source-build']:
    buildPath = os.getcwd()

# Determine where to unpack the dependencies to
installPath = os.path.join( baseWorkDirectoryPath, '_install' )

if 'KDECI_SHARED_INSTALL_PATH' in os.environ:
    installPath = os.environ['KDECI_SHARED_INSTALL_PATH']

# Determine where we will stage the installation
installStagingPath = os.path.join( baseWorkDirectoryPath, '_staging' )

####
# Fetch project sources
####

# In order to resolve project dependencies later, we need to ensure all remote refs have been fetched
if 'CI_REPOSITORY_URL' in os.environ and os.path.exists('.git/shallow'):
    subprocess.check_call("git fetch --quiet --unshallow --tags {0} +refs/heads/*:refs/heads/*".format(os.environ['CI_REPOSITORY_URL']), shell=True)
elif 'CI_REPOSITORY_URL' in os.environ:
    subprocess.check_call("git fetch --quiet --tags {0} +refs/heads/*:refs/heads/*".format(os.environ['CI_REPOSITORY_URL']), shell=True)

####
# Prepare to resolve and fetch our project dependencies
####

# Bring our dependency resolver online...
dependencyResolver = prepareDependenciesResolver(platform)

defaultBuildType = 'Debug'

# Have we explicitly requested a release build?
# This should only ever be used by applications, and never libraries
# On Windows we do this because building our dependencies in Debug mode is just too hard and MSVC requires everything to be in either Debug or Release (you can't mix/match)
if configuration['Options']['release-build'] or sys.platform == 'win32':
    # Switch the Debug build for a Release one then!
    defaultBuildType = 'Release'


# Retrieve some key bits of information from our environment
# All of these come from environment variables due to needing to be set on either the CI Agent level or the group project level
# We remove them from the environment as they are sensitive (in the case of KDECI_GITLAB_TOKEN especially) and aren't needed by anything else
# Of these values, KDECI_GITLAB_TOKEN is optional as it is only used for writing changes back to the package archive
# The remainder are required for storing packages locally and fetching them
localCachePath = os.environ.pop('KDECI_CACHE_PATH')
gitlabToken    = os.environ.pop('KDECI_GITLAB_TOKEN', None)
buildType = os.environ.get('KDECI_BUILD_TYPE', defaultBuildType)
buildTarget = os.environ.get('KDECI_BUILD_TARGET', 'all')
installTarget = os.environ.get('KDECI_INSTALL_TARGET', 'install')

# We can skip all communication with invent if we're not fetching dependencies, testing or publishing
if not (arguments.skip_dependencies_fetch and arguments.only_build):
    packageProject = os.environ.pop('KDECI_PACKAGE_PROJECT')
    gitlabInstance = os.environ.pop('KDECI_GITLAB_SERVER')

    # Bring the package archive up
    packageRegistry = Package.Registry( localCachePath, gitlabInstance, gitlabToken, packageProject )

    ####
    # Now resolve both build and runtime dependencies, then fetch the build dependencies!
    ####

    # Resolve the dependencies of this project
    projectBuildDependencies = dependencyResolver.resolve( configuration['Dependencies'], arguments.branch )
    # As well as the runtime dependencies
    projectRuntimeDependencies = dependencyResolver.resolve( configuration['RuntimeDependencies'], arguments.branch )

dependenciesToUnpack = []

if not arguments.skip_dependencies_fetch:
    # skip retrieving dependencies which are already prepared
    dependenciesToRetrieve = \
        projectBuildDependencies \
        if arguments.skip_deps is None \
        else dict(item for item in projectBuildDependencies.items() if item[0] not in arguments.skip_deps)

    # Now we can retrieve the build time dependencies
    allDependencies = packageRegistry.retrieveDependencies( dependenciesToRetrieve )

    dependenciesToUnpack = \
        allDependencies \
        if arguments.skip_deps is None \
        else [item for item in allDependencies if item[1]['identifier'] not in arguments.skip_deps]

    # sort the dependencies in the correct order

    projectToDepMap = []

    for packageContents, packageMetadata, cacheStatus in dependenciesToUnpack:
        projectId = packageMetadata['identifier']
        deps = packageMetadata['dependencies']
        projectToDepMap.append((projectId, list(deps.keys())))

    # for project, deps in projectToDepMap:
    #     print (f'{project}: {deps}')

    providedDeps = []
    installDepsOrder = []

    if not arguments.skip_deps is None:
        providedDeps.extend(arguments.skip_deps)

    while projectToDepMap:
        batchToInstall = []
        for project, deps in projectToDepMap:
            if all(dep in providedDeps for dep in deps):
                batchToInstall.append(project)

        projectToDepMap = [(project, dep)
                        for project,dep in projectToDepMap
                        if not project in batchToInstall]

        installDepsOrder.extend(batchToInstall)
        providedDeps.extend(batchToInstall)

    # And then unpack them
    for project in installDepsOrder:
        packageContents, packageMetadata, cacheStatus = \
            next((c,m,s) for c,m,s in dependenciesToUnpack if m['identifier'] == project)

        print('## Unpacking dependency: {} ({})'.format(packageMetadata['identifier'], cacheStatus.name))

        # Open the archive file
        archive = tarfile.open( name=packageContents, mode='r' )

        with tempfile.TemporaryDirectory() as tmpDir:
            # Extract it's contents into a temporary directory
            archive.extractall( path=tmpDir )
            # Merge it into the install directory
            MergeFolders.merge_folders(tmpDir, installPath, move_files=True)

if arguments.only_deps:
    sys.exit(0)

####
# Perform final steps needed to get ready to start the build process
####

# Determine what our build environment should be comprised of....
buildEnvironment = EnvironmentHandler.generateFor( installPrefix=installPath )

# Apply any environment changes from our configuration
for key, value in configuration['Environment'].items():
    # Apply each key in turn
    buildEnvironment[ key ] = value

def ccacheSupportsVerbose():
    result = True

    print( "## Test if ccache supports verbose (\'-vvv\') option")
    commandToRun = 'ccache -vvvs'

    # Run the command
    try:
        print( "## RUNNING: " + commandToRun )
        subprocess.check_call( commandToRun, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True )
    except Exception:
        result = False

    print ('## ccache supports verbose output: {}'.format(result))
    return result

useCcacheForBuilds = configuration['Options']['use-ccache'] and 'KDECI_CC_CACHE' in buildEnvironment
ccacheVerboseArg = '-vvv' if useCcacheForBuilds and ccacheSupportsVerbose() else ''

if arguments.only_env or arguments.only_deps:
    try:
        subprocess.check_call( 'ccache --version', stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )
    except:
        useCcacheForBuilds = False

# Do we need to get ccache ready to use?
if useCcacheForBuilds:
    # Setup the path used for the cache....
    buildEnvironment['CCACHE_DIR'] = os.path.join( buildEnvironment['KDECI_CC_CACHE'], arguments.project )
    buildEnvironment['CMAKE_C_COMPILER_LAUNCHER'] = 'ccache'
    buildEnvironment['CMAKE_CXX_COMPILER_LAUNCHER'] = 'ccache'
    # Ensure ccache is setup for use
    if configuration['Options']['ccache-large-cache']:
        subprocess.check_call( 'ccache -M 20G', stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )
    else:
        subprocess.check_call( 'ccache -M 2G', stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )
    # Reset cache-hit stats
    subprocess.check_call( 'ccache -z {}'.format(ccacheVerboseArg), stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )
    # Dump intial stats for ccache (to estimate the size)
    subprocess.check_call( 'ccache -s {}'.format(ccacheVerboseArg), stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )

# Python can create __pycache__ directories that will trigger DESTDIR leak detection so we disable this
buildEnvironment['PYTHONDONTWRITEBYTECODE'] = '1'

# Make sure the build directory exists
if not os.path.exists( buildPath ):
    os.makedirs( buildPath )

# Let the user know what we are about to do
print("## KDE Continuous Integration System")
print("##")
print("## Starting build for {0} on {1}".format(arguments.project, arguments.branch))
print("##")
print("## Installing project to {0}".format(installPath))
print("## Building project in {0}".format(buildPath))
print("## Staging project directory {0}".format(installStagingPath))
print("##")
print("## Project CI configuration as follows:")
for key, value in configuration['Options'].items():
    print("##    {0}: {1}".format(key, value))
print("##")
print("## Providing the following dependencies:")
for packageContents, packageMetadata, cacheStatus in dependenciesToUnpack:
    print("##    {0} - {1} ({2})".format(packageMetadata['identifier'], packageMetadata['branch'], packageMetadata['gitRevision']))
print("##")
if arguments.skip_deps:
    print("## Skipped the following deps (provided with --skip-deps option):")
    for depId in arguments.skip_deps:
        print("##     {}".format(depId))
print("##")
print("## Building with the following environment variables:")
for variable, contents in buildEnvironment.items():
    print("##    {0}={1}".format(variable, contents))
print("##")

if not arguments.env is None or arguments.only_env:
    envFile = arguments.env

    if envFile is None:
        envFile = 'env'

    if not os.path.isabs(envFile):
        envFile = os.path.abspath(os.path.join(baseWorkDirectoryPath, envFile))

    print("## Generating env file: {}".format(envFile))

    EnvFileUtils.writeEnvFile(os.path.dirname(envFile), os.path.basename(envFile),
                              buildEnvironment)
    if arguments.only_env:
        print("## env file generated, exiting...")
        sys.exit(0)

print("## Starting build process...")

####
# Configure the project!
####

# Begin building up our configure command
# There are some parameters which are universal to all platforms..
cmakeCommand = [
    # Run CMake itself
    'cmake',
    # We want a Debug build to allow for good backtraces
    '-DCMAKE_BUILD_TYPE={}'.format(buildType),
    # We want tests to be built!
    '-DBUILD_TESTING={}'.format('ON' if configuration['Options']['build-tests'] else 'OFF'),
    # And we want to be installed in a given directory
    '-DCMAKE_INSTALL_PREFIX="' + installPath + '"',
    # Generate compile_commands.json for tooling
    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
    # Plus any project specific parameters
    configuration['Options']['cmake-options']
]

useCoverageBuild = False

# Are we on Linux (but not Android)?
# If we are on Linux then we also need to check to see whether we are on a MUSL based system - as ASAN does not work there
if platform.os == 'Linux' and not os.path.exists('/lib/libc.musl-x86_64.so.1'):
    if configuration['Options']['run-gcovr']:
        # Then we also want Coverage by default
        cmakeCommand.append('-DBUILD_COVERAGE=ON')
        useCoverageBuild = True
    if configuration['Options']['use-asan']:
        # We also want to enable ASAN for our builds
        cmakeCommand.append("-DECM_ENABLE_SANITIZERS='address'")

# Are we on Windows?
if sys.platform == 'win32':
    if configuration['Options']['force-ninja-on-windows']:
        # We want a Ninja based build, rather than the default MSBuild
        cmakeCommand.append('-G "Ninja"')
    else:
        cmakeCommand.append('-G "MinGW Makefiles"')

if sys.platform == 'darwin':
    # use ninja if available
    try:
        subprocess.check_call('which ninja', stdout=sys.stdout, stderr=sys.stderr, shell=True, close_fds=True, cwd=buildPath, env=buildEnvironment)
        cmakeCommand.append('-G "Ninja"')
    except Exception:
        print("## Using Makefile Generator")

# Are we building for Android?
if platform.os == 'Android' and not skipECMAndroidToolchain:
    # We want CMake to cross compile appropriately
    cmakeCommand.append('-DKF5_HOST_TOOLING=/opt/nativetooling/lib/x86_64-linux-gnu/cmake/')
    cmakeCommand.append('-DKF6_HOST_TOOLING=/opt/nativetooling6/lib/x86_64-linux-gnu/cmake/')
    # CMake also needs additional guidance to find things
    # First though, apply a necessary transformation to allow CMake to parse the list we pass it
    ecmAdditionalRoots = buildEnvironment['CMAKE_PREFIX_PATH'].replace(':', ';')
    # Then give that list to CMake
    cmakeCommand.append('-DECM_ADDITIONAL_FIND_ROOT_PATH="' + ecmAdditionalRoots + '"')

    # Next we need to set the appropriate toolchain
    ecmToolchainLocations = [
        # First we should prefer toolchains shipped with this project
        os.path.join( sourcesPath, "toolchain/Android.cmake" ),
        # Next we  prefer a toolchain provided by the project dependencies
        os.path.join( installPath, "share/ECM/toolchain/Android.cmake" ),
        # As a final fallback use a toolchain baked into our SDK/Image
        "/opt/nativetooling/share/ECM/toolchain/Android.cmake",
    ]
    ecmToolchain = CommonUtils.firstPresentFile("/", ecmToolchainLocations)
    qt6Toolchain = "/home/user/android-arm-clang/lib/cmake/Qt6/qt.toolchain.cmake"

    # Now we make sure we found something (this should never happen)
    if ecmToolchain == "":
        print("## Unable to locate a suitable toolchain for this build!")
        print("## Aborting build - Android compilation requires use of an appropriate CMake toolchain to enable cross-compilation (please add a dependency on extra-cmake-modules)")
        sys.exit(1)

    # Determine whether we are in a Qt 6 or Qt 5 environment
    if os.path.exists( qt6Toolchain ):
        cmakeCommand.append("-DCMAKE_TOOLCHAIN_FILE=" + qt6Toolchain)
        cmakeCommand.append("-DQT_CHAINLOAD_TOOLCHAIN_FILE=" + ecmToolchain)
    else:
        cmakeCommand.append("-DCMAKE_TOOLCHAIN_FILE=" + ecmToolchain)

# Extra CMake arguments provided by the Gitlab template
if arguments.extra_cmake_args:
    # necessary since we cannot use the 'extend' action for the arguments due to requiring Python < 3.8
    flat_args = [item for sublist in arguments.extra_cmake_args for item in sublist]
    cmakeCommand.extend(flat_args)

if 'KDECI_EXTRA_CMAKE_ARGS' in os.environ:
    cmakeCommand.extend(os.environ['KDECI_EXTRA_CMAKE_ARGS'].split())

# Lucky last, we add the path to our sources
cmakeCommand.append( '"' + sourcesPath + '"' )

# Now glue it all together!
commandToRun = ' '.join( cmakeCommand )

# Run the command
try:
    print( "## RUNNING: " + commandToRun )
    subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=buildPath, env=buildEnvironment )
except Exception:
    print("## Failed to configure the project")
    sys.exit(1)

####
# Compile the project!!
####

beforeInstallTimestamp = datetime.datetime.now().timestamp()

# Determine the appropriate number of CPU cores we should use when running builds
cpuCount = int(multiprocessing.cpu_count())

makeCommand = "cmake --build . --parallel {cpuCount} --target {customTarget}"

# Finalise the command we will be running
commandToRun = makeCommand.format( cpuCount=cpuCount, maximumLoad=cpuCount+1, customTarget = buildTarget )

# Compile the project
try:
    print( "## RUNNING: " + commandToRun )
    subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=buildPath, env=buildEnvironment )
except Exception:
    print("## Failed to build the project")
    sys.exit(1)

####
# Run tests before installation if needed
####

if run_tests and configuration['Options']['test-before-installing']:
    # Run the tests!
    print("## RUNNING PROJECT TESTS")
    testResult = TestHandler.run( configuration, sourcesPath, buildPath, installPath, buildEnvironment )
    if not testResult and platform.matches(configuration['Options']['require-passing-tests-on']):
        print("## Tests failed")
        sys.exit(1)

####
# Install the project...
####

# Set the appropriate environment variables to ensure we can capture make install's output later on
buildEnvironment['DESTDIR'] = installStagingPath
buildEnvironment['INSTALL_ROOT'] = installStagingPath
buildEnvironment['KDECI_REAL_PREFIX_PATH'] = installPath

# Now determine the path we should be archiving
# Because we could potentially be running on Windows we have to ensure our second path has been converted to a suitable form
# This conversion is necessary as os.path.join can't handle the presence of drive letters in paths other than the first argument
pathToArchive = os.path.join( installStagingPath, CommonUtils.makePathRelative(installPath) )

makeCommand = "cmake --build . --target {customTarget}"
commandToRun = makeCommand.format(customTarget = installTarget)

# Install the project
try:
    print("## RUNNING: " + commandToRun)
    subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=buildPath, env=buildEnvironment )
except Exception:
    print("## Failed to install the project")
    sys.exit(1)

####
# Run post-install scripts
####

scriptsAllowed = None

if 'KDECI_POST_INSTALL_SCRIPTS_FILTER' in os.environ:
    scriptsAllowed = os.environ['KDECI_POST_INSTALL_SCRIPTS_FILTER'].split(';')

for name, script in configuration['PostInstallScripts'].items():

    if not scriptsAllowed is None and not name in scriptsAllowed:
        print('## Skipping script \"{}\" due to the filter active'.format(name))
        continue

    scriptEnvironment = copy.deepcopy(buildEnvironment)
    scriptEnvironment['KDECI_CACHE_PATH'] = localCachePath
    scriptEnvironment['KDECI_BUILD_TYPE'] = buildType
    scriptEnvironment['KDECI_INTERNAL_USE_CCACHE'] = str(useCcacheForBuilds)
    scriptEnvironment['KDECI_SOURCES_DIR'] = sourcesPath

    scriptEnvironment = EnvironmentHandler.addEnvironmentPrefix(pathToArchive, scriptEnvironment)

    if script.endswith('.py') and not (script.startswith('python ') or script.startswith('python3')):
        commandToRun = sys.executable + " " + os.path.join(sourcesPath, script)
    else:
        commandToRun = script if os.path.isabs(script) else os.path.join(sourcesPath, script)

    # Run post-install scripts
    try:
        print('## RUNNING POST-INSTALL SCRIPT \"{}\": {}'.format(name, commandToRun))
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=baseWorkDirectoryPath, env=scriptEnvironment )
    except Exception:
        print("## Failed to run post-install script the project")
        sys.exit(1)

leakedFiles = []

for root, dirs, files in os.walk(installPath):
    for name in files:
        filePath = os.path.join(root, name)
        fileTimeStamp = os.path.getctime(filePath)
        #print("file: {} timestamp: {}".format(filePath, fileTimeStamp))
        if fileTimeStamp > beforeInstallTimestamp:
            leakedFiles.append(filePath)

if leakedFiles:
    print("## ERROR: some files seem to have been installed bypassing the _staging directory ($DESTDIR environment variable)!")
    print("##  timestamp: {}".format(time.asctime(time.localtime(beforeInstallTimestamp))))
    for filePath in leakedFiles:
        print("##  leaked file: {}, {}".format(filePath, time.asctime(time.localtime(os.path.getctime(filePath)))))
    if arguments.fail_on_leaked_stage_files:
        print('## Exiting... (\'--fail-on-leaked-stage-files\' is set)')
        sys.exit(1)
    else:
        print('## Ignoring... (set \'--fail-on-leaked-stage-files\' to fail on leaked files)')

if configuration['Options']['pkg-config-sanity-check'] != 'none':
    commandToRun = '{} -u {} --prefix {} --destdir {} {}'.format(
        sys.executable,
        os.path.join(CommonUtils.scriptsBaseDirectory(), 'sanity-check-pkg-config-files.py'),
        installPath,
        installStagingPath,
        '-f' if configuration['Options']['pkg-config-sanity-check'] == 'error' else '')

    # Run pkg-config sanity checks
    try:
        print('## RUNNING PKG-CONFIG SANITY-CHECKS: {}'.format(commandToRun))
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=os.getcwd(), env=os.environ )
    except Exception:
        print("## Failed to run pkg-config sanity-check script")
        sys.exit(1)

if sys.platform == 'darwin':
    try:
        if configuration['Options']['macos-rpath-fix']:
            commandToRun = '{} {} --debug --prefix {} --destdir {}'.format(
                "zsh",
                os.path.join(CommonUtils.scriptsBaseDirectory(), 'macos-fix-rpath.sh'),
                installPath,
                installStagingPath)
            
            # Run macos-fix-rpath 
            try:
                print('## RUNNING MACOS-RPATH-FIX: {}'.format(commandToRun))
                subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=os.getcwd(), env=os.environ )
            except Exception:
                print("## Failed to run macOS rpath-fix script")
                sys.exit(1)
    except Exception:
        pass


# Cleanup the capture variables to ensure they don't interfere with later runs
del buildEnvironment['DESTDIR']
del buildEnvironment['INSTALL_ROOT']
del buildEnvironment['KDECI_REAL_PREFIX_PATH']

# Dump ccache stats if applicable
if useCcacheForBuilds:
    # Dump cache-hit stats
    subprocess.check_call( 'ccache -s {}'.format(ccacheVerboseArg), stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=sourcesPath, env=buildEnvironment )

####
# Capture the installation if needed and deploy the staged install to the final install directory
####

# We want to capture the tree as it is inside the install directory and don't want any trailing slashes in the archive as this isn't standards compliant
# Therefore we list everything in the install directory and add each of those to the archive, rather than adding the whole install directory
filesToInclude = os.listdir( pathToArchive )

# Copy the files into the installation directory
# This is so later tests can rely on the project having been installed
# While we ran 'make install' just before this didn't install it as we diverted the installation to allow us to cleanly capture it
for filename in filesToInclude:
    fullPath = os.path.join(pathToArchive, filename)
    print("Copying {} -> {}".format(fullPath, os.path.join(installPath, filename)))
    if os.path.isdir(fullPath):
        dstFullPath = os.path.join(installPath, filename)
        MergeFolders.merge_folders(fullPath, dstFullPath)
    else:
        shutil.copy2(fullPath, os.path.join(installPath, filename))

# Are we supposed to be publishing this particular package to the archive?
if (gitlabToken is not None or arguments.publish_to_cache) and not arguments.skip_publishing:
    # Create a temporary file, then open the file as a tar archive for writing
    # We don't want it to be deleted as storePackage will move the archive into it's cache
    archiveFile = tempfile.NamedTemporaryFile(delete=False)
    archive = tarfile.open( fileobj=archiveFile, mode='w' )

    # Add all the files which need to be in the archive into the archive
    for filename in filesToInclude:
        fullPath = os.path.join(pathToArchive, filename)
        archive.add( fullPath, arcname=filename, recursive=True )

    # Close the archive, which will write it out to disk, finishing what we need to do here
    archive.close()
    archiveFile.close()

    # With the archive being generated, we can now prepare some metadata...
    packageMetadata = {
        'dependencies': projectBuildDependencies,
        'runtime-dependencies': projectRuntimeDependencies
    }

    if gitlabToken is not None:
        # Grab the Git revision (SHA-1 hash) we are building
        # This is always present in Gitlab CI builds
        gitRevision = os.environ['CI_COMMIT_SHA']

        print('## Publishing package: {} branch: {} sha1: {}'.format(arguments.project, arguments.branch, gitRevision))
        print('##    metadata: {}'.format(packageMetadata))

        # Publish our package to the registry
        packageRegistry.upload(archiveFile.name, arguments.project, arguments.branch, gitRevision, packageMetadata)

    if arguments.publish_to_cache:
        packageNameFile = '{}-{}.tar'.format(arguments.project, arguments.branch)
        packageMetadataFile = '{}-{}.json'.format(arguments.project, arguments.branch)

        normalisedBranch = packageRegistry._normaliseBranchName(arguments.branch)

        packageTimestamp = int( os.path.getmtime(archiveFile.name) )
        versionForGitlab = "{0}-{1}".format(normalisedBranch, packageTimestamp)

        gitRevision = os.environ.get('CI_COMMIT_SHA', 'unknown')
        fullPackageMetadata = packageRegistry.generateMetadata(archiveFile.name, arguments.project, arguments.branch, gitRevision, packageMetadata)

        print('## Copying package to chache: {} branch: {}'.format(arguments.project, arguments.branch))
        print('##    metadata: {}'.format(fullPackageMetadata))
        print('##    package file: {}'.format(packageNameFile))
        print('##    location: {}'.format(localCachePath))

        shutil.copy2(archiveFile.name, os.path.join(localCachePath, packageNameFile))
        with open(os.path.join(localCachePath, packageMetadataFile), 'w') as f:
            f.write(json.dumps(fullPackageMetadata, indent = 4))

    # Cleanup the temporary archive file as it is no longer needed
    os.remove( archiveFile.name )

if removeInstallFoldersAfterBuild:
    print('## Removing install folder: {}'.format(installPath))
    shutil.rmtree(installPath)
    print('## Removing staging folder: {}'.format(installStagingPath))
    shutil.rmtree(installStagingPath)

# If this is a build only run then bail here
if arguments.only_build:
    sys.exit(0)

####
# Retrieve runtime dependencies if they are needed, and rebuild our environment
####

# Now we can retrieve the build time dependencies
dependenciesToUnpack = packageRegistry.retrieveDependencies( projectRuntimeDependencies, runtime=True )
# And then unpack them
for packageContents, packageMetadata, cacheStatus in dependenciesToUnpack:
    # Open the archive file
    archive = tarfile.open( name=packageContents, mode='r' )
    # Extract it's contents into the install directory
    archive.extractall( path=installPath )

# Regenerate our environment in case the newly installed software uses directories previously not used
buildEnvironment = EnvironmentHandler.generateFor( installPrefix=installPath )

# Apply any environment changes from our configuration as well
for key, value in configuration['Environment'].items():
    # Apply each key in turn
    buildEnvironment[ key ] = value

####
# Run tests if we didn't do that already
####

if run_tests and not configuration['Options']['test-before-installing']:
    # Run the tests!
    print("## RUNNING PROJECT TESTS")
    testResult = TestHandler.run( configuration, sourcesPath, buildPath, installPath, buildEnvironment )
    requirePassingTestsOn = configuration['Options']['require-passing-tests-on']
    if not testResult and platform.matches(requirePassingTestsOn):
        print("## Tests failed")
        sys.exit(1)

####
# Extract test coverage results for processing by Gitlab 
####

# If we aren't running on Linux then we skip this, as we consider that to be the canonical platform for code coverage...
# Additionally, as coverage information requires tests to have been run, skip extracting coverage information if tests have been disabled
if run_tests and useCoverageBuild:
    # Determine the command we need to run
    # We ask GCovr to exclude the build directory by default as we don't want generated artifacts (like moc files) getting included as well
    # Sometimes projects will want to customise things slightly so we provide for that as well
    commandToRun = 'gcovr --txt --xml "CoberturaLcovResults.xml" --exclude "_build/.*" --root "{sources}" {otherArguments}'
    commandToRun = commandToRun.format( sources=sourcesPath, otherArguments=configuration['Options']['gcovr-arguments'] )

    # Now run it!
    # If gcovr bails we ignore it, as failures to extract lcov results shouldn't cause builds to fail.
    try:
        print("## RUNNING: " + commandToRun)
        subprocess.check_call( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=buildEnvironment )
    except Exception:
        pass

####
# Run complete!
####

print("## CI Run Completed Successfully!")
sys.exit(0)
