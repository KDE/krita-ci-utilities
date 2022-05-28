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

    mods = data.get_object().get_array_member('modules')
    # loop through modules
    for i in range(mods.get_length()):
        mod = mods.get_element(i)
        if mod.get_node_type() != Json.NodeType.OBJECT:
            continue
        mod = mod.get_object()

        # we find the module whose source we need to update
        if mod.get_string_member('name') == modulename:
            sources = mod.get_array_member('sources')
            new_sources = Json.Array()
            for i in range(sources.get_length()):
                if sources.get_object_element(i).get_string_member('type') != 'git':
                    new_sources.add_object_element(sources.get_object_element(i))
                    continue

                path = os.path.relpath('.', os.path.dirname(manifestfile))
                new_sources.add_element(Json.from_string('{"type": "dir", "path": "%s"}' % path))

            mod.set_array_member('sources', new_sources)

            # add any extra config opts
            if config:
                newconfig = Json.Array.sized_new(len(config))
                for arg in config:
                    newconfig.add_string_element(arg)
                mod.set_array_member('config-opts', newconfig)

    # write out updated manifest
    with open(filename, 'w') as f:
        f.write(Json.to_string(data, True))

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

    # loop through modules
    for mod in data['modules']:
        if not isinstance(mod, dict):
            continue
        # we find the module whose source we need to update
        if mod['name'] == modulename:
            for i in range(len(mod['sources'])):
                if mod['sources'][i]['type'] != 'git':
                    continue
                path = os.path.relpath('.', os.path.dirname(manifestfile))
                mod['sources'][i] = {'type': 'dir', 'path': path}

                # add any extra config opts
                if config:
                    mod['config-opts'] = config

    # write out updated manifest
    with open(filename, 'w') as f:
        yaml.round_trip_dump(data, f)

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
    subprocess.call(["flatpak-builder", "--repo=repo", "--force-clean", "build-dir", "--install", manifestfile])
