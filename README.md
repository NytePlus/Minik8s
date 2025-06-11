# minik8使用指南：

## docker python api

https://docker-py.readthedocs.io/en/stable/networks.html

## etcd python api
https://python-etcd3.readthedocs.io/en/latest/usage.html

## knative functions
https://knative.dev/docs/functions/creating-functions/

## 首先需要启动etcd, kafka, cadviser两个docker
### etcd一键安装
```docker
docker run -d \
  --name etcd \
  -p 2379:2379 \
  -p 2380:2380 \
  quay.io/coreos/etcd:v3.5.0 \
  /usr/local/bin/etcd \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://localhost:2379
```
直接使用host网络，因为bridge网络会被修改为flannel网络，然而flannel的修改依赖于etcd。可能会出问题？
```docker
docker run -d \
  --name etcd \
  --net=host \
  quay.io/coreos/etcd:v3.5.0 \
  /usr/local/bin/etcd \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://10.119.15.182:2379
```

### kafka一键安装
打开代理将无法访问远端kafka
- 下面为docker-compose.yml文件
  ```
  version: '3'
  services:
    zookeeper:
      image: bitnami/zookeeper:3.9.0
      container_name: zookeeper
      ports:
        - 2181:2181
      environment:
        # 时区
        - TZ=Asia/Shanghai
        # 允许匿名登录
        - ALLOW_ANONYMOUS_LOGIN=yes
        # zk在集群中的序号（1~255）
        - ZOO_SERVER_ID=1
        # 端口
        - ZOO_PORT_NUMBER=2181
      volumes:
        - ./zookeeper:/bitnami/zookeeper
    kafka:
      image: bitnami/kafka:3.9.0
      container_name: kafka
      ports:
        - 9092:9092
      environment:
        - TZ=Asia/Shanghai
        # broker id>=0
        - KAFKA_BROKER_ID=0
        # kk配置zk连接
        - KAFKA_CFG_ZOOKEEPER_CONNECT=zookeeper:2181
        # 允许使用PLAINTEXT协议
        - ALLOW_PLAINTEXT_LISTENER=yes
        # kk配置监听器
        - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092
        # kk配置发布到zk的监听器 要公网访问需要配置公网ip 可以配置私网公网分流
        - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://<host-ip>:9092
      volumes:
        - ./kafka/data:/bitnami/kafka/data
      depends_on:
        - zookeeper
    kafka-manager:
      image: sheepkiller/kafka-manager:stable
      container_name: kafka-manager
      ports:
        - 9000:9000
      environment:
        # zk地址
        - ZK_HOSTS=47.103.11.77:2181
        # 应用秘钥
        - APPLICATION_SECRET=xcrj_km_secret
        # km用户名
        - KAFKA_MANAGER_USERNAME=xcrj_kkm_user
        # km密码
        - KAFKA_MANAGER_PASSWORD=xcrj_kkm_pwd
      depends_on:
        - kafka
  ```
- 使用方式：
  ```
  vim docker-compose.yml # 然后把文件粘贴进去
  mkdir ./zookeeper ./kafka
  sudo chown -R 1001:1001 ./zookeeper
  sudo chown -R 1001:1001 ./kafka
  sudo docker-compose up -d
  ```
- 此时kafka和zookeeper都正常启动
    - 可使用docker ps -a查看运行情况

## registry一键启动
serverless需要一个统一的镜像管理网站。然而dockerhub需要代理才能访问，并且他是一个公开网站不适合管理私有镜像。因此使用容器registry。

### 设置用户名密码
建立一个文件设置用户名和密码
```
mkdir -p auth
docker run --rm --entrypoint htpasswd httpd:2 -Bbn <用户名> <密码> > auth/htpasswd
```
### 获取证书
因为docker客户端必须用https传输，所以获取证书
```
mkdir -p certs
openssl req -newkey rsa:4096 -nodes -sha256 \
  -keyout certs/domain.key \
  -x509 -days 365 \
  -out certs/domain.crt \
  -subj "/CN=10.119.15.182" \
  -addext "subjectAltName = IP:10.119.15.182"
```
生成的证书在certs/domain.crt中

### 信任证书

#### 1. 让 Linux 系统信任证书
1. **创建目标目录**  
   ```bash
   sudo mkdir -p /etc/docker/certs.d/10.119.15.182:7000
   ```
2. **将证书复制到 WSL2**  
   ```bash
   sudo cp certs/domain.crt /etc/docker/certs.d/10.119.15.182:7000/ca.crt
   ```

#### 2. 让 Windows 系统信任证书
1. **双击证书文件**（`domain.crt`）→ 选择 **“安装证书”**。
2. **存储位置** 选择 **“本地计算机”** → 点击 **下一步**。
3. **选择证书存储** → **“将所有证书放入下列存储”** → 点击 **浏览** → 选择 **“受信任的根证书颁发机构”**。

