#!/usr/bin/env zsh
#
# Convert absolute rpath values to relative
#

# we depend on zsh modules, exit if not run with zsh
# this should not be a problem as zsh is standard on macOS
if [[ -z ${ZSH_VERSION} ]]; then
    echo "This script cannot be run using sh, use zsh."
    echo "exiting..."
    exit 1
fi

# NOTE: framework -id must include @rpath/pathframework/to/file
# NOTE: loader_path from libFile dir to relative lib directory
# NOTE: executable_path from binFile dir to relative lib directory

# NOTE: library not relative, but from base rpath to file ${fname##*lib/}

# Debug helper function
fn_script_debug() {
    echo "macos-rpath-subcmd: ${@}"
    ${@}
}

# get relative path of 1 to 2
perl_abs2rel() {
    perl -le 'use File::Spec; print File::Spec->abs2rel(@ARGV)' "${1}" "${2}"
}

# fixes rpath for all binary files given
# VARS
# global: installPath
fix_rpath () {
    for libFile in "${@}"; do
        if [[ -z "$(file ${libFile} | grep 'Mach-O')" ]]; then
            continue
        fi

        SharedLibs=($(otool -L "${libFile}" | awk 'BEGIN { arch = 0 } {    
            if ( !(pos = index($0,"architecture")) > 0 ) {
                if ( (pos = index($1,"@") == 0) ) {
                    print $1
                }
            } else {
                arch++
            }
            if ( arch > 1 ) {
                exit
            }
        } END {}'))

        installLibraryPath=${libFile#${installStagingPath}}
        installLibraryDir=$(dirname ${installLibraryPath})
        relativeToRPath=$(perl_abs2rel "${installPath}/lib" "${installLibraryDir}")
        relativeFromRPath=$(perl_abs2rel "${installLibraryPath}" "${installPath}/lib")
        libraryId=$(objdump --macho --dylib-id ${libFile} | grep -v "${libFile}:")
        if [[ -n ${SCRIPT_DEBUG} ]]; then
            echo "==="
            echo "libFile: ${libFile}"
            echo "installLibraryPath: ${installLibraryPath}"
            echo "relativeToRPath: ${relativeToRPath}"
            echo "relativeFromRPath: ${relativeFromRPath}"
            echo "libraryId: ${libraryId}"
        fi

        if [[ -n ${libraryId} ]]; then
            ${SCRIPT_DEBUG} install_name_tool -id "@rpath/${relativeFromRPath}" "${libFile}"
        fi

        ${SCRIPT_DEBUG} install_name_tool -delete_rpath "${installPath}/lib" "${libFile}" 2> /dev/null
        ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path/${relativeToRPath} "${libFile}" 2> /dev/null

        installPrefixes=${installPath}
        
        for lib in ${SharedLibs[@]}; do
            depInstallPath=${lib#${installStagingPath}}
            depInstallDir=$(dirname ${depInstallPath})
            if [[ ${depInstallDir} =~ .*"_build/bootstrap_prefix" ]]; then
                depInstallPath=${installPath}/${depInstallDir#*"_build/bootstrap_prefix/"}/$(basename ${lib})
            fi

            depRelativeFromRPath=$(perl_abs2rel "${depInstallPath}" "${installPath}/lib")

            local depIsInPrefix=""
            if [[ ${depInstallPath} =~ .*${installPath} ]]; then
                local depIsInPrefix="t"
            fi
            
            if [[ -n ${SCRIPT_DEBUG} ]]; then
                echo "  lib: ${lib}"
                echo "  depInstallPath: ${depInstallPath}"
                echo "  depRelativeFromRPath: ${depRelativeFromRPath}"
                echo "  depIsInPrefix: ${depIsInPrefix}"
            fi
            
            if [[ -n ${depIsInPrefix} ]]; then
                ${SCRIPT_DEBUG} install_name_tool -change ${lib} "@rpath/${depRelativeFromRPath}" "${libFile}"
            fi

        done

    done
}


script_print_help() {
    printf "USAGE: \n\t macos-fix-rpath.sh [d,--debug] --prefix <prefix> --destdir <destdir>\n"
    printf "\nOPTIONS:\t\t"
    printf "\n\t --prefix \t\t install prefix of package"
    printf "\n\t --destdir \t\t path to DESTDIR if used"
    printf "\n\t -d, --debug \t\t print all rpath commands used"
    printf "\n\t -h, --help \t\t show this help"
    printf "\n"
}

parse_args () {
    local InsStagingP=()
    local InsPath=()
    local DebugON=()
    local ShowHelp=()

    set -- ${@}
    zparseopts -K -E -destdir:=InsStagingP -prefix:=InsPath \
        {d,-debug}=DebugON \
        {h,-help}=ShowHelp

    if [[ -n ${ShowHelp} ]]; then
        script_print_help
        exit
    fi

    installStagingPath="${InsStagingP[2]}"
    installPath="${InsPath[2]}"

    if [[ -n ${DebugON} ]]; then
        SCRIPT_DEBUG="fn_script_debug"
    fi
}

# global variables
# installStagingPath=""
# installPath=""
# SCRIPT_DEBUG=""

parse_args ${@}

if [[ -n ${SCRIPT_DEBUG} ]]; then
    echo "staging: ${installStagingPath}"
    echo "prefix: ${installPath}"
fi

fix_rpath $(find ${installStagingPath} -type f)
