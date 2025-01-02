script_dir="$(cd "$(dirname "$0")" && pwd)"

#dnf group install -y "Development Tools" "Container Management" "System Tools"
sudo dnf group install -y "Development Tools" 

#apt install cmake libtool g++ libnuma-dev nasm autoconf automake
sudo dnf --enablerepo=devel install -y libtool numactl-libs numactl-devel libtool-ltdl-devel  cmake nasm

# Then install as
#sudo dpkg -i target/debian/escp_0.7.0-1_amd64.deb 
sudo dnf install -y  ${script_dir}/escp-0.7.0-1.el9.x86_64.rpm 
