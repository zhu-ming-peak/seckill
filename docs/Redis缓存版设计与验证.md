# Redis 缓存版设计

版本：0.2.0-cache。阶段 C，本机 Ubuntu WSL + Windows Java + MySQL。

## 1. 方案与环境

选择在已有 Ubuntu 24.04 WSL2 中安装 Redis 官方 APT 包 7.4.8，保留 Windows Java 与 MySQL，避免引入尚未运行的 Docker 引擎。ECS 自建和云托管作为后续方案，不用本机安装代替云端实践。

本机独立服务 lab2-redis：127.0.0.1:6379、密码认证、protected-mode=yes、最大内存 128 MiB、noeviction、AOF everysec。官方默认服务停止并禁用，仅新增实验服务启用。没有开放公网入口或修改 Windows/WSL 防火墙。

当前 WSL 使用 mirrored 网络。systemd 服务不能单独保证发行版在没有客户端时持续存活，因此 Windows 启动入口为运行或测试建立 WSL 保活客户端，退出时释放该入口创建的客户端。Redis 的凭据位于项目外私用 JSON 和 WSL 受限配置文件，不放进源码或命令参数。

## 2. 商品旁路缓存

活动列表先查询 MySQL 的活动时间、状态、价格与库存，再按 productId 读取商品缓存。静态商品资料与动态活动数据分开处理，避免把过期活动或旧库存当作可购买依据。

读路径：Redis GET → 命中则反序列化 → 未命中查 product 表 → 回填 Redis 并设置 60 秒 TTL。缺失商品返回 404，不缓存不存在数据。

商品资料修改通过 ProductCache.update 完成数据库事务；提交后删除对应 Redis 商品键。回滚时不执行提交后的失效。该修改方法供内部业务和测试使用，没有增加公开的商品管理写接口。

缓存读或回填失败时，商品查询降级到 MySQL；下单库存服务失败则拒绝新购买，不绕过预扣继续落单。商品只读可用不代表整个秒杀服务健康。

GET /api/products/{id} 响应头 X-Product-Cache 返回 HIT、MISS 或 BYPASS；应用日志记录命中、未命中、失效及异常类型，不记录密码。

旁路缓存不是强一致协议。并发查询回填与修改失效之间仍可能短暂返回旧商品资料，TTL 是兜底；本阶段没有实现版本化缓存或跨实例主动失效。购买价格和名称快照仍从事务内的数据库读取。

## 3. 活动预热与 Lua 原子预扣

| 键 | 结构 | 生命周期 |
| --- | --- | --- |
| lab2:v2:product:{id} | String，商品 JSON | 默认 60 秒 |
| lab2:v2:activity:{activityId}:reservation | Hash，stock、user:{userId}、token:{token} | 活动结束后至少保留 1 天；不存在时由数据库重建 |
| lab2:test:redis:* | 测试专用键 | 测试前后清理 |
| lab2:practice:* | 基础命令练习键 | 显式过期或删除 |

活动键中的花括号用于活动维度的 Redis 哈希标签。库存与资格存在同一个 Hash，避免多个键各自过期造成部分状态丢失。

应用启动时，在各活动的 MySQL 行锁内读取已提交剩余库存，预热有效活动；warm.lua 只初始化不存在的活动键，不覆盖已存在的预扣。首次购买遇到缺失键时，也在活动行锁内初始化。重启不会自动重置数据库库存。

reserve.lua 一次完成：必要的初始化、用户资格判断、库存判断、扣减及唯一预扣令牌记录。库存不足、用户已有预扣时拒绝。令牌由服务端生成，与业务 requestId 分开；客户端重试的幂等性仍以数据库订单为准。

本阶段为同步正确性版本：预扣发生在 MySQL 活动行锁内，随后仍执行数据库条件扣减与插单。它演示了 Redis 预扣和双存储状态协作，但并未把所有请求挡在数据库之外，不据此声称实现了流量削峰或吞吐提升。阶段 D 再设计队列受理与消费流程。

## 4. 提交、回滚与异常边界

