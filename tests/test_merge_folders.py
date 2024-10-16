# SPDX-License-Identifier: BSD-2-Clause
# SPDX-FileCopyrightText: 2024 KDE e.V.
# SPDX-FileContributor: Dmitry Kazakov <dimula73@gmail.com>

import os
import pytest
import sys

from components.MergeFolders import merge_folders
from pathlib import Path
import tempfile

class TestUtil:
    @staticmethod
    def _writeSimpleFile(file : Path, text : str):
        with open(file, "w") as f:
            f.write(text)

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not supported on Win32")
    def test_mergeFolders(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            (dstDir / "bin").mkdir()
            (dstDir / "usr").mkdir()
            (dstDir / "usr/lib").mkdir()
            (dstDir / "usr/lib/site-packages").mkdir()

            (dstDir / "lib").symlink_to(dstDir / "usr/lib", target_is_directory = True)

            self._writeSimpleFile(dstDir / "bin/krita", "krita executable")
            self._writeSimpleFile(dstDir / "bin/qtconfig", "qtconfig executable")
            self._writeSimpleFile(dstDir / "usr/lib/version_info", "version 1")

            (dstDir / "version_info").symlink_to(dstDir / "usr/lib/version_info", target_is_directory = False)

            srcDir = workDir / "src"

            srcDir.mkdir()
            (srcDir / "bin").mkdir()
            (srcDir / "lib").mkdir()
            (srcDir / "share").mkdir()

            self._writeSimpleFile(srcDir / "bin/python", "python executable")
            self._writeSimpleFile(srcDir / "lib/python.so.3.8", "python lib")
            (srcDir / "lib/python.so").symlink_to(srcDir / "lib/python.so.3.8", target_is_directory = False)

            self._writeSimpleFile(srcDir / "share/translation.en", "some translation")

            # copytree cannot merge symlinks properly, so we cannot use it
            #
            # import shutil
            # shutil.copytree(srcDir, dstDir, dirs_exist_ok=True)

            merge_folders(srcDir, dstDir)

            assert (dstDir / "lib").is_symlink()
            assert (dstDir / "lib/python.so.3.8").exists()
            assert (dstDir / "lib/python.so").exists()
            assert (dstDir / "lib/python.so").is_symlink()
            assert (dstDir / "usr/lib/python.so.3.8").exists()
            assert (dstDir / "usr/lib/python.so").exists()
            assert (dstDir / "usr/lib/python.so").is_symlink()
            assert (dstDir / "usr/lib/version_info").exists()
            assert (dstDir / "share/translation.en").exists()


    def test_skipSubFolders(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            (dstDir / "patches").mkdir()
            self._writeSimpleFile(dstDir / "CMakeLists.txt", "build instruction")
            self._writeSimpleFile(dstDir / ".kde-ci.yml", "CI config")
            self._writeSimpleFile(dstDir / "patches/patch1", "patch1")

            srcDir = workDir / "src"

            srcDir.mkdir();
            (srcDir / "patches").mkdir()
            self._writeSimpleFile(srcDir / ".kde-ci-override.yml", "CI config")
            self._writeSimpleFile(srcDir / "patches/patch2", "patch2")

            (srcDir / "_build").mkdir()
            # the skipped directory should be non-empty, otherwise it
            # may be not skipped
            (srcDir / "_build" / "ext_foobar").mkdir()
            (srcDir / "_staging").mkdir()
            (srcDir / "patches/non-needed-dir").mkdir()
            (srcDir / "patches/needed-dir").mkdir()

            merge_folders(srcDir, dstDir,
                          skip_paths=["_build",
                                      "_staging",
                                      "needed-dir",
                                      "patches/non-needed-dir"])

            assert (dstDir / "CMakeLists.txt").exists()
            assert (dstDir / ".kde-ci.yml").exists()
            assert (dstDir / "patches/patch1").exists()
            assert (dstDir / ".kde-ci-override.yml").exists()
            assert (dstDir / "patches/patch2").exists()
            assert not (dstDir / "_build").exists()
            assert not (dstDir / "_staging").exists()
            assert not (dstDir / "patches/non-needed-dir").exists()
            assert (dstDir / "patches/needed-dir").exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not supported on Win32")
    def test_overwriteNormalFiles(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            self._writeSimpleFile(dstDir / "python-3.8.0.so", "python lib")
            (dstDir / "python.so").symlink_to(dstDir / "python-3.8.0.so")

            srcDir = workDir / "src"

            srcDir.mkdir();
            self._writeSimpleFile(srcDir / "python-3.8.0.so", "a different python lib")

            merge_folders(srcDir, dstDir)

            assert (dstDir / "python-3.8.0.so").exists()
            assert (dstDir / "python.so").is_symlink()

    def test_overwriteNormalFilesIgnored(self):
        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            (dstDir / "pkg").mkdir()
            (dstDir / "pkg" / "_vendor").mkdir()
            self._writeSimpleFile(dstDir / "pkg" / "_vendor" / "mylib.py", "python lib 1")
            self._writeSimpleFile(dstDir / "pkg" / "_vendor" / "mylib.cpy", "python lib 1")

            srcDir = workDir / "src"

            srcDir.mkdir()
            (srcDir / "pkg").mkdir()
            (srcDir / "pkg" / "_vendor").mkdir()
            self._writeSimpleFile(srcDir / "pkg" / "_vendor" / "mylib.py", "python lib 2")
            self._writeSimpleFile(srcDir / "pkg" / "_vendor" / "mylib.cpy", "python lib 2")

            os.environ['KDECI_DEBUG_OVERWRITTEN_FILES'] = 'True'

            merge_folders(srcDir, dstDir)

            del os.environ['KDECI_DEBUG_OVERWRITTEN_FILES']

            assert (dstDir / "pkg" / "_vendor" / "mylib.py").exists()
            assert (dstDir / "pkg" / "_vendor" / "mylib.cpy").exists()

    @pytest.mark.xfail(reason="not implemented yet")
    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not supported on Win32")
    def test_overwriteSymlinkWithAFile(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            self._writeSimpleFile(dstDir / "python-3.8.0.so", "python lib")
            (dstDir / "python.so").symlink_to(dstDir / "python-3.8.0.so")

            srcDir = workDir / "src"

            srcDir.mkdir();
            self._writeSimpleFile(srcDir / "python.so", "a different python lib")

            with pytest.raises(FileExistsError):
                merge_folders(srcDir, dstDir)

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not supported on Win32")
    def test_overwriteAFileWithASymlink(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            self._writeSimpleFile(dstDir / "python.so", "a different python lib")

            srcDir = workDir / "src"

            srcDir.mkdir();
            self._writeSimpleFile(srcDir / "python-3.8.0.so", "python lib")
            (srcDir / "python.so").symlink_to(srcDir / "python-3.8.0.so")

            with pytest.raises(FileExistsError):
                merge_folders(srcDir, dstDir)

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not supported on Win32")
    def test_overwriteDifferentSymlinks(self):

        with tempfile.TemporaryDirectory() as wd:
            workDir = Path(wd)

            dstDir = workDir / "dst"

            dstDir.mkdir()
            self._writeSimpleFile(dstDir / "python-3.9.0.so", "python lib")
            (dstDir / "python.so").symlink_to(dstDir / "python-3.9.0.so")

            srcDir = workDir / "src"

            srcDir.mkdir();
            self._writeSimpleFile(srcDir / "python-3.8.0.so", "python lib")
            (srcDir / "python.so").symlink_to(srcDir / "python-3.8.0.so")

            with pytest.raises(FileExistsError):
                merge_folders(srcDir, dstDir)
