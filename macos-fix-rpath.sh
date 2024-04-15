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

        ${SCRIPT_DEBUG} install_name_tool -delete_rpath "${installPath}/lib" "${libFile}" 2> /dev/null

        if [[ -n "$(grep -E '(framework.*bin|MacOS)' <<< ${libFile})" ]]; then
            rel2lib=$(perl_abs2rel "${libFile%/lib/*}" "${libFile%/*}")
            ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path/${rel2lib}/lib "${libFile}" 2> /dev/null

        elif [[ -n "$(grep -E '(framework.*lib)' <<< ${libFile})" ]]; then
            rel2lib=$(perl_abs2rel "${libFile%%/lib/*}" "${libFile%/*}")
            ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path/${rel2lib}/lib "${libFile}" 2> /dev/null

        elif [[ -n "$(grep 'bin/' <<< ${libFile})" ]]; then
            ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path/../lib "${libFile}" 2> /dev/null
        fi

        for lib in ${SharedLibs[@]}; do
            if [[ -n ${SCRIPT_DEBUG} ]]; then
                echo "LIB: ${lib}"
                echo "INSTALLPATH_LIB: ${libFile#${installStagingPath}}"
            fi

            if [[ "${lib}" = "${libFile#${installStagingPath}}" ]]; then
                ${SCRIPT_DEBUG} install_name_tool -id "@rpath/${lib##*lib/}" "${libFile}"
                ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path "${libFile}" 2> /dev/null

            elif [[ -n "$(grep '_install' <<< ${lib})" ]]; then
                ${SCRIPT_DEBUG} install_name_tool -change ${lib} "@rpath/${lib##*lib/}" "${libFile}"
                ${SCRIPT_DEBUG} install_name_tool -add_rpath @loader_path "${libFile}" 2> /dev/null
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
