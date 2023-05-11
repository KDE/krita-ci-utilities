import os
import re
import sys
import stat
import time
import subprocess
import multiprocessing
from lxml import etree
from components import CommonUtils

import copy

def run( projectConfig, sourcesPath, buildPath, installPath, buildEnvironment ):
    # On Windows, we need to pull bin\data\ over from the Craft prefix to ensure resources in it can be found by QStandardPaths
    # This is a bit of a hack, but there isn't much we can do here as Qt doesn't give us any means of telling it to look elsewhere
    # Craft includes patches to Qt that help us workaround this on macOS but unfortunately those aren't applied on Windows so this is still needed there
    if sys.platform == 'win32' and 'CRAFT_ROOT' in os.environ:
        # Determine where Craft is...
        craftRoot = os.path.realpath( os.environ['CRAFT_ROOT'] )
        sourceDirectory = os.path.join( craftRoot, 'bin\data' )
        # Determine where we want to deploy these files to
        destinationDirectory = os.path.join( buildPath, 'bin\data' )
        # Do the copy!
        CommonUtils.recursiveDirectoryCopy( sourceDirectory, destinationDirectory )

    # Get a count of the number of available tests
    # This relies on the command "ctest -N" producing at least one line that matches "Total Tests: x" where x is the number of tests
    process = subprocess.Popen( "ctest -N", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, env=buildEnvironment, cwd=buildPath)
    stdout, stderr = process.communicate()
    testsFound = int( re.search( b'Total Tests: ([0-9]+)', stdout, re.MULTILINE ).group(1) )

    # If we had less than 1 test then there is nothing for us to do - bail
    if testsFound == 0:
        return True

    # Looks like we have some tests to run
    # Before we can get started, we should make sure the environment is ready for use
    # On Linux/*BSD systems we need to make sure XDG_RUNTIME_DIR is set as lots of tools are reliant on it being set and existing
    if sys.platform != 'win32' and sys.platform != 'darwin':
        # Set it in the environment
        buildEnvironment['XDG_RUNTIME_DIR'] = os.path.join('/tmp/runtime-kdeci/', buildEnvironment['CI_JOB_ID'])
        # And make sure it exists
        if not os.path.exists( buildEnvironment['XDG_RUNTIME_DIR'] ):
            # Create it!
            os.makedirs( buildEnvironment['XDG_RUNTIME_DIR'] )
            # And lock down it's permissions
            # This is needed to keep Wayland happy otherwise it won't work
            os.chmod( buildEnvironment['XDG_RUNTIME_DIR'], stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR )

    # Are we being asked to ensure ASAN is forcibly injected?
    # On FreeBSD their ASAN is different - it behaves properly
    # So we only need to force inject on Linux
    if sys.platform =='linux' and projectConfig['Options']['force-inject-asan']:
        # Where could the ASAN library live?
        knownAsanLocations = [
                '/lib64/',
                '/usr/lib64/',
                '/usr/lib/x86_64-linux-gnu/'
        ]
        # And what names could it be hiding under?
        knownAsanNames = [
                'libasan.so.4',
                'libasan.so.3',
                'libasan.so.2'
        ]
        # Knowing all of that, let's find ASAN's library and set it up to be injected
        buildEnvironment['LD_PRELOAD'] = CommonUtils.firstPresentFileInPaths( knownAsanLocations, knownAsanNames )

    # We want Qt to be noisy about debug output to make debugging tests easier
    # Some stuff is so verbose it hits the testlib maxwarnings limits though
    buildEnvironment['QT_LOGGING_RULES'] = "*.debug=true;qt.text.font.db=false;kf.globalaccel.kglobalacceld=false;kf.wayland.client=false"
    # We want to force Qt to print to stderr, even on Windows
    buildEnvironment['QT_LOGGING_TO_CONSOLE'] = '1'
    buildEnvironment['QT_FORCE_STDERR_LOGGING'] = '1'
    # Always use software libgl instead of hardware
    buildEnvironment['LIBGL_ALWAYS_SOFTWARE'] = 'true'
    # We also want Mesa to tell us what it's doing
    # This makes it much easier to debug tests which are dependent on 3D stuff
    buildEnvironment['EGL_LOG_LEVEL'] = 'debug'
    buildEnvironment['LIBGL_DEBUG'] = 'verbose'
    buildEnvironment['MESA_DEBUG'] = '1'
    # We also want CMake to be noisy when tests fail
    buildEnvironment['CTEST_OUTPUT_ON_FAILURE'] = '1'

    # Cleanup the builder if needed
    if sys.platform == 'freebsd12' or sys.platform == 'freebsd13':
        subprocess.call("killall -9 dbus-daemon kded5 kioslave klauncher kdeinit5 kiod openbox Xvfb kscreenlocker_greet lldb", shell=True)
        if os.path.exists('/tmp/.X90-lock'):
            os.remove('/tmp/.X90-lock')
        if os.path.exists('/tmp/.X11-unix/X90'):
            os.remove('/tmp/.X11-unix/X90')

    # when the project uses its own harfbuzz, it may interfere with
    # the one used in the system packages, so remove our installation
    # library path from the search path for the system tools
    systemToolsEnvironment = copy.deepcopy(buildEnvironment)
    del systemToolsEnvironment['LD_LIBRARY_PATH']

    # Spawn a X windowing system if needed
    # We'll also launch a Window Manager at the same time as some tests often need or unknowingly rely on one being present
    # As X doesn't belong on Windows or macOS we don't run it there
    if projectConfig['Options']['setup-x-environment'] and ( sys.platform != 'win32' and sys.platform != 'darwin' ):
        # Setup Xvfb
        systemToolsEnvironment['DISPLAY'] = ':90'
        buildEnvironment['DISPLAY'] = ':90'
        commandToRun = "Xvfb :90 -ac -screen 0 1600x1200x24+32"
        xvfbProcess = subprocess.Popen( commandToRun, stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT, shell=True, env=systemToolsEnvironment )

        # Give Xvfb a few moments to get on it's feet
        time.sleep( 5 )

        # Startup a Window Manager
        commandToRun = "openbox"
        wmProcess = subprocess.Popen( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=systemToolsEnvironment )

    # Spawn D-Bus if needed
    # Same rules apply for X in regards to Windows and macOS - it doesn't belong so we don't support it
    if projectConfig['Options']['setup-dbus-session'] and ( sys.platform != 'win32' and sys.platform != 'darwin' ):
        # Determine the command to run, then launch it and wait for it to exit
        commandToRun = 'dbus-launch'
        process = subprocess.Popen( commandToRun, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=systemToolsEnvironment )
        process.wait()
        # Determine what environment variables need to be set, and ensure those are included in our build environment
        for variable in process.stdout:
            variable  = str(variable, 'utf-8')
            splitVars = variable.split('=', 1)
            buildEnvironment[ splitVars[0] ] = splitVars[1].strip()

    # Do we need to run update-mime-database?
    # First we need to determine what mime directory we will have
    # On most platforms this will be $prefix/share/mime
    mimeDirectory = os.path.realpath( os.path.join( installPath, 'share', 'mime' ) )
    # Except on Windows... where it is bin/data/mime/
    if sys.platform == 'win32':
        mimeDirectory = os.path.realpath( os.path.join( installPath, 'bin', 'data', 'mime' ) )

    # Make sure the mime directory exists - otherwise there is no point to running update-mime-database
    if os.path.exists( mimeDirectory ):
        # Let's run update-mime-database
        commandToRun = 'update-mime-database "' + mimeDirectory + '"'
        process = subprocess.Popen( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=buildEnvironment )
        process.wait()

    # KDE Tests often need kdeinit running, in order to have klauncher, kded, etc available so let's spawn those now
    # This is the case regardless of the platform
    commandToRun = 'kdeinit5'
    try:
        kdeinitProcess = subprocess.Popen( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, env=buildEnvironment )
    except OSError:
        pass

    # As some of the above might still be getting themselves ready, wait for a few moments...
    time.sleep( 5 )

    # Does this project have load sensitive tests?
    # Running tests for KWin while load is high on the system pretty much always results in tests failing
    # We therefore check the system load before continuing to the actual test execution
    while projectConfig['Options']['tests-load-sensitive'] and sys.platform != 'win32' and sys.platform != 'darwin':
        # Grab the current system load
        load1, load5, load15 = os.getloadavg()
        # Check to see if it's low enough for us
        if load1 < 2 and load5 < 2:
            break

        # Otherwise sleep for a few seconds and try again
        time.sleep( 5 )

    # Do we need to run CTest with multiple parallel jobs?
    cpuCount = 1
    if projectConfig['Options']['tests-run-in-parallel']:
        cpuCount = int(multiprocessing.cpu_count())

    # Now it's time to invoke CTest! Build up the command...
    commandToRun = "ctest -T Test --output-on-failure --no-compress-output --test-output-size-passed 1048576 --test-output-size-failed 1048576 -j {cpuCount} --timeout {timeLimit} {additionalCTestArguments}"
    commandToRun = commandToRun.format(
        cpuCount=cpuCount,
        timeLimit=projectConfig['Options']['per-test-timeout'],
        additionalCTestArguments=projectConfig['Options']['ctest-arguments']
    )

    # And run it!
    print( "## RUNNING: " + commandToRun )
    ctestProcess = subprocess.Popen( commandToRun, stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=buildPath, env=buildEnvironment )
    ctestProcess.wait()

    # Now that CTest is done, we convert it's output to JUnit format
    junitOutput = convertCTestResultsToJUnit( buildPath )
    junitFilename = os.path.join( sourcesPath, 'JUnitTestResults.xml' )
    with open(junitFilename, 'w', encoding='UTF-8') as junitFile:
        junitFile.write( str(junitOutput) )

    # To ensure we don't hang, cleanup the Window Manager and X server if needed
    if projectConfig['Options']['setup-x-environment'] and ( sys.platform != 'win32' and sys.platform != 'darwin' ):
        wmProcess.terminate()
        xvfbProcess.terminate()

    # Finally, we do some last cleanup
    # This is particularly relevant on FreeBSD and Windows where the slaves are permanent
    # We wait around on Windows before trying to kill off kioslave.exe as it likes to get into a weird state and not die
    if sys.platform == 'win32':
        subprocess.call("taskkill /f /T /im kded5.exe", shell=True)
        subprocess.call("taskkill /f /T /im klauncher.exe", shell=True)
        subprocess.call("taskkill /f /T /im kdeinit5.exe", shell=True)
        subprocess.call("taskkill /f /T /im dbus-daemon.exe", shell=True)
        time.sleep( 30 )
        subprocess.call("taskkill /f /T /im kioslave.exe", shell=True)
        subprocess.call("taskkill /f /T /im kioslave5.exe", shell=True)
        subprocess.call("taskkill /f /T /im vctip.exe", shell=True)

    if sys.platform == 'freebsd12' or sys.platform == 'freebsd13':
        subprocess.call("killall -9 dbus-daemon kded5 kioslave klauncher kdeinit5 kiod openbox Xvfb lldb", shell=True)

    # All done!
    return ctestProcess.returncode == 0

def convertCTestResultsToJUnit( buildDirectory ):
    # Where is the base prefix for all test data for this project located?
    testDataDirectory = os.path.join( buildDirectory, 'Testing' )

    # Determine where we will find the test run data for the latest run
    filename = os.path.join( testDataDirectory, 'TAG' )
    with open(filename, 'r') as tagFile:
        testDirectoryName = tagFile.readline().strip()

    # Open the test result XML and load it
    filename = os.path.join( testDataDirectory, testDirectoryName, 'Test.xml' )
    with open(filename , 'r', encoding='UTF-8') as xmlFile:
        xmlDocument = etree.parse( xmlFile )

    # Load the XSLT file
    filename = os.path.join( CommonUtils.scriptsBaseDirectory(), 'resources', 'ctesttojunit.xsl' )
    with open(filename, 'r') as xslFile:
        xslContent = xslFile.read()
        xsltRoot = etree.XML(xslContent)

    # Transform the CTest XML into JUnit XML
    transform = etree.XSLT(xsltRoot)
    return transform(xmlDocument)
