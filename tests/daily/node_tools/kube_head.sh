#https://phoenixnap.com/kb/install-kubernetes-on-rocky-
#https://www.golinuxcloud.com/deploy-multi-node-k8s-cluster-rocky-linux-8/

#https://www.linuxtechi.com/install-kubernetes-on-rockylinux-almalinux/
#https://www.centlinux.com/2022/11/install-kubernetes-master-node-rocky-linux.html
#https://github.com/kubernetes/kubernetes/issues/33618

dataplane_ip=$1

headnode=`hostname -s`

sudo dnf install -y iproute-tc 

sudo setenforce 0
sudo sed -i --follow-symlinks 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/sysconfig/selinux
sestatus

sudo modprobe overlay
sudo modprobe br_netfilter

#sudo tee /etc/sysctl.d/kubernetes.conf<<EOF
sudo tee /etc/sysctl.d/k8s.conf<<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sudo sysctl --system

sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
sudo swapoff -a

sudo tee /etc/yum.repos.d/kubernetes.repo<<EOF
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.28/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.28/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF

dnf makecache --refresh

#sudo dnf update -y

sudo dnf -y install epel-release vim git curl wget kubelet kubeadm kubectl --disableexcludes=kubernetes

sudo tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

sudo dnf install -y yum-utils device-mapper-persistent-data lvm2
#sudo dnf update -y && yum install -y containerd.io
sudo dnf install -y containerd.io

sudo mkdir -p /etc/containerd 
#sudo containerd config default > /etc/containerd/config.toml
#sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g'  /etc/containerd/config.toml

containerd config default | sudo tee /etc/containerd/config.toml >/dev/null 2>&1
sudo sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml

sudo systemctl enable --now kubelet

sudo systemctl restart containerd
sudo systemctl enable containerd

sudo systemctl status containerd


#########
lsmod | grep br_netfilter

sudo systemctl enable kubelet

sudo kubeadm config images pull

sudo kubeadm init \
  --pod-network-cidr=10.42.0.0/16 \
  --control-plane-endpoint=${headnode} \
  --apiserver-advertise-address=${dataplane_ip}

mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

kubectl cluster-info

kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/calico.yaml
#kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml
#kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml


kubectl get pods --all-namespaces









