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
        return ('export {saved}=\"${var}\"\n'.format(saved = savedVariableName, var = var),
                'export {var}=\"${saved}\"\nunset {saved}\n'.format(saved = savedVariableName, var = var))
    
def getVarSetterLine(var, value):
    if platform.system() == "Windows":
        return 'set {}={}\n'.format(var, value)
    else:
        return 'export {}=\"{}\"\n'.format(var, value)

def getVarUpdaterLine(var, values):
    if not isinstance(values, list):
        raise('The argument must be a list')
    
    if platform.system() == "Windows":
        return 'set {var}={value};%{var}%\n'.format(var=var, value=';'.join(values))
    else:
        return 'export {var}={value}:${var}\n'.format(var=var, value=':'.join(values))

def getScriptLine(script):
    if platform.system() == "Windows":
        return 'call {}\n'.format(os.path.abspath(script))
    else:
        return '. {}\n'.format(os.path.abspath(script))

def writeEnvFile(directory, fileBaseName, environmentUpdate, environmentAppend = {}, extraActivationScripts = [], extraDeactivationScripts = []):
    if platform.system() == "Windows" and fileBaseName.endswith('.bat'):
        raise("Env file base name must not include the OS-specific suffix: {}".format(fileBaseName))

    if platform.system() != "Windows":
        promptModificationScript="""
NEW_PROMPT="({environmentName}) "

if [[ -n $VIRTUAL_ENV_PROMPT ]] && grep $VIRTUAL_ENV_PROMPT <<< $PS1 > /dev/null; then
    NEW_PS1=$(sed -e "s/$VIRTUAL_ENV_PROMPT/$NEW_PROMPT/" <<< $PS1)
    export VIRTUAL_ENV_PROMPT=$NEW_PROMPT
    export PS1=$NEW_PS1
else
    export VIRTUAL_ENV_PROMPT=$NEW_PROMPT
    export PS1="$NEW_PROMPT$PS1"
fi
        """
    else:
        promptModificationScript="""
@echo off
setlocal enableextensions enabledelayedexpansion

set "NEW_PROMPT_PREFIX=({environmentName}) "

if %NEW_PROMPT_PREFIX% == %VIRTUAL_ENV_PROMPT% (
    exit /b 0
)

if not "%VIRTUAL_ENV_PROMPT%" == "" (
    set "NEW_PROMPT=!PROMPT:%VIRTUAL_ENV_PROMPT%=%NEW_PROMPT_PREFIX%!"

    if not !NEW_PROMPT! == !PROMPT! (
        @rem do nothing
    ) else (
        set "NEW_PROMPT=%NEW_PROMPT_PREFIX%%PROMPT%"
    )
) else (
    set "NEW_PROMPT=%NEW_PROMPT_PREFIX%%PROMPT%"
)

endlocal & SET "PROMPT=%NEW_PROMPT%" & set "VIRTUAL_ENV_PROMPT=%NEW_PROMPT_PREFIX%"
        """
    promptModificationScript = promptModificationScript.format(
        environmentName = os.path.basename(directory))

    fileSuffix = '.bat' if platform.system() == "Windows" else ''

    varsToSave = list(environmentUpdate.keys())
    if environmentAppend:
        varsToSave.extend(environmentAppend.keys())

    varsToSave.append('KDECI_ENV_ACTIVATION_SCRIPT')
    varsToSave.append('KDECI_ENV_DEACTIVATION_SCRIPT')

    if not 'VIRTUAL_ENV_PROMPT' in varsToSave:
        varsToSave.append('VIRTUAL_ENV_PROMPT')
    if platform.system() != "Windows":
        if not 'PS1' in varsToSave:
            varsToSave.append('PS1')
    else:
        if not 'PROMPT' in varsToSave:
            varsToSave.append('PS1')

    saveLines = []
    restoreLines = []

    for var in varsToSave:
        save, restore = getSaveResotreVarLine(var)
        saveLines.append(save)
        restoreLines.append(restore)

    activationScript = os.path.abspath(os.path.join(directory, fileBaseName + fileSuffix))
    deactivationScript = os.path.abspath(os.path.join(directory, fileBaseName + '_deactivate' + fileSuffix))

    with open(activationScript, 'w') as envFile:
        if platform.system() == "Windows":
            envFile.write('@echo off\n')
        
        envFile.writelines(saveLines)

        envFile.write(getVarSetterLine('KDECI_ENV_ACTIVATION_SCRIPT', activationScript))
        envFile.write(getVarSetterLine('KDECI_ENV_DEACTIVATION_SCRIPT', deactivationScript))

        for var, value in environmentUpdate.items():
            envFile.write(getVarSetterLine(var, value))
        for var, value in environmentAppend.items():
            envFile.write(getVarUpdaterLine(var, value))
        for script in extraActivationScripts:
            envFile.write(getScriptLine(os.path.abspath(script)))

        envFile.write(promptModificationScript)

    with open(deactivationScript, 'w') as envFile:
        if platform.system() == "Windows":
            envFile.write('@echo off\n')

        for script in extraDeactivationScripts:
            envFile.write(getScriptLine(os.path.abspath(script)))
        envFile.writelines(restoreLines)
