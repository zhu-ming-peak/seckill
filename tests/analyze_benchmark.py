"""从实际测试 JSON/JSONL 生成表格、可编辑矢量图及分析文档，不内置性能数值。"""
from pathlib import Path
import argparse,collections,csv,hashlib,json,math,statistics,sys
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT.parent/'实验记录/本机私用/stageE-python'
if SITE.exists():sys.path.insert(0,str(SITE))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from benchmark import dump,percentile,latency
VERSIONS=['0.1.0-db','0.2.0-cache','0.3.0-async']
LABELS={'0.1.0-db':'数据库版','0.2.0-cache':'缓存版','0.3.0-async':'异步版'}
COLORS=['#0072B2','#E69F00','#009E73'];MARKERS=['o','s','^']
def med(rows,key):return statistics.median(x[key] for x in rows)
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--publish',type=Path,default=ROOT/'docs/阶段E结果');p.add_argument('--qa-helpers',type=Path);a=p.parse_args()
    run=a.run.resolve();out=a.publish.resolve();out.mkdir(parents=True,exist_ok=True);figures=out/'figures';figures.mkdir(exist_ok=True)
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'));assert manifest['status']=='PASS'
    environment=json.loads((run/'environment.json').read_text(encoding='utf-8'))
    assert manifest.get('data_quality',{}).get('eligible_for_final_comparison',True),'该轮已在数据审计中排除'
    assert manifest.get('driver_sha256') and manifest.get('mysql_probe'),'缺少最终采集器和探针身份记录'
    rows=json.loads((run/'summary.json').read_text(encoding='utf-8'));assert len(rows)==60
    resource_files=list((run/'raw').glob('*-resources.json'));assert len(resource_files)==57
    for file in resource_files:
        samples=json.loads(file.read_text(encoding='utf-8'))
        assert len(samples)>=2 and all(x.get('mysql_probe_valid') and x.get('mysql_pid') and x.get('app_pid') and x.get('mysql_listen_port') for x in samples),'资源样本未记录实际进程身份'
    functional=json.loads((run/'functional.json').read_text(encoding='utf-8'));assert len(functional)==3 and all(x['passed'] for x in functional)
    audit_layout=None;exporter=None;profile_helper=None
    if a.qa_helpers:
        sys.path.insert(0,str(a.qa_helpers))
        from setup_style import setup_style
        from visual_qa import audit_layout
        from export_figure import export_figure
        from profile_data import profile_data
        setup_style(journal='general',lang='zh',use_sciplots=False);exporter=export_figure;profile_helper=profile_data
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'font.size':9,'axes.labelsize':9,'axes.titlesize':10,'legend.fontsize':8,'legend.frameon':False,'xtick.labelsize':8,'ytick.labelsize':8,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none','savefig.dpi':300,'savefig.bbox':None})
    keys=sorted(set().union(*(x.keys() for x in rows)))
    with (out/'round_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v for k,v in row.items()})
    grouped=[]
    for kind in ['read','write','cache']:
        for version in VERSIONS:
            for condition in ([1,8,16] if kind!='cache' else ['MISS','HIT']):
                group=[r for r in rows if r['kind']==kind and r['version']==version and (r.get('condition')==condition if kind=='cache' else r['concurrency']==condition)]
                if not group:continue
                assert len(group)==3 and {x['rep'] for x in group}=={1,2,3}
                metrics=['p95_ms','p50_ms','mean_ms','response_rps','completion_p95_ms','completed_orders_per_second','completion_seconds','app_cpu_seconds','app_rss_mib_max','mysql_cpu_seconds','generator_cpu_seconds','host_cpu_pct_max']
                grouped.append({'kind':kind,'version':version,'condition':condition,'n_rounds':3,'metrics':{k:{'median':med(group,k),'min':min(x[k] for x in group),'max':max(x[k] for x in group),'raw':[x[k] for x in group]} for k in metrics if all(k in x for x in group)}})
    dump(out/'grouped_summary.json',grouped)
    # 先做原始数据审计与 EDA，图形不删除长尾或失败样本。
    cache={'MISS':[],'HIT':[]};raw_count=0;unexpected=0;profile=[];checksum=[]
    for file in sorted((run/'raw').glob('*-requests.jsonl')):
        records=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
        checksum.append({'file':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'count':len(records)})
        assert records and all(r['latency_ms']>0 and math.isfinite(r['latency_ms']) for r in records)
        errors=[r for r in records if r['error'] is not None or not 200<=r['status']<300];unexpected+=len(errors);raw_count+=len(records)
        values=[r['latency_ms'] for r in records]
        profile.append({'file':file.name,'n':len(values),'missing_latency':0,'errors':len(errors),'min_ms':min(values),**latency(values),'right_tail_ratio_max_to_median':max(values)/statistics.median(values)})
        if file.name.startswith('cache-'):
            for r in records:assert r['cache']==r['condition'];cache[r['condition']].append(r['latency_ms'])
    assert unexpected==0 and all(len(cache[k])==300 for k in cache)
    assert all(r['orders']==128 and r['accepted']==128 and r['invariant_pass'] for r in rows if r['kind']=='write')
    dump(run/'原始数据审计.json',{'formal_http_requests':raw_count,'unexpected_errors':unexpected,'profiles':profile,'files':checksum})
    if profile_helper:
        info=profile_helper(str(out/'round_summary.csv'),group_cols=['kind','version'])
        dump(run/'绘图数据剖析.json',info)
    qa={}
    def save(fig,name):
        fig.set_layout_engine(None)
        if len(fig.axes)==2:fig.subplots_adjust(left=.105,right=.975,bottom=.20,top=.86,wspace=.48)
        else:fig.subplots_adjust(left=.105,right=.98,bottom=.25 if name.startswith('03') else .20,top=.86)
        fig.canvas.draw()
        issues=audit_layout(fig) if audit_layout else []
        # 辅助审计会以 100 dpi 临时保存，须重画后再用当前 DPI 量边界。
        fig.canvas.draw();renderer=fig.canvas.get_renderer();bounds=fig.bbox
        clipped=[]
        # 对数轴会创建位于显示范围之外、实际不绘制的刻度标签。
        ticks={id(t) for ax in fig.axes for t in [*ax.get_xticklabels(),*ax.get_xticklabels(minor=True),*ax.get_yticklabels(),*ax.get_yticklabels(minor=True)]}
        for text in fig.findobj(matplotlib.text.Text):
            if id(text) in ticks or not text.get_visible() or not text.get_text().strip():continue
            b=text.get_window_extent(renderer)
            if b.x0 < -2 or b.y0 < -2 or b.x1 > bounds.width+2 or b.y1 > bounds.height+2:clipped.append(text.get_text())
        qa[name]={'helper_issues':issues,'fresh_same_dpi_text_bounds':'PASS' if not clipped else clipped}
        if any(severity=='FAIL' for severity,message in issues):raise RuntimeError('figure has missing glyphs')
        if clipped:raise RuntimeError('figure contains clipped text: '+repr(clipped))
        # 辅助器的灰度选项会用 tight 重写原 PNG；单独生成预览以保留固定尺寸。
        if exporter:exporter(fig,str(figures/name),formats=['png','svg','pdf'],size_inches=tuple(fig.get_size_inches()),dpi=300,grayscale_preview=False,tight=False)
        else:
            for fmt in ['png','svg','pdf']:fig.savefig(figures/(name+'.'+fmt),dpi=300)
        from PIL import Image
        Image.open(figures/(name+'.png')).convert('L').save(figures/(name+'_grayscale.png'),dpi=(300,300))
        plt.close(fig)
    def compare(ax,kind,metric,scale=1,log=False):
        for j,version in enumerate(VERSIONS):
            g=[next(x for x in grouped if x['kind']==kind and x['version']==version and x['condition']==c)['metrics'][metric] for c in [1,8,16]]
            xs=np.array([1,8,16])+(j-1)*.2;ys=np.array([x['median']/scale for x in g])
            low=[(x['median']-x['min'])/scale for x in g];high=[(x['max']-x['median'])/scale for x in g]
            ax.errorbar(xs,ys,yerr=[low,high],marker=MARKERS[j],color=COLORS[j],lw=.8,capsize=3,ms=4,label=LABELS[version])
            for x,group in zip(xs,g):ax.scatter([x-.08,x,x+.08],np.array(group['raw'])/scale,s=9,color=COLORS[j],alpha=.65,zorder=3)
        ax.set_xticks([1,8,16]);ax.set_xlabel('并发工作线程数');ax.grid(axis='y',alpha=.16)
        if log:ax.set_yscale('log')
        else:ax.set_ylim(bottom=0)
    fig,axes=plt.subplots(1,2,figsize=(6.8,3.2),layout='constrained')
    compare(axes[0],'read','response_rps');axes[0].set_ylabel('响应吞吐 / (请求/s)');axes[0].set_title('a  活动查询吞吐')
    compare(axes[1],'read','p95_ms');axes[1].set_ylabel('HTTP 响应 p95 / ms');axes[1].set_title('b  活动查询尾延迟')
    axes[0].legend(loc='upper left');save(fig,'01_活动查询对比')
    fig,axes=plt.subplots(1,2,figsize=(6.8,3.2),layout='constrained')
    compare(axes[0],'write','p95_ms');axes[0].set_ylabel('HTTP 响应 p95 / ms');axes[0].set_title('a  下单请求响应')
    compare(axes[1],'write','completion_p95_ms',scale=1000,log=True);axes[1].set_ylabel('订单完成观察 p95 / s（对数）');axes[1].set_title('b  已提交订单首次可见')
    axes[0].legend(loc='upper left');save(fig,'02_受理与最终完成延迟')
    fig,ax=plt.subplots(figsize=(6.8,3.2),layout='constrained');data=[cache['MISS'],cache['HIT']]
    boxes=ax.boxplot(data,positions=[1,2],widths=.35,showfliers=False,patch_artist=True,medianprops={'color':'#222222','linewidth':1.3})
    rng=np.random.default_rng(20261030)
    for i,(box,values,color) in enumerate(zip(boxes['boxes'],data,COLORS[:2]),1):
        box.set_facecolor(color);box.set_alpha(.28);ax.scatter(rng.normal(i,.035,len(values)),values,s=5,alpha=.25,color=color)
    ax.set_xticks([1,2],['MISS：每次先清键\nn=300（100×3 轮）','HIT：计时前已填充\nn=300（100×3 轮）']);ax.set_yscale('log');ax.set_ylabel('商品 HTTP 延迟 / ms（对数）');ax.set_title('缓存版商品接口：相同商品的冷/热路径');ax.grid(axis='y',alpha=.15);save(fig,'03_缓存命中与未命中')
    candidates=[x for x in rows if x['kind']=='write' and x['version']=='0.3.0-async' and x['concurrency']==16]
    chosen=sorted(candidates,key=lambda x:x['completion_seconds'])[1]
    trace=json.loads((run/'raw'/(chosen['name']+'-completion.json')).read_text(encoding='utf-8'))
    requests=[json.loads(line) for line in (run/'raw'/(chosen['name']+'-requests.jsonl')).read_text().splitlines()]
    origin=trace['start'];accepted=sorted(r['end']-origin for r in requests)
    fig,ax=plt.subplots(figsize=(6.8,3.2),layout='constrained')
    ax.step([0]+accepted,[0]+list(range(1,129)),where='post',color=COLORS[0],lw=1.3,label='收到 202 的请求累计数')
    ax.step([x['time']-origin for x in trace['trace']],[x['orders'] for x in trace['trace']],where='post',color=COLORS[1],lw=1.4,linestyle='--',label='首次可见的已提交订单数')
    ax.set_xlim(left=0);ax.set_ylim(0,135);ax.set_yticks([0,32,64,96,128]);ax.set_xlabel('自批次开始的时间 / s');ax.set_ylabel('累计数量 / 条');ax.set_title('异步版 128 请求：受理结束后仍需等待订单生成');ax.legend(loc='lower right');ax.grid(alpha=.15);save(fig,'04_异步请求完成轨迹')
    dump(run/'图表程序检查.json',qa)
    dump(out/'cache_summary.json',{k:latency(v) for k,v in cache.items()})
    dump(out/'provenance.json',{'run_id':manifest['run_id'],'driver_sha256':manifest.get('driver_sha256'),'mysql_probe':manifest.get('mysql_probe'),'created_at':manifest['created_at'],'completed_at':manifest['completed_at'],'artifacts':[{k:v for k,v in r.items() if k in ['tag','commit','jar_sha256','tests']} for r in manifest['artifacts']],'http_requests':raw_count,'error_count':unexpected,'formal_bursts':27,'formal_orders':3456,'functional_versions':3,'trajectory_round':chosen['name'],'system':manifest['system'],'environment':environment})
    def group(kind,version,c):return next(x for x in grouped if x['kind']==kind and x['version']==version and x['condition']==c)['metrics']
    query_table=['| 版本 | 并发 | 响应 RPS 中位数 [最小,最大] | HTTP p95 中位数 / ms |','| --- | --- | --- | --- |']
    post_table=['| 版本 | 并发 | 响应 p95 / ms | 完成观察 p95 / s | 响应 RPS | 完成观察吞吐 / 单·s⁻¹ |','| --- | --- | --- | --- | --- | --- |']
    resource_table=['| 版本（并发 16） | 应用 CPU 秒/批 | 应用最大 RSS / MiB | MySQL CPU 秒/批 | 施压器 CPU 秒/批 |','| --- | --- | --- | --- | --- |']
    for version in VERSIONS:
        for c in [1,8,16]:
            g=group('read',version,c);r=g['response_rps'];query_table.append(f"| {LABELS[version]} | {c} | {r['median']:.1f} [{r['min']:.1f}, {r['max']:.1f}] | {g['p95_ms']['median']:.2f} |")
            g=group('write',version,c);post_table.append(f"| {LABELS[version]} | {c} | {g['p95_ms']['median']:.2f} | {g['completion_p95_ms']['median']/1000:.3f} | {g['response_rps']['median']:.1f} | {g['completed_orders_per_second']['median']:.2f} |")
        g=group('write',version,16);resource_table.append(f"| {LABELS[version]} | {g['app_cpu_seconds']['median']:.3f} | {g['app_rss_mib_max']['median']:.1f} | {g.get('mysql_cpu_seconds',{}).get('median',float('nan')):.3f} | {g['generator_cpu_seconds']['median']:.3f} |")
    d=latency(cache['MISS']);h=latency(cache['HIT']);async_c=group('write','0.3.0-async',16);tests=sum(x['tests']['tests'] for x in manifest['artifacts']);system=manifest['system']
    report=f'''# 阶段 E：功能测试与性能分析

实际测试时间：{manifest['created_at']} 至 {manifest['completed_at']}。运行编号 {manifest['run_id']}。本机 Python 闭环施压，未使用 PTS 发起压测。

## 方法与可复现材料

测试条件在[固定方案](../阶段E固定测试方案.md)中于运行前确定。三个原始标签单独导出、重跑测试并构建：8/25/38 项全部通过，合计 {tests} 次测试执行，包含跨版本重复用例，并非 {tests} 个独立用例。

主机 {system['physical_cpus']} 核/{system['logical_cpus']} 逻辑处理器，内存 {system['total_memory_mib']/1024:.1f} GiB；Java 17，JVM 128–384 MiB，数据库池上限 12。MySQL 位于 Windows，Redis/RocketMQ 位于同机 WSL；施压器也在同机运行。全部组件实际版本、提交号、JAR 校验值见 provenance.json。每个版本/并发组合有 3 轮，版本与并发顺序轮换；查询预热 1 秒，每轮读 4 秒，写另预热 16 单，再以新活动发 128 请求。它是短时课程实验，不是稳态容量评估。

正式样本共 **{raw_count:,} 次 HTTP 请求**，覆盖 27 个查询窗口、27 个下单批次及 600 次缓存探测；不包含预热、功能矩阵、缓存控制请求和 SQL 观察。正式未知错误为 **0**。全部 27 个下单批次各 128 单，合计 **3456 单**，初始库存、剩余、订单和待处理请求核对通过。未删除长尾样本。

所有表格的“中位数”均先按轮次计算相应指标，再取 3 轮中位数；范围为实际最小至最大，不是置信区间。图中显示各轮原始点、中位数和最小/最大范围，连线仅帮助阅读测试档位，不用于外推。

## 功能与故障正确性

三个版本的正常下单、相同请求重试、重复购买、他人结果查询、未开始/结束/停用/售罄、参数错误均通过 HTTP 断言。各版的 32 请求抢 8 份库存均为 8 单、24 次售罄；同用户 16 个不同编号并发仅生成 1 单。

本阶段重跑异步版 38 项测试，其中真实 Broker 测试再次覆盖暂停消费后恢复、重复投递、注入发送异常后的补发、注入消费异常后的 Broker 重投。实际服务停止/恢复证据沿用阶段 D 同一源码的记录，未声称在本轮性能测量中再断开 Broker。确定失败与事务回滚也包含在回归中。

## 活动查询

{chr(10).join(query_table)}

![活动查询对比](figures/01_活动查询对比.png)

图 1：三个版本、1/8/16 并发，各 n=3 轮；范围为 min–max。此接口始终查询活动动态数据，缓存版增加商品缓存访问，异步版还计算待请求占用，三者并非只切换一个组件的纯因果消融。波动和访问路径都必须纳入解释，不能从部分轮次的差异推广生产性能。

## 下单响应与最终完成

{chr(10).join(post_table)}

![下单响应与最终完成](figures/02_受理与最终完成延迟.png)

图 2：每点 n=3 轮，每轮 128 个不同用户、128 份库存。左为完整 HTTP 响应，异步为 202 受理；右为数据库已提交订单第一次被观察到的延迟，纵轴为对数。SQL 每约 100 ms 轮询，因此右侧包含观察等待与查询时间，是提交完成延迟的上界，不能用于辨别小于该粒度的提交差异。

异步版并发 16 的受理 p95 中位数为 {async_c['p95_ms']['median']:.2f} ms，最终完成观察 p95 为 {async_c['completion_p95_ms']['median']/1000:.2f} s，固定批次完成观察吞吐为 {async_c['completed_orders_per_second']['median']:.2f} 单/s。受理和订单完成不能混为同一指标；当前配置没有证明异步化提高了下单性能。

![异步完成轨迹](figures/04_异步请求完成轨迹.png)

图 4：并发 16 中按整批完成时长居中的实际轮次（{chosen['name']}），128 个请求。蓝线为收到 202，橙线为已提交订单首次可见。阶梯与当前每约 2 秒扫描最多 20 条的后台发送策略相符；fixedDelay 还包含发送/数据库操作耗时，不能把 20/2 直接当实测吞吐。活动行锁、持久请求写入和每次重建资格 Hash 也增加受理工作。本轮保留默认策略，没有为获得更好图形而调参。

## 商品缓存路径

600 个计时样本按固定随机顺序交错；每条件 100×3 轮，全部响应头断言正确。MISS 前只删除本轮商品键，HIT 在计时前预填。控制操作不计入 HTTP 延迟，也没有据此报告 MISS 场景的 RPS。

| 条件 | n | HTTP p50 / ms | HTTP p95 / ms | 最大 / ms |
| --- | --- | --- | --- | --- |
| MISS | 300 | {d['p50_ms']:.3f} | {d['p95_ms']:.3f} | {d['max_ms']:.3f} |
| HIT | 300 | {h['p50_ms']:.3f} | {h['p95_ms']:.3f} | {h['max_ms']:.3f} |

![商品缓存探测](figures/03_缓存命中与未命中.png)

图 3：箱体为四分位范围，中线为中位数，须线 1.5×IQR；散点包含全部样本，含长尾，纵轴为对数。300 次请求不是 300 次独立环境重复实验。这里只比较同一缓存版的两条实际路径，不能从 HTTP 耗时直接推出数据库负载下降。

## 资源观察

下表为并发 16 下单时 3 轮的指标中位数。CPU 秒为该批次直至所有订单被观察完成的累计进程 CPU 时间，RSS 为该窗口最大工作集；同步与异步窗口长短不同，不能直接比较平均利用率。

{chr(10).join(resource_table)}

原始文件还保留约 200 ms 间隔的主机 CPU/可用内存、进程 CPU/RSS 和施压器资源。MySQL 按实际监听端口唯一定位 PID，逐样本保存身份；首轮按进程名称选取时误取了监护进程，该轮原始文件保留但 MySQL CPU 无效。本报告使用修正探针后完整重采的一轮，不混入原轮性能值。进程 CPU 百分比以单核 100% 计，可超过 100%。应用进程不包含 WSL 内 Broker/Redis 的全部成本；MySQL CPU 是进程级观察，不能归因到某一 SQL，更不等于每个接口的数据库读取次数。采样可能遗漏极短峰值。

## 可支持的结论与限制

1. 三个版本在本次场景中均满足库存和购买约束，异步已受理请求全部有终态；这是有限功能验证。
2. 当前异步受理仍依赖数据库活动锁与逐次资格重建，默认 Outbox 的小批次和间隔造成可见等待，未观察到“引入 MQ 就必然更快”的证据。
3. 活动查询结果与商品缓存探测分别解释。小商品、快速本机 MySQL、额外 Redis 往返、JVM 预热及同机负载都会影响结果；不预设缓存收益。
4. n=3 且每窗口仅 4 秒、预热较短、同机施压、闭环等待偏差、数据表随测试增长及后台任务均限制外推。没有控制操作系统缓存、温度/频率或其他桌面应用，也未消除施压器瓶颈。
5. 没有稳定目标 RPS/饱和点搜索、长时间浸泡、多机、故障期间性能或 ECS/云产品性能结果。后续若优化，应建立新版本并固定方案另测，不改写本轮原始结果。

PTS 已完成[官方压力模型](https://help.aliyun.com/zh/pts/performance-test-pts-3-0/user-guide/pressure-model)和[报告指标](https://www.alibabacloud.com/help/zh/pts/performance-test-pts-3-0/user-guide/check-pts-3-report)资料学习；本轮使用 Python，不是 PTS 报告。HTTP 202 仅能证明请求受理，PTS 业务检查点也应另查订单完成。

## 复现与文件

先准备本机环境并停止演示应用，再运行 tests/prepare_benchmark.py 导出构建，tests/benchmark.py 执行。完整命令见 tests/README.md。round_summary.csv 为 60 个分组，grouped_summary.json 保存三轮点和聚合，provenance.json 记录版本和条件；原始数据在项目外本次运行目录。图形同时导出 PNG 300 dpi、可编辑文字 SVG 和嵌入字体 PDF，绘图代码为 tests/analyze_benchmark.py。

原始库存、订单、请求按本次清单保存后才清理，展示数据须逐行与测试前一致，再恢复本机异步演示。清理执行情况以 cleanup-result.json 和阶段 E 完成记录为准，不根据本报告的生成推断清理已经执行。
'''
    # 按正文出现顺序放置四幅图，轨迹独立成节。
    begin=report.index('![异步完成轨迹]');end=report.index('## 商品缓存路径',begin)
    trajectory_block=report[begin:end];report=report[:begin]+report[end:]
    report=report.replace('## 资源观察','## 异步完成轨迹\n\n'+trajectory_block+'## 资源观察')
    (out/'性能分析.md').write_text(report,encoding='utf-8')
    print(json.dumps({'formal_requests':raw_count,'unknown_errors':unexpected,'groups':len(rows),'figures':4,'qa':qa},ensure_ascii=False))
if __name__=='__main__':main()
