# 统一术语表

本表登记 Training Viewer 文档、界面与代码中首次出现的技术缩写。界面优先使用完整中文名称；英文标识只用于代码和协议字段。

## 1. 项目核心概念

| 术语 | 完整名称 / 中文含义 | 在本项目中的作用 |
|---|---|---|
| Project（项目） | 项目 | 多个相关实验的上层归档，来自 `run.json.project` |
| Experiment（实验组） | 实验组 | 围绕同一问题或消融维度的一组运行，来自 `run.json.experiment` |
| Run（运行） | 单次运行 | 一次独立训练/评估，由全局唯一 `run_id` 标识；可包含多次恢复训练 |
| Session（会话） | 执行会话 | 训练进程一次启动到退出的时间段，来自 `session_id`；断点续训产生新会话 |
| Phase（阶段） | 训练阶段 | 指标所属阶段，例如 `train`、`val`、`test`；界面显示原文并标注“阶段” |
| Metric（指标） | 指标 | 连续记录的数值结果，例如 Loss、mIoU、学习率 |
| Artifact（产物） | 实验产物 | 图像、表格、HTML、模型等非标量结果 |
| Step（优化步） | 优化器更新次数 | `global_step`；累计模型参数更新次数，恢复训练时不应回退 |
| Epoch（训练轮次） | 训练轮次 | 数据集完整遍历一次；从 1 开始计数 |
| Checkpoint（检查点） | 训练检查点 | 保存并恢复训练状态的文件；查看器只作为产物引用，不加载 |
| `run_id` | 运行唯一标识 | 协议字段。用 UUID 生成，不随目录移动改变 |
| `session_id` | 执行会话标识 | 协议字段。每次训练进程启动生成新值 |

## 2. 日志协议与数据格式

| 缩写 / 词 | 完整名称 / 中文含义 | 在本项目中的作用 |
|---|---|---|
| TVLP | Training Viewer Log Protocol，训练日志协议 | 本项目定义的稳定日志格式，当前版本 1.0 |
| Schema | 结构定义 | `schemas/*.schema.json` 用 JSON Schema Draft 2020-12 描述协议字段 |
| JSON | JavaScript Object Notation，JSON 数据格式 | 元数据与事件记录的文本格式 |
| JSONL | JSON Lines，逐行 JSON | 每行一个独立 JSON 对象；指标与事件日志使用此格式 |
| CSV | Comma-Separated Values，逗号分隔值 | 指标表和表格产物的常见格式 |
| TSV | Tab-Separated Values，制表符分隔值 | 表格预览支持的另一种分隔格式 |
| RFC 3339 | 互联网日期时间格式标准 | `timestamp` 必须带时区，推荐 UTC `Z` |
| UTC | Coordinated Universal Time，协调世界时 | 查看器内部统一使用 UTC 存储，界面按浏览器本地时区显示 |
| JSONL offset | 字节偏移 | 记录已消费位置，用于断点续读和幂等导入 |
| WAL | Write-Ahead Logging，预写式日志 | SQLite 的一种日志模式，提高读写并发能力 |

## 3. 系统组件

| 缩写 / 词 | 完整名称 / 中文含义 | 在本项目中的作用 |
|---|---|---|
| Source Adapter（适配器） | 日志来源适配器 | 把一种日志源转换为统一记录，例如 TensorBoard、CSV |
| Writer | 日志写入器 | 训练程序侧的 `TrainingRunWriter`，创建标准 Run 并追加指标/事件；不启动服务 |
| attach | 接入 / 挂载 | `training-viewer attach` 把日志目录注册到后台查看器并返回 URL |
| detached process | 脱离终端会话的后台进程 | `attach` 用它启动服务，Agent 退出后仍可浏览 |
| Normalizer | 数据标准化器 | 把来源记录统一为指标/事件/产物对象；本项目由读取器与索引器共同完成 |
| Indexer | 索引器 | 把新日志写入 SQLite 查询索引 |
| Reader | 读取器 | 只读取文件新增内容并产出标准化记录 |
| Cursor | 文件游标 | 记录文件身份、大小、偏移、行号/事件序号 |
| Scanner | 目录扫描器 | 从根目录递归发现 Run |
| Index Queries | 索引查询层 | 为页面与导出提供运行列表、曲线、对比、诊断 |
| Service | 应用服务 | 协调扫描、索引、状态刷新、SSE 通知 |
| SSE | Server-Sent Events，服务器发送事件 | 服务端向浏览器单向推送“有新数据”的轻量通知 |
| REST | Representational State Transfer，表述性状态转移 | 前后端 HTTP 接口风格 |
| API | Application Programming Interface，应用程序编程接口 | 本项目的 `/api/v1/*` 接口 |
| SDK | Software Development Kit，软件开发工具包 | 可选的训练日志写入辅助库；V1 未提供，训练程序可直接写文件 |
| CLI | Command-Line Interface，命令行界面 | `training-viewer` 命令 |
| UI | User Interface，用户界面 | 浏览器页面 |
| VS Code | Visual Studio Code，代码编辑器 | 通过扩展提供启动入口 |
| VSIX | VS Code Extension Package，VS Code 扩展安装包 | 本项目的 `training-viewer-vscode-1.0.0.vsix` |
| ECharts | Apache ECharts，图表库 | 前端曲线、缩放、PNG/SVG 导出 |
| FastAPI | Python Web 框架 | 提供 REST、SSE 与静态资源 |
| SQLite | 嵌入式关系数据库 | 保存可重建索引与界面数据 |
| Uvicorn | Python ASGI 服务器 | 运行 FastAPI 应用 |
| watchdog | 文件系统事件库 | 提前唤醒扫描；轮询仍是正确性保证 |

