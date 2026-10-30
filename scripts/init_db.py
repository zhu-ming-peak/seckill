"""创建独立实验库与最小权限账户。管理员密码只从环境或交互读取。"""
from pathlib import Path
import getpass
import json
import os
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get("LAB2_ENV_FILE", ROOT.parent / "实验记录/本机私用/app-env.json"))
MYSQL = os.environ.get("MYSQL_BIN") or shutil.which("mysql") or r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"


def execute(sql, password):
    env = os.environ.copy()
    env["MYSQL_PWD"] = password
    args = [MYSQL,"--protocol=TCP","--host=127.0.0.1","--user=root","--default-character-set=utf8mb4","--batch","--skip-column-names"]
    r = subprocess.run(args,input=sql.encode("utf-8"),capture_output=True,env=env)
    if r.returncode:
        # 不输出可能带有凭据的 SQL 原文。
        raise RuntimeError("MySQL 操作失败，请检查权限、现有表结构和账户；未输出含凭据的 SQL。")
    return r.stdout.decode("utf-8", errors="replace").strip()


if __name__ == "__main__":
    admin = os.environ.pop("LAB2_MYSQL_ADMIN_PASSWORD", None) or getpass.getpass("本机 MySQL root 密码：")
    print("MySQL:",execute("SELECT VERSION(),CURRENT_USER();",admin))
    account = execute("SELECT COUNT(*) FROM mysql.user WHERE User='lab2_app' AND Host='localhost';", admin)
    if account != "0" and not PRIVATE.exists():
        raise SystemExit("lab2_app 已存在但没有私用连接文件；为避免修改已有账户，停止初始化。")
    execute((ROOT/"sql/01_schema.sql").read_text(encoding="utf-8"),admin)
    if account == "0":
        password = secrets.token_urlsafe(32)
        execute(f"CREATE USER 'lab2_app'@'localhost' IDENTIFIED BY '{password}'; GRANT SELECT,INSERT,UPDATE,DELETE ON lab2_seckill.* TO 'lab2_app'@'localhost';",admin)
        PRIVATE.parent.mkdir(parents=True,exist_ok=True)
        PRIVATE.write_text(json.dumps({"DB_HOST":"127.0.0.1","DB_PORT":"3306","DB_NAME":"lab2_seckill","DB_USER":"lab2_app","DB_PASSWORD":password},indent=2),encoding="utf-8")
    execute((ROOT/"sql/02_seed.sql").read_text(encoding="utf-8"),admin)
    execute((ROOT/"sql/06_async_requests.sql").read_text(encoding="utf-8"),admin)
    print("独立实验库、表结构、演示数据准备完成；应用凭据保存在项目外私用文件，未打印。")

