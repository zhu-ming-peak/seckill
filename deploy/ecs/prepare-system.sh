#!/usr/bin/env bash
# Ubuntu 22.04 专用实验机：不替换默认 Java，不修改 EDAS/SSH/安全组。
set -euo pipefail
test "$(id -u)" = 0
. /etc/os-release
test "$VERSION_CODENAME" = jammy
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
if { command -v mysqld >/dev/null || command -v redis-server >/dev/null; } && [ ! -e /opt/lab2-seckill/.bootstrap-owned ]; then
  echo 'Existing database/cache requires a separate review; no configuration overwritten'; exit 3
fi
python3 - <<'PY'
from pathlib import Path
import json,os,shutil
path=Path('/var/tmp/lab2-preflight.json')
java=shutil.which('java')
if not java:raise RuntimeError('Record and review the default Java environment before installation')
actual=os.path.realpath(java)
if path.exists():
    assert json.loads(path.read_text())['default_java_path']==actual
else:
    path.write_text(json.dumps({'default_java_path':actual}))
    path.chmod(0o600)
PY
install -m 600 /dev/null /opt/lab2-seckill/.bootstrap-owned
install -d /etc/mysql/mysql.conf.d /etc/systemd/system/mysql.service.d
cat > /etc/mysql/mysql.conf.d/zz-lab2.cnf <<'EOF'
[mysqld]
bind-address=127.0.0.1
mysqlx=0
innodb_buffer_pool_size=128M
max_connections=32
table_open_cache=256
table_definition_cache=400
tmp_table_size=16M
max_heap_table_size=16M
EOF
cat > /etc/systemd/system/mysql.service.d/lab2-memory.conf <<'EOF'
[Service]
MemoryHigh=512M
MemoryMax=768M
EOF
apt-get -o DPkg::Lock::Timeout=180 update -qq
apt-get -o DPkg::Lock::Timeout=180 install -y -qq --no-install-recommends mysql-server ca-certificates curl gnupg unzip logrotate
curl --connect-timeout 15 --max-time 90 -fsSL https://packages.redis.io/gpg -o /opt/lab2-seckill/staging/redis-signing-key.gpg
gpg --batch --yes --dearmor -o /usr/share/keyrings/lab2-redis.gpg /opt/lab2-seckill/staging/redis-signing-key.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/lab2-redis.gpg] https://packages.redis.io/deb jammy main' > /etc/apt/sources.list.d/lab2-redis.list
apt-get -o DPkg::Lock::Timeout=180 update -qq
redis_version=$(python3 -c 'import subprocess; rows=subprocess.check_output(["apt-cache","madison","redis-server"],text=True).splitlines(); print(next((r.split("|")[1].strip() for r in rows if r.split("|")[1].strip().split(":")[-1].startswith("7.4.8-")),""))')
test -n "$redis_version" || { echo 'Redis 7.4.8 package unavailable; selection must be reviewed'; exit 2; }
apt-get -o DPkg::Lock::Timeout=180 install -y -qq "redis-server=$redis_version" "redis-tools=$redis_version"
systemctl disable --now redis-server.service
systemctl daemon-reload
systemctl restart mysql.service
mysql --version
redis-server --version
readlink -f /usr/bin/java
echo 'LAB2_SYSTEM_READY'
