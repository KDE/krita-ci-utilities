#!/usr/bin/env python3
import os, sys, subprocess

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
    subprocess.call(["flatpak", "info", "org.kde.Sdk"])
    subprocess.call(["flatpak", "info", "org.kde.Platform"])

    # finally, build and install
    subprocess.call(["flatpak-builder", "--repo=repo", "--force-clean", "build-dir", "--disable-rofiles-fuse", "--user", manifestfile])
