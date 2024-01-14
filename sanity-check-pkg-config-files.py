#!/usr/bin/python3
import os
import argparse
import glob
import re

def fix_abs_path(destdir, path):
    #print("fix_abs_path: path={}, destdir={}".format(path, destdir))
    if os.path.isabs(path):
        if destdir:
            print("   fixing...")
            normedPath = os.path.normpath(path)
            normedPath = os.path.splitdrive(normedPath)[1]
            if normedPath.startswith(os.sep):
                normedPath = normedPath[1:]
            outpath = os.path.join(destdir, normedPath)
        else:
            outpath = path
    return outpath

# Capture our command line parameters
parser = argparse.ArgumentParser(description='Scan pkg-config files for being relocatable')
parser.add_argument('--prefix', type=str, required=True)
parser.add_argument('--destdir', type=str)
parser.add_argument('-f', '--fail-on-error', default=False, action='store_true')
arguments = parser.parse_args()

pkgConfigPaths = []
absPrefixPath = os.path.abspath(arguments.prefix)

if 'PKG_CONFIG_PATH' in os.environ:
    pkgConfigPaths.append[os.environ['PKG_CONFIG_PATH'].split(os.pathsep)]

if not arguments.destdir is None or 'DESTDIR' in os.environ:
    destdir = arguments.destdir if not arguments.destdir is None else os.environ['DESTDIR']
    fixedPrefix = fix_abs_path(os.path.abspath(destdir), absPrefixPath)
    # print('Adding destdir location: {}'.format(fixedPrefix))
    pkgConfigPaths.append(os.path.join(fixedPrefix, 'lib', 'pkgconfig'))
else:
    pkgConfigPaths.append(os.path.join(absPrefixPath, 'lib', 'pkgconfig'))

haveFailingFiles = False
errorPrefix = 'ERROR' if arguments.fail_on_error else 'WARNING'
prefixMatcher = re.compile('^\s*prefix\s*=\s*(.+)')

for path in pkgConfigPaths:
    # print('# Checking relocatability in folder: {}'.format(path))
    if not os.path.isdir(path):
        continue

    os.chdir(path) # `root_dir` option is not available in Python 3.8
    for relFile in glob.glob(os.path.join('**', '*.pc'), recursive=True):
        file = os.path.join(path, relFile)
        # print('#   Checking file: {}'.format(file))
        
        with open(file, "r") as fileData:
            for line in fileData:
                prefixCheck = prefixMatcher.match(line)
                if prefixCheck:
                    if not '${pcfiledir}' in prefixCheck.group(1):
                        haveFailingFiles = True
                        print('# {}: {}: .pc file contains non-relocatable prefix: {}'.format(errorPrefix, file, prefixCheck.group(1)))
                elif absPrefixPath in line:
                    haveFailingFiles = True
                    print('# {}: {}: .pc file contains absolute path: {}'.format(errorPrefix, file, line))

exit (0 if not arguments.fail_on_error else int(haveFailingFiles == True))
