#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modify a Ubuntu live CD with a series of scripts.

   TODO: Describe parameters and script naming conventions.

   Based on the Ubuntu article LiveCDCustomization
   https://help.ubuntu.com/community/LiveCDCustomization
"""
import argparse
from contextlib import ExitStack
import glob
import os
from pathlib import Path
from pprint import pprint
import shutil
import subprocess
import sys
import tempfile
import time


class ChRoot(object):

    """Class that will enter/exit chroot 'with'-style"""

    def __init__(self, new_root):
        self.new_root = str(Path(new_root).resolve())
        pass

    def __enter__(self):
        self.real_root = os.open("/", os.O_RDONLY)
        os.chroot(self.new_root)
        return self

    def __exit__(self, type, value, traceback):
        os.fchdir(self.real_root)
        os.chroot(".")
        os.close(self.real_root)


def rmtree(path):
    """Remove a directory and contents, including escalating to sudo
       if necessary.
    """
    try:
        shutil.rmtree(path)
    except PermissionError:
        subprocess.check_call(['sudo', 'rm', '-rf', path])


def run(stack, start=None, stop=None):
    """Run a subprocess.run command (and optionally and undo
       command) based on lists
    """
    if start is not None:
        subprocess.check_call(start)
    if stop is not None:
        stack.callback(subprocess.call, stop)


def run_scripts(path, prefix):
    """Run a list of scripts found in the providedfind_scripts path"""
    dashes1 = '-' * 10 + ' '
    dashes2 = ' ' + '-' * 10

    with ExitStack() as stack:

        original_path = os.getcwd()
        os.chdir(path)
        stack.callback(os.chdir, original_path)

        items = []
        s = str(prefix) + "[0-9][0-9]*"
        for name in glob.glob(s):
            if os.access(name, os.X_OK):
                items.append(str(Path(name).resolve()))
        items.sort()
        for item in items:
            print(dashes1 + 'START ' + str(item) + dashes2)
            subprocess.check_call([item])
            print(dashes1 + 'END ' + str(item) + dashes2)


def modify_live_cd(input_iso_path, output_iso_path, mod_scripts_path):
    """TODO: Document.
    """

    input_iso_path = str(Path(input_iso_path).resolve())
    output_iso_path = os.path.abspath(output_iso_path)
    mod_scripts_path = str(Path(mod_scripts_path).resolve())

    #------------------------------------------------------
    # INSTALL PRE-REQUISITIES
    # 1. Make sure that you have installed the needed tools
    subprocess.check_call(
        ['sudo',
         'apt-get',
         'install',
         'squashfs-tools',
         'genisoimage'])

    with ExitStack() as stack:
        #--------------------------------------------------
        # OBTAIN THE BASE SYSTEM
        # 1. Download an official Desktop CD from http://releases.ubuntu.com/
        #    (not done here: passed as input_iso_path)

        # 2. Create a temporary directory (and remove it when done)
        livecdtmp = tempfile.mkdtemp()
        stack.callback(rmtree, livecdtmp)

        # 3. Change to that directory (and go back when done)
        original_path = os.getcwd()
        os.chdir(livecdtmp)
        stack.callback(os.chdir, original_path)

        #--------------------------------------------------
        # EXTRACT THE CD .iso CONTENTS
        print('--> 05. Mount the desktop ISO')
        os.mkdir('mnt')
        mnt = str(Path('mnt').resolve())
        stack.callback(rmtree, mnt)
        run(stack=stack,
            start=[
            'sudo',
            'mount',
            '-o',
            'loop,ro',
            '-t',
            'auto',
            input_iso_path,
            mnt],
            stop=['sudo', 'umount', mnt])

        print('--> 10. Extract .iso contents into dir extract-cd')
        os.mkdir('extract-cd')
        extractcd = str(Path('extract-cd').resolve())
        stack.callback(rmtree, extractcd)
        subprocess.check_call(
            ['sudo', 'rsync', '--exclude=/casper/filesystem.squashfs',
             '-a', mnt + '/', extractcd])

        #--------------------------------------------------
        # EXTRACT THE DESKTOP SYSTEM
        print('--> 15. Extract the SquashFS filesystem')
        subprocess.check_call(
            ['sudo', 'unsquashfs', '-d', 'edit',
                'mnt/casper/filesystem.squashfs']
        )
        edit = str(Path('edit').resolve())

        print('--> 20. Run BeforeChroot scripts')
        run_scripts(mod_scripts_path, 'B')  # Run "before" scripts

        #--------------------------------------------------
        # PREPARE AND CHROOT

        # input('Press <ENTER> to continue')

        with ExitStack() as chroot_stack:

            print('--> 25. Mount /dev')
            dev_path = os.path.join(edit, 'dev')
            run(stack=chroot_stack,
                start=['sudo', 'mount', '--bind', '/dev/', dev_path],
                stop=['sudo', 'umount', dev_path]
                )

            print("--> 30. Put your host's resolvconf info into the chroot")
            run_path = os.path.join(edit, 'run')
            run(stack=chroot_stack,
                start=['sudo', 'mount', '--bind', '/run/', run_path],
                stop=['sudo', 'umount', run_path]
                )

            print('--> 35. Mount script directory underneath chroot root dir')
            link_to_scripts_dir = tempfile.mkdtemp(dir=edit)
            chroot_stack.callback(rmtree, link_to_scripts_dir)
            run(stack=chroot_stack,
                start=[
                'sudo',
                'mount',
                '--bind',
                mod_scripts_path +
                '/',
                link_to_scripts_dir],
                stop=['sudo', 'umount', link_to_scripts_dir]
                )
            chroot_scripts_path = '/' + \
                os.path.relpath(link_to_scripts_dir, edit)

            chroot_stack.callback(os.chdir, os.getcwd())

            print('--> 40. chroot to ' + edit)
            chroot_stack.enter_context(ChRoot(edit))
            os.chdir('/')

            print('--> 45. Mount /proc')
            run(stack=chroot_stack,
                start=['sudo', 'mount', '-t', 'proc', 'none', '/proc'],
                stop=['sudo', 'umount', '/proc']
                )

            print('--> 50. Mount /sys')
            run(stack=chroot_stack,
                start=['sudo', 'mount', '-t', 'sysfs', 'none', '/sys'],
                stop=['sudo', 'umount', '/sys']
                )

            print('--> 55. Mount /dev/pts')
            run(stack=chroot_stack,
                start=['sudo', 'mount', '-t', 'devpts', 'none', '/dev/pts'],
                stop=['sudo', 'umount', '/dev/pts']
                )

            #----------------------------------------------
            # CUSTOMIZATIONS
            #
            print('--> 60. Run user scripts from ' + chroot_scripts_path)
            run_scripts(chroot_scripts_path, 'C')  # Run "chroot" scripts

            #----------------------------------------------
            # CLEANUP
            #
            print('--> 65. Perform image cleanup.')
            # pprint(os.listdir(chroot_scripts_path))

        print('--> 70. Run AfterChroot scripts')
        run_scripts(mod_scripts_path, 'A')  # Run "after" scripts

        #--------------------------------------------------
        # PRODUCING THE CD IMAGE
        # Assembling the file system

        print('--> 75. Regenerate manifest')
        steps = [
            "chmod +w extract-cd/casper/filesystem.manifest",
            "sudo chroot edit dpkg-query -W --showformat='${Package} ${Version}\n' > extract-cd/casper/filesystem.manifest",
            "sudo cp extract-cd/casper/filesystem.manifest extract-cd/casper/filesystem.manifest-desktop",
            "sudo sed -i '/ubiquity/d' extract-cd/casper/filesystem.manifest-desktop",
            "sudo sed -i '/casper/d' extract-cd/casper/filesystem.manifest-desktop"
        ]
        for step in steps:
            subprocess.check_call(step, shell=True)

        print('--> 80. Compress filesystem')
        steps = [
            "sudo rm -f extract-cd/casper/filesystem.squashfs",
            "sudo mksquashfs edit extract-cd/casper/filesystem.squashfs -comp xz -e edit/boot",
        ]
        for step in steps:
            subprocess.check_call(step, shell=True)

        print('--> 85. Miscellaneous file updates')
        today = time.strftime("%Y-%m-%d")
        steps = [
            "printf $(sudo du -sx --block-size=1 edit | cut -f1) > extract-cd/casper/filesystem.size",
            "sudo sed -i 's/DISKNAME/DISKNAME " +
                today + "/g' extract-cd/README.diskdefines",
            "sudo rm extract-cd/md5sum.txt",
            "cd extract-cd && find -type f -print0 | sudo xargs -0 md5sum | grep -v isolinux/boot.cat | sudo tee md5sum.txt",
        ]
        for step in steps:
            subprocess.check_call(step, shell=True)

        print('--> 90. Create the ISO image')
        subprocess.check_call(
            ['sudo', 'mkisofs', '-D', '-r', '-V', '"$IMAGE_NAME"',
             '-cache-inodes', '-J', '-l', '-b', 'isolinux/isolinux.bin', '-c',
             'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4',
             '-boot-info-table', '-o', output_iso_path, 'extract-cd'])


if __name__ == "__main__":
    if os.getuid() != 0:
        print("root level access required.")
        sys.exit(-1)

    parser = argparse.ArgumentParser(description='Modify Ubuntu ISO')
    parser.add_argument(
        '-i',
        '--input',
        help='Path to source ISO',
        required=True)

    parser.add_argument(
        '-o',
        '--output',
        help='Output ISO file name',
        required=True)

    parser.add_argument(
        '-s',
        '--script',
        help='Path to script directory',
        required=True)

    args = vars(parser.parse_args())

    modify_live_cd(
        input_iso_path=args['input'],
        output_iso_path=args['output'],
        mod_scripts_path=args['script']
    )
