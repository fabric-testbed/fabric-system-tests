#!/bin/bash

#dnf group install -y "Development Tools" "Container Management" "System Tools"
sudo dnf group install -y "Development Tools" 

#apt install cmake libtool g++ libnuma-dev nasm autoconf automake
sudo dnf --enablerepo=devel install -y libtool numactl-libs numactl-devel libtool-ltdl-devel  cmake nasm


git clone https://github.com/esnet/EScp.git
mkdir EScp
cd EScp

curl https://sh.rustup.rs -sSf | sh
. "$HOME/.cargo/env"

#edit vim libdtn/CMakeLists.txt.  Add '-fPIE' to cmake c flags
#set(CMAKE_C_FLAGS_RELEASE "-g -march=sandybridge -O3 -pthread -fPIE")
#set(CMAKE_C_FLAGS_DEBUG "-g -march=sandybridge -O3 -pthread -fPIE")

sed -i 's/\(set(CMAKE_C_FLAGS_RELEASE ".*\)\(")\)/\1 -fPIE\2/' libdtn/CMakeLists.txt
sed -i 's/\(set(CMAKE_C_FLAGS_DEBUG ".*\)\(")\)/\1 -fPIE\2/' libdtn/CMakeLists.txt


cargo build

cargo install cargo-rpm
cargo rpm init
cargo rpm build

# Then install as
#sudo dpkg -i target/debian/escp_0.7.0-1_amd64.deb 
sudo dnf install -y  target/release/rpmbuild/RPMS/x86_64/escp-0.7.0-1.el9.x86_64.rpm 

# dtn and escp executables at target/{release,debug}/{escp,dtn}
#cargo install --path . --root /usr/local --force

# DEVELOPMENT TOOLS:
#cargo install bindgen-cli # bindgen at version 0.68.1
#apt  install flatbuffers-compiler # flatc at version 23.5.26
# + GDB, valgrind,