**验证是否导入成功：**
- 按 `Win + R` → 输入 `certmgr.msc` → 进入 **证书管理器**。
- 展开 **“受信任的根证书颁发机构”** → **“证书”**，检查你的证书是否存在。

#### 3. 修改 Docker 配置
如果 Docker 仍然不信任证书，可以临时添加 `insecure-registries`（仅限测试环境）：
修改 `daemon.json`，添加：
   ```json
   {
     "insecure-registries": ["10.119.15.182:7000"]
   }
   ```

### 启动registry，在同一目录下执行
```
docker run -d \
  --name registry \
  -p 7000:5000 \
  -v $(pwd)/certs:/certs \
  -v $(pwd)/auth:/auth \
  -v $(pwd)/data:/var/lib/registry \ # 不需要
  -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/domain.crt \ # 加载证书
  -e REGISTRY_HTTP_TLS_KEY=/certs/domain.key \ # 加载证书
  -e "REGISTRY_AUTH=htpasswd" \ # 设置密码
  -e "REGISTRY_AUTH_HTPASSWD_REALM=Registry Realm" \ # 设置密码
  -e "REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd" \ #设置密码
  registry:2.8.2
```

注意我们没有将它加入flannel内网，为了简单起见直接通过公网ip访问

### 验证registry运行
```
docker login 10.119.15.182:7000
```
输入你的用户名和密码，应该可以正常登录

### cadvisor一键启动
- 注：cadvisor仅能在amd64平台上启动（未知能否在windows上启动）
```
sudo docker run \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --volume=/dev/disk/:/dev/disk:ro \
  --publish=8080:8080 \
  --detach=true \
  --name=cadvisor \
  google/cadvisor:latest
```
- 访问硬件资源uri：
```
curl http://localhost:8080/api/v1.3/machine
```
- 访问当前使用资源uri：
```
# docker/ 的 /表示获取整台机器的资源，所以也可以通过container id拿到具体某个docker的资源使用情况
curl http://localhost:8080/api/v1.3/docker/
curl 
```

## CNI插件flannel配置使用

### flannel的配置

每台主机网络配置，**安全组**、**防火墙**，并且确保两个服务器的**docker版本**，然后
```
# docker就用这个版本
sudo apt-get install -y docker-ce=5:20.10.24~3-0~ubuntu-focal docker-ce-cli=5:20.10.24~3-0~ubuntu-focal containerd.io --allow-downgrades

echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p

# 清空防火墙规则
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT

# 清空iptable规则
iptables -F
iptables -L -n
```

为了实现CNI，**每台机器**上都要配置flannel。flannel插件的配置文件需要存储在etcd中，共用一个etcd的机器之间就可以通过flannel互相通信。这里我们和apiServer共用etcd，进入etcd容器并运行指令。
```
docker exec -it <etcd容器名> sh
etcdctl put /coreos.com/network/config '{ "Network": "10.5.0.0/16", "Backend": {"Type": "vxlan"}}'
```

在master节点下载并运行flannel。如果没有查看到配置文件，启动进程会阻塞
```
wget https://github.com/flannel-io/flannel/releases/latest/download/flanneld-amd64 && chmod +x flanneld-amd64
sudo ./flanneld-amd64 -etcd-endpoints http://<etcd服务器ip>:2379
```

现在flannel正在运行，它在主机上创建了一个VXLAN隧道设备，并编写了一个子网配置文件。可以通过打印配置文件来验证
```
cat /run/flannel/subnet.env
FLANNEL_NETWORK=10.5.0.0/16
FLANNEL_SUBNET=10.5.53.1/24
FLANNEL_MTU=1400
FLANNEL_IPMASQ=false
```

需要flannel一直在后台运行，所以需要让它作为服务启动，首先移动到服务的二进制目录下
```
sudo mv flanneld-amd64 /usr/local/bin/flanneld
```
创建一个`/etc/systemd/system/flanneld.service`文件，写入服务配置信息
```
[Unit]
Description=Flannel Network Fabric
After=network.target etcd.service  # 依赖 etcd 或 kube-apiserver
Wants=etcd.service

[Service]
Type=notify
ExecStart=/usr/local/bin/flanneld \
  --etcd-endpoints=http://10.119.15.182:2379
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target                                               
```
确保etcd中写入了配置内容，启动服务
```
sudo systemctl daemon-reload
sudo systemctl enable --now flanneld

# 检查状态和日志
sudo systemctl status flanneld
journalctl -u flanneld -f
```

#### 方法一：将默认bridge网络设置为子网
docker守护进程启动时应该读取这个配置。修改`/etc/docker/daemon.json`增加bip和mtu字段。其中bip是上面配置文件中的FLANNEL_SUBNET（字符串），mtu是FLANNEL_MTU（整型，如果是字符串则报错）。比如
```
"bip": "10.5.53.1/24",
"mtu": 1400,
```
接着重启docker，修改生效
```
systemctl restart docker
```