- MySQL 提交：令牌状态改为 COMMITTED，Redis 预扣数量保留。
- MySQL 明确回滚：检查用户及令牌仍匹配且状态为 PENDING，再回补 1 件并删除该令牌和资格。
- 重复回调或旧令牌：complete.lua 不再次回补，避免缓存库存被多加。
- 数据库事务状态 UNKNOWN：不假定回滚，不盲目回补；记录 RESERVATION_RECONCILE_REQUIRED。
- Redis 在数据库完成后故障：保留日志和预扣状态，要求核对。当前没有自动对账任务或跨 MySQL/Redis 原子提交协议。
- 应用进程崩溃时，完成回调可能未执行；MySQL 仍是最终订单与库存依据，Redis 可能保守少卖，需要停流核对。
- 预扣调用超时或脚本执行异常时，客户端未收到成功不代表 Redis 一定未执行；Lua 原子执行也不提供脚本报错后的自动回滚。此类情况记录待核对标记，不盲目补库存。

## 5. 重置与人工恢复

正常演示不需要重置。只有需要开始新一轮实验，或出现 RECONCILE_REQUIRED 时才按以下顺序操作：

1. 停止本机应用，确认没有其他进程写入这些活动；不能让数据库版与缓存版同时修改同一活动。
2. 核对 MySQL 库存和已提交订单。若确需删除演示订单并重置活动，再人工执行 sql/05_reset_demo.sql，先保存原实验结果。
3. 仅删除对应活动的 lab2:v2:activity:{id}:reservation 键；商品被修改时可一并删除对应商品键。禁止 FLUSHDB 或清理无关命名空间。
4. 启动缓存版，预热从当前数据库恢复；再次核对数据库 stock 与 Redis Hash 的 stock。

直接执行 SQL 重置而保留旧 Redis 活动键，会造成预扣状态失配，因此不提供运行中的自动重置按钮。AOF 能减少状态丢失，但不能替代数据库与 Redis 对账，也不等于零数据丢失保证。

## 6. 云 Redis 学习

阿里云当前文档以“云数据库 Tair（兼容 Redis）”描述相关产品。连接时先确认实例地域、连接地址和网络路径；ECS 内网接入核对同地域、同 VPC、白名单及账号密码。本地安装结果不能替代云实例连接验证。

基础步骤为：准备实例 → 获取连接地址 → 配置客户端网络与白名单 → 配置认证 → 使用 redis-cli 或 SDK 连接 → 验证 PING、键操作及监控。具体认证模式与实例类型有关，按实际实例文档配置，不默认开启免密或公网访问。

本阶段仅完成资料学习；阶段 A 的北京地域查询未发现可用云 Redis 实例，本次没有购买或创建云实例。

## 7. 参考资料

- [Redis 官方 Ubuntu 安装](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/apt/)
- [Redis Lua 脚本与原子执行](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Spring Data Redis 脚本执行](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [阿里云连接准备](https://help.aliyun.com/zh/redis/user-guide/connection-preparation)
- [阿里云实例认证方式](https://help.aliyun.com/zh/redis/user-guide/logon-methods)

## 8. 实际验证（2026-10-30）

25 项集成测试通过：数据库回归 8 项、Redis 正常场景 15 项、连接失败场景 2 项。覆盖命中与数据库读取次数、2 秒 TTL 到期、修改后失效、修改回滚、库存预热不覆盖已有预扣、并发 Lua、同一用户资格、幂等回补和过期令牌、业务事务回滚，以及 Redis 故障。

原子操作测试用 32 个并发任务争抢 8 份预扣资格，只有 8 个成功；同一回补执行两次，只增加 1 份库存。数据库端原有并发订单约束也在 Redis 模式下回归通过。它们是小规模正确性验证，不是容量测试。

18 项 HTTP 回归通过。实际商品请求响应头按顺序为 MISS、HIT；本机 Windows 可连接 WSL 的 127.0.0.1:6379。Edge 页面完成新用户下单、订单展示与库存刷新。

验收快照：MySQL 初始库存 30、剩余 26、订单 4、核对差额 0；Redis 剩余 26、PENDING 令牌 0、COMMITTED 令牌 2。前两笔订单来自数据库版，缓存版从当时剩余 28 预热，因此 Redis 提交令牌数不应被误认为全部历史订单数。

实际问题包括安装入口的标准输入与命令转义、pipefail 下版本筛选管道提前退出、WSL 空闲退出导致连接拒绝，以及测试直接读取 Spring 代理对象字段导致空值。均保留失败日志，修正后完整测试通过；没有把失败轮次当作成功。

交付打包另遇到 Windows 对运行中 JAR 的占用；停止演示进程后重建成功。启动入口改用项目外按 SHA-256 标识的运行副本，避免继续锁住 target 的构建文件。

测试、命令原始输出和截图位于项目外阶段 C 记录。尚未验证进程崩溃后的自动修复；人工恢复和缓存一致性限制以本文件第 4、5 节为准。
