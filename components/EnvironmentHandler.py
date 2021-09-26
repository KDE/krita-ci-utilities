import os
import sys
import copy
import collections

# Module which handles everything to do with environment variables in relation to builds

# Method which determines the appropriate environment variables to set for builds
# This ensures that build systems and running tests can find the dependencies located within it
def generateFor( installPrefix ):
    # Create our initial store for environment changes
    envChanges = collections.defaultdict(list)

    # We always check the install prefix we've been given - so let's look there first
    envChanges = changesForPrefix( os.path.realpath( installPrefix ), envChanges )

    # Are we on Windows?
    if sys.platform == 'win32' and 'CRAFT_ROOT' in os.environ:
        # Then we need to consider Craft...
        # Grab our Craft Root directory
        craftRoot = os.path.realpath(os.environ['CRAFT_ROOT'])
        # Process the base directory first
        envChanges = changesForPrefix( craftRoot, envChanges )
        # As well as it's dev-utils directory (why it's split up like this - no clue...)
        utilsPrefix = os.path.join( craftRoot, 'dev-utils' )
        envChanges = changesForPrefix( utilsPrefix, envChanges )

    # Are we performing an Android build?
    if 'ANDROID_HOME' in os.environ and sys.platform == 'linux':
        # Then we need to include the separate Qt SDK for Android
        # Grab it's directory
        envChanges = changesForPrefix( '/opt/Qt', envChanges )
        # We also need to include other dependencies which are shipped in the Docker SDK image
        envChanges = changesForPrefix( '/opt/kdeandroid-arm', envChanges )
        envChanges = changesForPrefix( '/opt/kdeandroid-arm64', envChanges )

    # Otherwise are we on a Non-Windows / Mac platform?
    elif sys.platform != 'win32' and sys.platform != 'darwin':
        # The we need to consider the system install prefix
        # Normally these would be setup for us, but this is just to be absolutely sure everything is right
        envChanges = changesForPrefix( "/usr/", envChanges, systemPrefix=True )
        # We should also consider /usr/local/ as FreeBSD uses this as a system prefix quite extensively
        envChanges = changesForPrefix( "/usr/local/", envChanges, systemPrefix=True )

    # On FreeBSD LLVM gets installed to it's own separate prefix
    # Make sure that is included too
    elif sys.platform == 'freebsd12':
        # Include the necessary LLVM path then
        envChanges = changesForPrefix( "/usr/local/llvm90", envChanges, systemPrefix=True )

    # Now we can merge this into the real environment
    splitChar = separatorCharacter()
    clonedEnv = copy.deepcopy(os.environ)
    for variableName, variableEntries in envChanges.items():
        # Join them
        newEntry = splitChar.join( variableEntries )
        # If the variable already exists in the system environment, we prefix ourselves on
        if variableName in clonedEnv:
            newEntry = '%s%s%s' % (newEntry, splitChar, clonedEnv[variableName])
        # Set the variable into our cloned environment
        clonedEnv[variableName] = newEntry

    # If we're on Windows or MacOS, then setting XDG_DATA_DIRS will have no effect whatsoever
    # Fortunately, even though Qt Upstream doesn't support this, the Craft patched version of Qt does support the QT_DATA_DIRS variable which will be followed
    # To ensure all our resources can be found, we make sure QT_DATA_DIRS is set
    # We leave XDG_DATA_DIRS set to ensure any tools which haven't been adapted to the Windows/Mac environment continue to work
    if sys.platform == 'win32' or sys.platform == 'darwin':
        clonedEnv['QT_DATA_DIRS'] = clonedEnv['XDG_DATA_DIRS']

    # Qt needs hand holding in order to work properly
    # We only do this if we are in a Qt 5 environment which we determine by the absence of a Qt 4 environment
    if sys.platform != 'win32' and not os.path.exists('/usr/bin/qmake-qt4'):
        clonedEnv['QT_SELECT'] = 'qt5'

    # If this is a Linux/FreeBSD system, making sure we're going to have a UTF-8 environment
    if sys.platform == 'linux' or sys.platform == 'freebsd12':
        clonedEnv['LANG'] = 'en_US.UTF-8'

    # Mark ourselves as a KDE session, for things like the platform plugin, etc.
    clonedEnv['XDG_CURRENT_DESKTOP'] = 'KDE'
    # Make sure ASAN doesn't get in the way
    clonedEnv['ASAN_OPTIONS'] = "detect_leaks=0:new_delete_type_mismatch=0:detect_odr_violation=0:stack-use-after-scope=0:alloc_dealloc_mismatch=0"

    # On FreeBSD we also want ASAN to be symbolised to aid in debugging
    # Additionally, we disable container overflow detection, as this seems to have generated false positives on FreeBSD
    if sys.platform == 'freebsd12':
        clonedEnv['ASAN_OPTIONS'] = "detect_leaks=0:new_delete_type_mismatch=0:detect_odr_violation=0:stack-use-after-scope=0:alloc_dealloc_mismatch=0:detect_container_overflow=0:symbolize=1"
        clonedEnv['ASAN_SYMBOLIZER_PATH'] = '/usr/local/bin/llvm-symbolizer'

    # All done
    return clonedEnv

