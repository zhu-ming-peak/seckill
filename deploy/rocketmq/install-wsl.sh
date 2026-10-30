#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq openjdk-17-jre-headless unzip
install -d /opt/lab2-rocketmq /etc/lab2-rocketmq /var/lib/lab2-rocketmq
if [ ! -d /opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release ]; then
  unzip -q "$LAB2_ROCKETMQ_ARCHIVE" -d /opt/lab2-rocketmq
fi
cat > /etc/lab2-rocketmq/namesrv.properties <<'EOF'
listenPort=9876
bindAddress=127.0.0.1
EOF
cat > /etc/lab2-rocketmq/broker.properties <<'EOF'
brokerClusterName=Lab2Cluster
brokerName=lab2-broker
brokerId=0
brokerIP1=127.0.0.1
bindAddress=127.0.0.1
namesrvAddr=127.0.0.1:9876
listenPort=10911
haListenPort=10912
haListenAddress=127.0.0.1
storePathRootDir=/var/lib/lab2-rocketmq/store
storePathCommitLog=/var/lib/lab2-rocketmq/store/commitlog
mappedFileSizeCommitLog=16777216
mappedFileSizeConsumeQueue=600000
brokerRole=ASYNC_MASTER
flushDiskType=SYNC_FLUSH
autoCreateTopicEnable=false
autoCreateSubscriptionGroup=true
fileReservedTime=24
deleteWhen=04
diskMaxUsedSpaceRatio=85
transientStorePoolEnable=false
EOF
for spec in 'namesrv org.apache.rocketmq.namesrv.NamesrvStartup 128' 'broker org.apache.rocketmq.broker.BrokerStartup 384'; do
  read -r component main heap <<< "$spec"
  cat > "/etc/systemd/system/lab2-mq-$component.service" <<EOF
[Unit]
Description=Lab2 RocketMQ $component
After=network.target lab2-mq-namesrv.service
[Service]
Type=simple
WorkingDirectory=/var/lib/lab2-rocketmq
Environment=ROCKETMQ_HOME=/opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release
ExecStart=/usr/lib/jvm/java-17-openjdk-amd64/bin/java -Xms64m -Xmx${heap}m -XX:MaxDirectMemorySize=128m --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED -Drocketmq.home.dir=/opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release -cp /opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release/lib/* $main -c /etc/lab2-rocketmq/$component.properties
Restart=on-failure
RestartSec=3
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
EOF
done
# NameServer 不能依赖自身；Broker 的 HA 服务不支持本方案中的 bindAddress，单独限制该端口。
sed -i 's/After=network.target lab2-mq-namesrv.service/After=network.target/' /etc/systemd/system/lab2-mq-namesrv.service
iptables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || iptables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP
ip6tables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || ip6tables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP
sed -i '/^ExecStart=/i ExecStartPre=/bin/sh -c "iptables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || iptables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP"\nExecStartPre=/bin/sh -c "ip6tables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || ip6tables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP"' /etc/systemd/system/lab2-mq-broker.service
systemctl daemon-reload
systemctl enable --now lab2-mq-namesrv.service
systemctl enable --now lab2-mq-broker.service
systemctl is-active lab2-mq-namesrv.service lab2-mq-broker.service
