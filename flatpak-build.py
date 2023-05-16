#!/usr/bin/env python3
import os, sys, subprocess, json
from ruamel.yaml import YAML


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

    # might be useful for debugging
    subprocess.call(["flatpak", "info", "org.kde.Sdk//5.15-21.08"])
    subprocess.call(["flatpak", "info", "org.kde.Sdk//5.15-22.08"])
    subprocess.call(["flatpak", "info", "org.kde.Platform//5.15-21.08"])
    subprocess.call(["flatpak", "info", "org.kde.Platform//5.15-22.08"])

    # finally, build and install
    subprocess.call(["flatpak-builder", "--repo=repo", "--force-clean", "build-dir", "--disable-rofiles-fuse", "--user", manifestfile])

    # Export the result to a bundle
    f = open(manifestfile, "r")
    if manifestfile.endswith(".json"):
        manifest = json.load(f)
    else:
        yaml = YAML()
        manifest = yaml.load(f)

    app_id = manifest["id"]
    subprocess.call(["flatpak", "build-bundle", "repo",
                     f"{modulename}.flatpak", app_id, "master"])