#### ~~方法二：新建一个容器网络为子网（还不行）~~
```
source /run/flannel/subnet.env
docker network create --attachable=true --subnet=${FLANNEL_SUBNET} -o "com.docker.network.driver.mtu"=${FLANNEL_MTU} flannel
```

### docker api分配子网
只需给容器设置为flannel网络。假如将bridge设置为flannel子网，则创建一个容器指定bridge网络
```
docker run -d --network bridge --name test_flannel nginx
```

#### 验证ip分配
执行`docker inspect`可以看到它的地址为子网下新分配的地址
```
➜   docker inspect test_flannel | grep IPAddress
            "SecondaryIPAddresses": null,
            "IPAddress": "10.5.53.4",
                    "IPAddress": "10.5.53.4",
```

再分配一个则分配一个新的
```
➜   docker run -d --network bridge --name test_flannel2 nginx
83650543a66c389232b9c281c113ea97a21de1e840620e0b3206c7cefa71c3f3
(base) root@group-k8s-master: /root/dockers
➜   docker inspect test_flannel2 | grep IPAddress
            "SecondaryIPAddresses": null,
            "IPAddress": "10.5.53.5",
                    "IPAddress": "10.5.53.5",
```

#### 验证pod间通信

在服务端运行构建好的flask服务器镜像
```
docker run -d --name server-container --net=bridge -p 5000:5000 nyteplus/cni-server:latest
docker inspect server-container | grep IPAddress #查看子网ip
```

在客户端
```
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://<服务端容器子网ip>:5000"
```

如果无法收到消息，则进行下一步抓包排查

#### 排查问题
服务器A上容器A发送给服务器B上的容器B，flannel网络VXLAN模式链路：

容器A的eth0 → 服务器A的cni0 → flannel.1（封包VXLAN）→ 服务器A的物理网卡（如eth0）→ 服务器B的物理网卡 → flannel.1（解包VXLAN）→ cni0 → 容器B的eth0

1. 在服务器B的物理网卡抓包`sudo tcpdump -i ens3 -nn 'udp and port 8472'`
2. 在flannel.1网卡抓包`sudo tcpdump -i flannel.1 -vv`
3. 在容器内eth0抓包

## 配置coredns
创建一个`Corefile`，注意etcd的ip不能使用etcd容器名，因为默认bridge网络不会提供服务发现功能，而我们的flannel建立在bridge网络之上
```
.:53 {
    etcd {
        path /skydns
        endpoint http://<etcd内网ip>:2379
        fallthrough
    }
    forward . 8.8.8.8
    log
    errors
}
```
一键启动coredns，注意确保与etcd处于同一个网络。主机dns服务在53端口，我们映射到主机54端口
```
docker run -d \
  --name coredns \
  -p 54:53/udp \
  -p 54:53/tcp \
  -v $(pwd)/Corefile:/Corefile \
  --network bridge \
  coredns/coredns:latest
```

### 验证安装配置
主机验证，往etcd插入记录看是否能够通过`dig`访问
```
dig @127.0.0.1 -p 54 www.example.com #查询，应该无回复

docker exec -it etcd sh
etcdctl put /skydns/com/example/www '{"host":"1.1.1.1","ttl":60}'
exit

dig @127.0.0.1 -p 54 www.example.com #查询，应该有回复
```
Pod验证

## 运行环境创建
- 创建虚拟环境（也可以选择在本机上直接运行）并配置python包
  ```
  conda create -n k8s python=3.12
  pip install -r requirements.txt
  ```

- 如果在一台新机器上，需要配置flannel，参考上面的指南

### 配置cicd
- 首选确保服务器上有python和docker（这两个没有的话一切都进行不了）
```
sudo apt install python3 python3-pip
sudo apt install python3-dev build-essential
sudo apt install python-is-python3

wget https://github.com/edenhill/librdkafka/archive/refs/tags/v2.10.0.tar.gz
tar -xzf v2.10.0.tar.gz
cd librdkafka-2.10.0
./configure
make
sudo make install
sudo ldconfig
pip install --no-binary :all: confluent-kafka
# 给容器授权
sudo chown -R 1001:1001 /home/chenglianglin/actions-runner/_work/k8s_group_4/k8s_group_4/yamls
```
- 配置服务器上的runner
  - 首先创建一个非root用户，并给予它/home/<username>下文件的创建、修改权限
  ```

  ```
  - 然后根据github action中对于self host的指令进行配置，最后在该用户下运行./run.sh

## hf下模型
```
git clone https://NytePlus:REMOVED@huggingface.co/distilbert/distilgpt2
```