def changesForPrefix( installPrefix, envChanges, systemPrefix=False ):
    # Setup CMAKE_PREFIX_PATH
    extraLocation = os.path.join( installPrefix )
    if os.path.exists( extraLocation ):
        envChanges['CMAKE_PREFIX_PATH'].append( extraLocation )

    # Setup PATH
    extraLocation = os.path.join( installPrefix, 'bin' )
    if os.path.exists( extraLocation ) and not systemPrefix:
        envChanges['PATH'].append(extraLocation)

    # Handle those paths which involve $prefix/lib*
    for libraryDirName in ['lib', 'lib32', 'lib64', 'lib/x86_64-linux-gnu', 'libdata']:
        # Do LD_LIBRARY_PATH
        extraLocation = os.path.join( installPrefix, libraryDirName )
        if os.path.exists( extraLocation ) and not systemPrefix:
            envChanges[ libraryPathVariableName() ].append(extraLocation)

        # Now do PKG_CONFIG_PATH
        extraLocation = os.path.join( installPrefix, libraryDirName, 'pkgconfig' )
        if os.path.exists( extraLocation ):
            envChanges['PKG_CONFIG_PATH'].append(extraLocation)

        # Next up is QT_PLUGIN_PATH
        for pluginDirName in ['plugins', 'qca-qt5']:
            extraLocation = os.path.join( installPrefix, libraryDirName, pluginDirName )
            if os.path.exists( extraLocation ):
                envChanges['QT_PLUGIN_PATH'].append(extraLocation)

        # Now we do QML2_IMPORT_PATH
        extraLocation = os.path.join( installPrefix, libraryDirName, 'qml' )
        if os.path.exists( extraLocation ):
            envChanges['QML2_IMPORT_PATH'].append(extraLocation)

    # Special Case for QT_PLUGIN_PATH and QML2_IMPORT_PATH
    # On Windows these are installed to $prefix/bin/$pluginDirName rather than under $prefix/lib/$pluginDirName
    if sys.platform == 'win32':
        # Check QT_PLUGIN_PATH first
        for pluginDirName in ['plugins', 'qca-qt5']:
            extraLocation = os.path.join( installPrefix, 'bin', pluginDirName )
            if os.path.exists( extraLocation ):
                envChanges['QT_PLUGIN_PATH'].append(extraLocation)

        # Now we do QML2_IMPORT_PATH
        extraLocation = os.path.join( installPrefix, 'bin', 'qml' )
        if os.path.exists( extraLocation ):
            envChanges['QML2_IMPORT_PATH'].append(extraLocation)

    # Setup XDG_DATA_DIRS - used to ensure applications on XDG platforms find their resources
    extraLocation = os.path.join( installPrefix, 'share' )
    if os.path.exists( extraLocation ):
        envChanges['XDG_DATA_DIRS'].append(extraLocation)

    # Setup XDG_CONFIG_DIRS - needed to ensure XDG based applications find their configuration
    extraLocation = os.path.join( installPrefix, 'etc/xdg' )
    if os.path.exists( extraLocation ):
        envChanges['XDG_CONFIG_DIRS'].append(extraLocation)

    # Setup QMAKEFEATURES
    # This mostly undocumented environment variable lets QMake find *.pri files which are outside Qt's install prefix
    extraLocation = os.path.join( installPrefix, 'mkspecs/features' )
    if os.path.exists( extraLocation ):
        envChanges['QMAKEFEATURES'].append( extraLocation )

    return envChanges

# Which character should be used as a separator for paths?
def separatorCharacter():
    # Are we on Windows?
    if sys.platform == 'win32':
        # Then semi-colon it is
        return ';'

    # Everything else uses a full colon
    return ':'

# Which environment variable is used to influence the loading of libraries?
def libraryPathVariableName():
    # Are we on OS X?
    if sys.platform == 'darwin':
        # OS X with System Integrity Protection does not support this at all - it will be unset when calling any system binary (incl. shell interpreters)
        # The variable is DYLD_LIBRARY_PATH, but considering it will only be passed through sometimes, we may as well not bother with setting it
        return 'IGNORE_THIS_VARIABLE'

    # Are we on Windows?
    elif sys.platform == 'win32':
        # Windows uses PATH for this - interesting choice Microsoft...
        return 'PATH'

    # Everything else (Linux, FreeBSD, etc) uses LD_LIBRARY_PATH for this
    return 'LD_LIBRARY_PATH'
