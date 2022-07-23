#!/usr/bin/env python3

import gi
gi.require_version('Json', '1.0')

from gi.repository import Json
from ruamel import yaml
import os, sys, subprocess
from pathlib import Path


def process_json_manifest(filename, config):
    # open manifest
    with open(filename) as f:
        data = Json.from_string(f.read())

    # get platfom and sdk info
    runtime = data.get_object().get_string_member('runtime')
    runtime_version = data.get_object().get_string_member('runtime-version')
    sdk = data.get_object().get_string_member('sdk')
    # install platform and sdk
    subprocess.call(["flatpak", "--user", "install", "-y", f"{runtime}//{runtime_version}"])
    subprocess.call(["flatpak", "--user", "install", "-y", f"{sdk}//{runtime_version}"])

def process_yaml_manifest(filename, config):
    # open manifest
    with open(filename) as f:
        data = yaml.round_trip_load(f, preserve_quotes=True)
    
    # get platform and sdk info
    runtime = data['runtime']
    runtime_version = data['runtime-version']
    sdk = data['sdk']
    # install platform and sdk
    subprocess.call(["flatpak", "install", "-y", f"{runtime}//{runtime_version}"])
    subprocess.call(["flatpak", "install", "-y", f"{sdk}//{runtime_version}"])

if __name__ == '__main__':
    try:
        modulename = sys.argv[1]
        config = sys.argv[2:]
    except ValueError:
        print("usage: {} module_name [config-opt ...]".format(sys.argv[0]))
        sys.exit(1)
    
    manifestfile = ".flatpak-manifest"
    # add right extension
    if os.path.exists(f"{manifestfile}.yml"):
        manifestfile = f"{manifestfile}.yml"
    elif os.path.exists(f"{manifestfile}.yaml"):
        manifestfile = f"{manifestfile}.yaml"
    else:
        manifestfile = f"{manifestfile}.json"

    # install platform and sdk and update module source
    if manifestfile.endswith('.json'):
        process_json_manifest(manifestfile, config)
    else:
        process_yaml_manifest(manifestfile, config)

    # might be useful for debugging
    subprocess.call(["flatpak", "info", "org.kde.Sdk"])
    subprocess.call(["flatpak", "info", "org.kde.Platform"])

    # finally, build and install
    subprocess.call(["flatpak-builder", "--repo=repo", "--install-deps-from=flathub", "--force-clean", "build-dir", "--disable-rofiles-fuse", "--user", manifestfile])
