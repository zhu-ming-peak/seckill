#!/usr/bin/env bash
# 由本机准备脚本以 root 在 Ubuntu WSL 中运行；密码由环境传入，不回显。
set -euo pipefail
: "${LAB2_REDIS_PASSWORD:?missing Redis password}"
export DEBIAN_FRONTEND=noninteractive
if ! command -v redis-server >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  curl --connect-timeout 20 --max-time 90 -fsSL https://packages.redis.io/gpg -o /tmp/lab2-redis.gpg
  gpg --batch --yes --dearmor -o /usr/share/keyrings/lab2-redis.gpg /tmp/lab2-redis.gpg
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/lab2-redis.gpg] https://packages.redis.io/deb noble main' > /etc/apt/sources.list.d/lab2-redis.list
  apt-get update -qq
  version=$(apt-cache madison redis-server | awk '$3 ~ /7\.4\.8/ && !found {print $3; found=1}')
  if [ -z "$version" ]; then echo 'Redis 7.4.8 not available; stop without silently changing version'; exit 2; fi
  echo "Installing Redis package version: $version"
  apt-get install -y -qq "redis-server=$version" "redis-tools=$version"
  systemctl disable --now redis-server.service
fi
if [ -e /etc/redis/lab2.conf ]; then
  echo 'lab2.conf already exists; refuse to overwrite'; exit 3
fi
install -d -o redis -g redis -m 750 /var/lib/redis/lab2
umask 027
cat > /etc/redis/lab2.conf <<EOF
bind 127.0.0.1
protected-mode yes
port 6379
requirepass $LAB2_REDIS_PASSWORD
daemonize no
supervised systemd
dir /var/lib/redis/lab2
appendonly yes
appendfsync everysec
save 60 1000
maxmemory 128mb
maxmemory-policy noeviction
logfile ""
EOF
chown root:redis /etc/redis/lab2.conf
chmod 640 /etc/redis/lab2.conf
cat > /etc/systemd/system/lab2-redis.service <<'EOF'
[Unit]
Description=Lab2 Redis local experiment
After=network.target
[Service]
Type=notify
User=redis
Group=redis
ExecStart=/usr/bin/redis-server /etc/redis/lab2.conf
Restart=on-failure
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now lab2-redis.service
redis-server --version
REDISCLI_AUTH="$LAB2_REDIS_PASSWORD" redis-cli PING
