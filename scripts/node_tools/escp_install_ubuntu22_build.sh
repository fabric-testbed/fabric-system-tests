#!/bin/bash

# Install system dependencies
sudo apt update
sudo apt install -y vim iputils-ping  curl net-tools
sudo apt install -y build-essential 
sudo apt install -y cmake libtool g++ libnuma-dev nasm autoconf automake

# Get rust
#curl https://sh.rustup.rs -sSf | sh
curl https://sh.rustup.rs -o sh.rustup.rs
chmod +x sh.rustup.rs
./sh.rustup.rs -y
. "$HOME/.cargo/env"

git clone https://github.com/esnet/EScp.git

cd EScp

# Build escp (This also build libdtn.a using build_libdtn.sh script)
cargo build

# You now need to install escp, the suggested path is to create an RPM/DEB
cargo install cargo-deb
cargo deb

# or

#cargo install cargo-rpm
#cargo rpm init
#cargo rpm build

# Then install as
sudo dpkg -i target/debian/escp_0.7.0-1_amd64.deb 

# For development
#cargo install bindgen-cli --version 0.68.1
#bindgen ../include/dtn.h -o bindings.rs --use-core  --generate-cstr

# You probably also want gdb/valgrind/whatever your favorite debug tools are

echo "Done!"
