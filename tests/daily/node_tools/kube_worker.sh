#https://www.golinuxcloud.com/kubernetes-add-node-to-existing-cluster/


sudo dnf install -y iproute-tc 

#systemctl enable systemd-resolved --now

swapoff -a
free -m

setenforce 0
sed -i --follow-symlinks 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/sysconfig/selinux

modprobe br_netfilter

ssudo tee /etc/sysctl.d/k8s.conf<<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
EOF

sysctl --system

dnf install -y yum-utils device-mapper-persistent-data lvm2

yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

dnf install containerd.io docker-ce docker-ce-cli -y

####
mkdir -p /etc/docker

sudo tee /etc/docker/daemon.json<<EOF
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m"
  },
  "storage-driver": "overlay2"
}
EOF

systemctl restart docker
systemctl enable docker


sudo mkdir -p /etc/containerd 
sudo containerd config default > /etc/containerd/config.toml

sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g'  /etc/containerd/config.toml


sudo systemctl restart containerd
sudo systemctl enable containerd

sudo tee /etc/yum.repos.d/kubernetes.repo<<EOF 
[kubernetes]
name=Kubernetes
baseurl=https://packages.cloud.google.com/yum/repos/kubernetes-el7-\$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://packages.cloud.google.com/yum/doc/yum-key.gpg https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg
exclude=kubelet kubeadm kubectl
EOF

dnf makecache --refresh

dnf install -y kubelet kubeadm kubectl --disableexcludes=kubernetes

lsmod | grep br_netfilter

sudo systemctl enable kubelet


####  SOME ON HEAD NODE   #######
#kubectl get nodes

#kubeadm token create --print-join-command

### XXXXXX this should be the command that results from previous commmand XXXXX
#kubeadm join 192.168.0.150:6443 --token 1642s5.ih5q6mdtf0pt9jey --discovery-token-ca-cet-hash sha256:d35bc841bd1ad7fd0223e506c8484bcafe9aa59427535b2709ed4b41201ce81b




