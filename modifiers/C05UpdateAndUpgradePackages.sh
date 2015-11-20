#!/bin/bash
set -e

# update & dist-upgrade
unset UCF_FORCE_CONFFOLD
export UCF_FORCE_CONFFNEW=YES
sudo ucf --purge /boot/grub/menu.lst

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get -o Dpkg::Options::="--force-confnew" --force-yes -fuy dist-upgrade

