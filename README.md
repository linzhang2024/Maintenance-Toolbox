# Maintenance-Toolbox

# Maintenance-Toolbox

实施运维百宝箱 - 一个用于医院信息系统(HIS)的智能化运维巡检工具，提供环境扫描、接口巡检、日志诊断等功能，并生成可视化HTML报告。
Maintenance-Toolbox/
├── main.py          # 主程序入口
├── checker.py       # 核心检查模块
├── logger.py        # 日志诊断模块
├── utils.py         # 工具函数模块
├── config.json      # 配置文件
└── README.md

1. 配置文件 (config.json) 结构要求：

包含 database 配置（IP, Port, ServiceName, User, Pwd）。

包含 api_list（需要测试的接口 URL 列表及预期返回码）。

包含 log_rules（日志存放目录、需要监控的关键字如 ORA-, ERROR, Timeout）。

包含 env_check（磁盘阈值、时间同步服务器等）。

2. 核心功能模块：

环境扫描模块：检查本地与数据库的时间差、检查磁盘空间、检查 tj_xtsz_xtbl 表中关键变量（如：‘JMPDF导出地址’）是否正确。

接口巡检模块：使用 requests 库并发测试配置文件中的所有 API。如果接口失败，记录下失败时间。

智能日志诊断模块：如果上述接口失败或数据库连接异常，自动根据配置的路径扫描相关日志。提取错误前后的 10 行上下文，并根据预设的字典（如 ORA-12541 对应‘监听未启动’）匹配实施建议。

3. 交互与输出：

脚本启动时，先检查 config.json 是否存在，不存在则初始化一个默认模板。

运行后，生成一个交互式的 HTML 报告 inspection_report.html，用颜色标记各项任务的健康状态（绿色、橙色、红色）。

4. 技术要求：

使用 Python 编写，要求代码解耦，分为 main.py、checker.py、logger.py 和 utils.py。

处理大日志文件时要考虑内存效率（使用生成器读取）。

必须处理中文 GBK 编码兼容性问题（HIS 系统的常见问题）。”
