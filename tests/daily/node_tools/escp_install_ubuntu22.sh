#!/bin/bash

# Install system dependencies
sudo apt update
sudo apt install -y vim iputils-ping  curl net-tools
sudo apt install -y build-essential 
sudo apt install -y cmake libtool g++ libnuma-dev nasm autoconf automake

# Then install as
sudo dpkg -i escp_0.7.0-1_amd64.deb 

echo "Done!"
