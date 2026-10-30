# 验证与性能测试

当前业务版本的集成测试共 38 项：数据库 8、Redis 正常 15、Redis 故障 2、异步流程 10、真实 Broker 3。通过 `python scripts/lab.py test` 执行，先停止所有使用同一实验库的异步应用。专用活动在 900001–900010、900020、900100、900200，测试会清理自己创建的数据，展示活动 1–5 保留。Redis 与 MQ 测试使用独立前缀、Topic 和消费组。

`verify_http.py` 用于旧同步标签；`verify_async_http.py` 用于异步版，会保留一笔真实实验订单。异步脚本的 `--pause-at-accepted` 要求事先停止消费者；`--resume-from` 核对原请求，不自动修改 Broker 或消费者。

## 阶段 E 实测

方案：[固定方案](../docs/阶段E固定测试方案.md)；结果：[性能分析](../docs/阶段E结果/性能分析.md)。

本机独立 Python 施压器：固定线程、每线程持久 HTTP 连接、闭环请求。包含版本/并发顺序轮换、3 次重复、预热、超卖与重复用户场景、全部请求和资源原始数据、数据库首次可见性观察。并发 1/8/16，读窗口每轮 4 秒，写批次每轮 128 库存/128 用户。缓存另测 300 次 MISS 与 300 次 HIT。

该工具用于课程有限比较，不提供开放到达率、协调遗漏修正、分布式施压或生产容量认证。Windows MySQL 可能同时存在监护进程；资源探针按监听端口唯一定位实际进程并记录 PID，不按名称取第一个。

## 复现流程

只适用于当前 Windows + 本机 MySQL + Ubuntu WSL 环境。Java 17、Maven、数据库/Redis/MQ 的准备见项目 README。Python 依赖可装入自己的虚拟环境：

```powershell
python -m pip install -r tests/requirements-benchmark.txt

# 先停止其他使用同库的应用；后台演示用此入口停止
python scripts/local_app.py stop

# 输出目录必须是新的，脚本拒绝覆盖历史运行
python tests/prepare_benchmark.py --output ../实验记录/阶段E/新构建
python tests/benchmark.py --artifacts ../实验记录/阶段E/新构建/artifacts.json --output ../实验记录/阶段E/新测试
python tests/analyze_benchmark.py --run ../实验记录/阶段E/新测试 --publish ../实验记录/阶段E/新分析

# 确认试验退出后，保存快照并清理自己创建的专用数据
python tests/cleanup_benchmark.py --run ../实验记录/阶段E/新测试
python scripts/local_app.py start
```

本次依赖为 PyMySQL 1.2.3、psutil 7.2.2、Matplotlib 3.11.2、NumPy 2.5.4，隔离安装于项目外目录；脚本自动识别该本机目录，其他机器按依赖文件自行准备。可选 `--qa-helpers` 连接本机绘图技能的脚本目录进行额外审计；不提供该参数也可独立生成图表。

准备入口只从三个标签导出快照，在快照内分别执行原有测试与构建，不切换当前分支，也不在仓库保存凭据。它有本机工具回退路径，可通过环境提供 JAVA_HOME、MAVEN_BIN。测试环境文件默认位于项目外，也可传 `--env-file`。不要在真实生产库使用此课程工具。

测试启动前保活 WSL；只允许测试端口空闲，不终止未知进程。失败时保留现场和 JSON，不自动抹去原轮次；排查并停止清单匹配的测试 Java 后，才运行清理。不要覆盖旧目录，也不要复用旧请求编号。

## 数据和清理

性能活动使用 910000–919999 中空闲的 200 号块；商品和每个活动 ID 写入清单，标题/商品名包含运行号。清理先验证归属与进程退出、保存订单/请求/活动快照，再事务删除清单内数据，只删除本轮专用 Redis 前缀，核对展示数据与测试前逐行一致。禁止 FLUSHDB、批量清空订单表或自动重置展示活动。专用 MQ Topic 的历史消息不自动清空。

原始材料保存在项目外：manifest、events、逐请求 JSONL、200 ms 资源采样、100 ms 订单可见性轨迹、每批订单/请求快照、完整日志与 cleanup-result。公开仓库只收录可复现工具、汇总数据和图表。

最初一轮 MySQL CPU 探针误选同名监护进程，原始文件保留并标为不用于最终比较；最终报告采用修正后完整重采的一轮，避免混合两轮数值。绘图时发现字体缺字也已修正，保留失败日志。
