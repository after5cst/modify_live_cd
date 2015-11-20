#!/bin/bash
set -e

sudo apt-get install aptitude --force-yes -fuy
sudo aptitude clean

sudo apt-get autoclean
sudo apt-get clean
sudo apt-get autoremove

sudo rm -rf /tmp/* ~/.bash_history

sudo rm -f /var/lib/dbus/machine-id

sudo rm -f /sbin/initctl
sudo dpkg-divert --rename --remove /sbin/initctl
