import os
import platform

def getSaveResotreVarLine(var):
    counter = 0
    savedVariableName = '__OLD_{}'.format(var)
    while True:
        if not savedVariableName in os.environ:
            break
        counter = counter + 1
        savedVariableName = '__OLD{}_{}'.format(counter, var)

    if platform.system() == "Windows":
        return ('set {saved}=%{var}%\n'.format(saved = savedVariableName, var = var),
                'set {var}=%{saved}%\n'.format(saved = savedVariableName, var = var))
    else:
        return ('export {saved}=${var}\n'.format(saved = savedVariableName, var = var),
                'export {var}=${saved}\n'.format(saved = savedVariableName, var = var))
    
def getVarSetterLine(var, value):
    if platform.system() == "Windows":
        return 'set {}={}\n'.format(var, value)
    else:
        return 'export {}={}\n'.format(var, value)

def getVarUpdaterLine(var, values):
    if not isinstance(values, list):
        raise('The argument must be a list')
    
    if platform.system() == "Windows":
        return 'set {var}={value};%{var}%\n'.format(var=var, value=';'.join(values))
    else:
        return 'export {var}={value}:${var}\n'.format(var=var, value=':'.join(values))

def getScriptLine(script):
    if platform.system() == "Windows":
        return '{}\n'.format(os.path.abspath(script))
    else:
        return '. {}\n'.format(os.path.abspath(script))

def writeEnvFile(directory, fileBaseName, environmentUpdate, environmentAppend = {}, extraActivationScripts = [], extraDeactivationScripts = []):
    if platform.system() == "Windows" and fileBaseName.endswith('.bat'):
        raise("Env file base name must not include the OS-specific suffix: {}".format(fileBaseName))
    
    fileSuffix = '.bat' if platform.system() == "Windows" else ''

    varsToSave = list(environmentUpdate.keys())
    if environmentAppend:
        varsToSave.extend(environmentAppend.keys())

    saveLines = []
    restoreLines = []

    for var in varsToSave:
        save, restore = getSaveResotreVarLine(var)
        saveLines.append(save)
        restoreLines.append(restore)

    with open(os.path.join(directory, fileBaseName + fileSuffix), 'w') as envFile:
        if platform.system() == "Windows":
            envFile.write('@echo off\n')
        
        envFile.writelines(saveLines)

        for var, value in environmentUpdate.items():
            envFile.write(getVarSetterLine(var, value))
        for var, value in environmentAppend.items():
            envFile.write(getVarUpdaterLine(var, value))
        for script in extraActivationScripts:
            envFile.write(os.path.abspath(script))

    with open(os.path.join(directory, fileBaseName + '_deactivate' + fileSuffix), 'w') as envFile:
        if platform.system() == "Windows":
            envFile.write('@echo off\n')

        for script in extraDeactivationScripts:
            envFile.write(getScriptLine(script))
        envFile.writelines(restoreLines)