## 4. 指标与算法

| 缩写 / 词 | 完整名称 / 中文含义 | 在本项目中的作用 |
|---|---|---|
| Loss | 损失函数值 | 训练/验证损失；具体计算由训练程序定义 |
| mIoU | mean Intersection over Union，平均交并比 | 语义分割指标；类别集合、忽略索引和平均方式必须由 `metric_definitions` 说明 |
| IoU | Intersection over Union，交并比 | 单类别预测区域与真实区域的重合程度 |
| F1 | F1 score，F1 分数 | 精确率与召回率的调和平均；宏/微平均方式需声明 |
| Accuracy | 准确率 | 分类任务中预测正确的比例 |
| LR | Learning Rate，学习率 | 优化器超参数；旧日志可保留 `lr` 键 |
| EMA | Exponential Moving Average，指数移动平均 | 前端曲线平滑方法之一，仅影响显示 |
| Moving Average | 移动平均 | 前端曲线平滑方法之一，仅影响显示 |
| LTTB | Largest-Triangle-Three-Buckets，三角面积采样 | 曲线降采样算法之一；本项目实际使用最小-最大分桶 |
| Min-Max Bucket | 最小-最大分桶 | 每个分桶保留首尾、最小值、最大值，优先保留极值 |
| Best | 最佳值 | 按指标方向在全部原始采样中取得的最优值，不使用平滑/抽样点 |
| Last | 最终值 | 最新有效时间序列记录 |
| direction | 优化方向 | `min`、`max` 或 `none`；没有方向时不能自动评优 |
| unit | 数据单位 | `ratio`、`percent`、`ms` 等精确数据单位，不是显示格式 |
| comparison_key | 比较键 | 用户声明的指标可比性分组键 |

## 5. 安全与其他

| 缩写 / 词 | 完整名称 / 中文含义 | 在本项目中的作用 |
|---|---|---|
| UUID | Universally Unique Identifier，通用唯一标识符 | 推荐生成 `run_id` 的方式 |
| HTML | HyperText Markup Language，超文本标记语言 | 可作为产物；默认按不可信文本附件返回，不执行脚本 |
| SVG | Scalable Vector Graphics，可缩放矢量图形 | 图表导出格式；产物默认不内联执行 |
| PNG | Portable Network Graphics，便携式网络图形 | 图表导出格式；常见预测图格式 |
| DDP | Distributed Data Parallel，分布式数据并行 | 多进程训练；建议只由 rank 0 写日志 |
| Host / Origin | HTTP 请求头 | 用于拒绝非本机访问和外部网站跨域请求 |
| CSRF | Cross-Site Request Forgery，跨站请求伪造 | 本机 API 通过 Host/Origin 校验降低风险 |
| CSP | Content Security Policy，内容安全策略 | 产物响应头设置 `sandbox`，限制脚本执行 |
| MIME | Multipurpose Internet Mail Extensions，媒体类型 | 产物内容类型；只对白名单位图内联返回 |
| entry point | Python 包入口点 | 第三方来源/导出器的安装式扩展机制 |
| rank 0 | 主进程 | 多进程训练中建议唯一写日志的进程 |

## 6. 统一命名约定

| 场景 | 约定 | 示例 |
|---|---|---|
| Python 文件 | 小写英文 + 下划线 | `standard_training_log_reader.py` |
| Python 类 | 大驼峰 | `TrainingMetricIndexer` |
| Python 函数 | 小写英文 + 下划线 | `read_new_records()` |
| React 组件 | 大驼峰 | `ExperimentComparisonPage` |
| TypeScript 函数 | 小驼峰 | `groupMetricsByTrainingPhase()` |
| 协议字段 | 保持已冻结的 `snake_case` | `run_id`、`global_step`、`session_id` |
| 界面名称 | 完整中文 | “实验对比”“预测结果对照” |
| 实验名称 | 模型 + 关键变量 + 种子 | `SegFormer 波长条件化输入｜10 波段｜随机种子 43` |

禁止使用 `ModuleV2`、`ParserV3`、`NewAdapter`、`helper2`、`final_final` 等不能表达职责的名称。软件版本、协议版本、组件名称、实验名称是四种独立标识，不能混用。
