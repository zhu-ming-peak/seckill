# Lab2 商品秒杀系统

本项目用于《架构驱动的软件开发实践》实验二，以商品秒杀场景学习 MySQL、Redis、RocketMQ 的基础使用和协作。

## 当前状态

已完成阶段 A、阶段 B 本机数据库版和阶段 C Redis 缓存版，当前版本 `0.2.0-cache`。支持活动展示、同步事务下单、每场每人限购、请求重试、订单查询，以及商品缓存、活动库存预热、Lua 原子预扣和回滚补偿。尚未接入 RocketMQ，也未将本项目部署到 ECS。RDS 入门实践待资源。

本地访问：`http://127.0.0.1:18092/`。这是课程演示，实验用户编号不构成登录认证，不提供真实支付。

## 拟实现的三个阶段

1. 数据库版：活动查询、事务下单、库存条件更新、重复购买约束。
2. 缓存版：商品缓存、缓存失效、活动库存预热和原子预扣。
3. 异步版：消息入队、异步落单、请求结果查询、消费幂等与失败恢复。

## 技术路线

- Java 17、Maven、Spring Boot 3.5.16、MyBatis Starter 3.0.5。
- 本机 MySQL 服务端版本已核实为 8.0.46，InnoDB。
- Redis 已在本机 Ubuntu WSL 中安装并验证为 7.4.8；RocketMQ 拟用 5.5.1，尚未安装。
- 先完成本机实践，再以独立目录部署到已有 ECS，保留 lab1 应用与默认 Java 8。

## 目录

- `sql/`：后续建表、初始化与验证 SQL。
- `deploy/`：配置模板与后续部署说明。
- `docs/`：架构、接口、测试与限制说明。
- `tests/`：后续验证和测试材料。

## 使用说明

先确保 Java 17、Maven、Python 3 和本机 MySQL 可用。已有实验环境可以直接使用项目外配置；新环境先初始化：

```powershell
python scripts/init_db.py
python scripts/prepare_redis_wsl.py
python scripts/lab.py test
python scripts/lab.py build
python scripts/lab.py run
```

初始化脚本在终端交互读取本机 root 密码，创建独立 `lab2_seckill` 数据库与 `lab2_app@localhost` 账户，仅授权该库 SELECT、INSERT、UPDATE、DELETE。应用连接配置默认保存在项目外 `../实验记录/本机私用/app-env.json`；管理员密码不保存。已有同名账户却缺少私用配置时，脚本会停止，不重置原账户。

`lab.py` 支持 `--env-file` 和 `--maven`；可通过 `MYSQL_BIN` 指定 MySQL 客户端，通过 `MAVEN_BIN` 指定 Maven。脚本中的 Windows 工具路径为本次实验的回退路径，其他机器应显式提供工具位置。

Redis 准备脚本针对本机默认 Ubuntu 24.04 WSL2，以发行版 root 安装官方软件包和独立 lab2-redis 服务，不涉及 ECS root。先初始化数据库私用配置，再执行 Redis 准备脚本；它不会覆写已存在的 Redis 实验配置。已有环境直接使用启动入口即可。Windows 启动和测试入口保持 WSL 运行，避免无客户端时发行版退出导致连接中断。

运行入口将 JAR 复制到项目外私用 runtime 目录后启动，副本按内容哈希区分，避免 Windows 锁定 target 中的构建产物。结束演示时在前台窗口使用 Ctrl+C。

`.env.example` 是配置变量示例，不会被 Spring Boot 自动加载；本机入口读取上述 JSON 并注入进程环境。服务器安装与正式部署说明在阶段 F 补充。

运行接口检查：

```powershell
python tests/verify_http.py --output ../实验记录/阶段B/HTTP验收.json
```

该检查会创建一笔真实实验订单，需要活动 1 仍在有效期且有库存。活动会随时间自然结束；如需重新演示，可人工执行 `sql/05_reset_demo.sql`，它会删除演示活动 1–5 的实验订单，不能在需要保留结果时执行。

当前验证结果：25 项集成测试通过（数据库版回归 8 项、真实 Redis 场景 15 项、Redis 故障场景 2 项），18 项 HTTP 回归及 Edge 页面下单通过。商品接口 `/api/products/{id}` 用 `X-Product-Cache` 响应头区分 MISS/HIT；最终双库存核对通过。这不是系统容量或高并发性能结论。

设计和恢复边界见 [Redis 缓存版设计](docs/Redis缓存版设计与验证.md)。数据库基础版历史说明见 [数据库版设计与验证](docs/数据库版设计与验证.md)。本地版本标签 `v0.1.0-db` 与 `v0.2.0-cache` 分别保留两个阶段；尚未推送 GitHub。

基础命令示例：`python scripts/redis_local.py PING`。恢复库存前必须停流并核对 MySQL，再仅删除相应活动预扣键，不能在运行中直接执行 SQL 重置或 FLUSHDB。具体过程见缓存版设计说明。

真实凭据、服务器私用配置和原始实验记录不提交到公开仓库。

