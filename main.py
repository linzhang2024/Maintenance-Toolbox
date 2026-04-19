#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HIS 实施辅助工具套件 - 主程序入口
"""

import os
import sys
import argparse
from datetime import datetime
from typing import Dict, Any, List

from utils import ConfigManager, Status, get_status_color, get_status_text, format_timestamp
from checker import EnvironmentScanner, ApiChecker, DatabaseChecker, CheckResult
from logger import LogAnalyzer


class HISHelperTool:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config_manager = ConfigManager(config_path)
        self.config = None
        self.results = {}
        self.log_analyzer = None
        self.html_report = None
    
    def initialize(self) -> bool:
        print(f"{'='*60}")
        print(f"      HIS 实施辅助工具套件 v1.0")
        print(f"{'='*60}")
        print(f"[{format_timestamp()}] 初始化...")
        
        if not os.path.exists(self.config_path):
            print(f"[{format_timestamp()}] 配置文件不存在，正在创建默认配置...")
            self.config_manager.init_default()
            print(f"[{format_timestamp()}] 已创建默认配置文件: {self.config_path}")
            print(f"请编辑配置文件后重新运行。")
            return False
        
        try:
            self.config = self.config_manager.load()
            self.log_analyzer = LogAnalyzer(self.config)
            print(f"[{format_timestamp()}] 配置加载成功")
            return True
        except Exception as e:
            print(f"[{format_timestamp()}] 配置加载失败: {e}")
            return False
    
    def run_all_checks(self):
        print(f"\n{'='*60}")
        print(f"      开始执行检查任务")
        print(f"{'='*60}")
        
        self.results = {
            'run_time': format_timestamp(),
            'environment': {},
            'database': {},
            'api': {},
            'log': {}
        }
        
        self._check_environment()
        self._check_database()
        self._check_api()
        self._trigger_log_analysis()
        
        print(f"\n{'='*60}")
        print(f"      检查任务完成")
        print(f"{'='*60}")
    
    def _check_environment(self):
        print(f"\n[{format_timestamp()}] [环境检查] 开始...")
        
        scanner = EnvironmentScanner(self.config)
        env_results = scanner.check_all()
        
        self.results['environment'] = {
            name: self._result_to_dict(result)
            for name, result in env_results.items()
        }
        
        for name, result in env_results.items():
            status_color = self._get_status_console_color(result.status)
            status_text = get_status_text(result.status)
            print(f"  {status_color}[{status_text}] {result.name}: {result.message}")
        
        print(f"[{format_timestamp()}] [环境检查] 完成")
    
    def _check_database(self):
        print(f"\n[{format_timestamp()}] [数据库检查] 开始...")
        
        db_checker = DatabaseChecker(self.config)
        
        conn_result = db_checker.check_connection()
        time_result = db_checker.check_time_diff()
        
        self.results['database'] = {
            'connection': self._result_to_dict(conn_result),
            'time_diff': self._result_to_dict(time_result)
        }
        
        for name, result in [('connection', conn_result), ('time_diff', time_result)]:
            status_color = self._get_status_console_color(result.status)
            status_text = get_status_text(result.status)
            print(f"  {status_color}[{status_text}] {result.name}: {result.message}")
        
        print(f"[{format_timestamp()}] [数据库检查] 完成")
    
    def _check_api(self):
        print(f"\n[{format_timestamp()}] [接口巡检] 开始...")
        
        api_checker = ApiChecker(self.config)
        api_results = api_checker.check_all()
        
        self.results['api'] = {
            name: self._result_to_dict(result)
            for name, result in api_results.items()
        }
        
        summary = api_results.get('summary')
        if summary:
            status_color = self._get_status_console_color(summary.status)
            status_text = get_status_text(summary.status)
            print(f"  {status_color}[{status_text}] {summary.message}")
            
            for name, result in api_results.items():
                if name != 'summary':
                    status_color = self._get_status_console_color(result.status)
                    status_text = get_status_text(result.status)
                    print(f"    {status_color}[{status_text}] {name}: {result.message}")
        
        print(f"[{format_timestamp()}] [接口巡检] 完成")
    
    def _trigger_log_analysis(self):
        print(f"\n[{format_timestamp()}] [日志诊断] 检查触发条件...")
        
        should_scan = False
        trigger_type = 'manual'
        trigger_message = '正常扫描'
        
        api_results = self.results.get('api', {})
        api_summary = api_results.get('summary', {})
        if api_summary.get('status') in [Status.ERROR, Status.WARNING]:
            should_scan = True
            trigger_type = 'api_failure'
            trigger_message = '接口巡检发现异常'
        
        db_results = self.results.get('database', {})
        for name, result in db_results.items():
            if result.get('status') in [Status.ERROR, Status.WARNING]:
                should_scan = True
                trigger_type = 'database_failure'
                trigger_message = '数据库检查发现异常'
                break
        
        if should_scan:
            print(f"[{format_timestamp()}] [日志诊断] 触发条件满足，开始扫描日志...")
            print(f"  触发原因: {trigger_message}")
            
            log_result = self.log_analyzer.analyze_triggered(trigger_type, trigger_message)
            self.results['log'] = log_result
            
            scan_result = log_result.get('scan_result', {})
            findings_count = scan_result.get('findings_count', 0)
            
            if findings_count > 0:
                print(f"[{format_timestamp()}] [日志诊断] 发现 {findings_count} 个异常")
                for finding in scan_result.get('findings', []):
                    print(f"  - {finding['file_name']}:{finding['line_number']} - {finding['matched_keyword']}")
                    if finding.get('suggestion'):
                        print(f"    建议: {finding['suggestion']}")
            else:
                print(f"[{format_timestamp()}] [日志诊断] 未发现异常")
        else:
            print(f"[{format_timestamp()}] [日志诊断] 无触发条件，跳过日志扫描")
            self.results['log'] = {
                'trigger_type': 'none',
                'trigger_message': '无触发条件',
                'trigger_time': format_timestamp(),
                'scan_result': None
            }
    
    def generate_html_report(self, output_path: str = "inspection_report.html"):
        print(f"\n[{format_timestamp()}] 生成 HTML 报告...")
        
        html_content = self._build_html_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.html_report = output_path
        print(f"[{format_timestamp()}] 报告已生成: {os.path.abspath(output_path)}")
    
    def _build_html_report(self) -> str:
        overall_status = self._calculate_overall_status()
        status_color = get_status_color(overall_status)
        status_text = get_status_text(overall_status)
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HIS 实施辅助工具 - 巡检报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header .status-badge {{
            display: inline-block;
            padding: 8px 24px;
            border-radius: 50px;
            font-size: 18px;
            font-weight: bold;
            background: {status_color};
            color: white;
        }}
        .header .meta {{
            margin-top: 15px;
            opacity: 0.8;
            font-size: 14px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        .summary-card:hover {{ transform: translateY(-5px); }}
        .summary-card .number {{
            font-size: 36px;
            font-weight: bold;
        }}
        .summary-card .label {{
            font-size: 14px;
            color: #6c757d;
            margin-top: 8px;
        }}
        .section {{
            padding: 30px;
            border-bottom: 1px solid #eee;
        }}
        .section:last-child {{ border-bottom: none; }}
        .section h2 {{
            font-size: 20px;
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            display: inline-block;
        }}
        .result-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
            border-left: 4px solid;
        }}
        .result-card.ok {{ border-left-color: #28a745; }}
        .result-card.warning {{ border-left-color: #ffc107; }}
        .result-card.error {{ border-left-color: #dc3545; }}
        .result-card.skipped {{ border-left-color: #6c757d; }}
        .result-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .result-name {{
            font-weight: bold;
            font-size: 16px;
        }}
        .result-status {{
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            color: white;
        }}
        .result-status.ok {{ background: #28a745; }}
        .result-status.warning {{ background: #ffc107; }}
        .result-status.error {{ background: #dc3545; }}
        .result-status.skipped {{ background: #6c757d; }}
        .result-message {{
            color: #495057;
            font-size: 14px;
        }}
        .details-toggle {{
            cursor: pointer;
            color: #667eea;
            font-size: 12px;
            margin-top: 8px;
            user-select: none;
        }}
        .details-content {{
            display: none;
            margin-top: 12px;
            padding: 12px;
            background: white;
            border-radius: 6px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .details-content.show {{ display: block; }}
        .log-finding {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .log-finding-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .log-finding .keyword {{
            background: #dc3545;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .log-context {{
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px;
            border-radius: 6px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
            overflow-x: auto;
        }}
        .log-context .highlight {{
            background: #dc3545;
            color: white;
            padding: 2px 4px;
            border-radius: 2px;
        }}
        .suggestion {{
            background: #d4edda;
            color: #155724;
            padding: 12px;
            border-radius: 6px;
            margin-top: 10px;
            border-left: 4px solid #28a745;
        }}
        .suggestion-title {{
            font-weight: bold;
            margin-bottom: 4px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-size: 12px;
            background: #f8f9fa;
        }}
        .api-list {{ margin-top: 10px; }}
        .api-item {{
            padding: 10px 15px;
            background: white;
            border-radius: 6px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .api-name {{ font-weight: bold; }}
        .api-url {{
            color: #6c757d;
            font-size: 12px;
            font-family: monospace;
        }}
        .disk-list {{ margin-top: 10px; }}
        .disk-item {{
            padding: 12px 15px;
            background: white;
            border-radius: 6px;
            margin-bottom: 8px;
        }}
        .disk-path {{ font-weight: bold; }}
        .disk-bar {{
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            margin-top: 8px;
            overflow: hidden;
        }}
        .disk-bar-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s;
        }}
        .disk-info {{
            display: flex;
            justify-content: space-between;
            margin-top: 4px;
            font-size: 12px;
            color: #6c757d;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 HIS 实施辅助工具 - 巡检报告</h1>
            <div class="status-badge">{status_text}</div>
            <div class="meta">
                生成时间: {self.results.get('run_time', '未知')} |
                配置文件: {self.config_path}
            </div>
        </div>
        
        <div class="summary">
            {self._build_summary_cards()}
        </div>
        
        {self._build_environment_section()}
        {self._build_database_section()}
        {self._build_api_section()}
        {self._build_log_section()}
        
        <div class="footer">
            HIS 实施辅助工具套件 v1.0 | 报告生成于 {self.results.get('run_time', '未知')}
        </div>
    </div>
    
    <script>
        document.querySelectorAll('.details-toggle').forEach(toggle => {{
            toggle.addEventListener('click', function() {{
                const content = this.nextElementSibling;
                content.classList.toggle('show');
                this.textContent = content.classList.contains('show') ? '收起详情 ▲' : '查看详情 ▼';
            }});
        }});
    </script>
</body>
</html>"""
        
        return html
    
    def _build_summary_cards(self) -> str:
        env_ok = 0
        env_total = 0
        for name, result in self.results.get('environment', {}).items():
            if result.get('status') != Status.SKIPPED:
                env_total += 1
                if result.get('status') == Status.OK:
                    env_ok += 1
        
        db_ok = 0
        db_total = 0
        for name, result in self.results.get('database', {}).items():
            if result.get('status') != Status.SKIPPED:
                db_total += 1
                if result.get('status') == Status.OK:
                    db_ok += 1
        
        api_ok = 0
        api_total = 0
        api_results = self.results.get('api', {})
        for name, result in api_results.items():
            if name != 'summary' and result.get('status') != Status.SKIPPED:
                api_total += 1
                if result.get('status') == Status.OK:
                    api_ok += 1
        
        log_findings = 0
        log_result = self.results.get('log', {})
        scan_result = log_result.get('scan_result', {})
        if scan_result:
            log_findings = scan_result.get('findings_count', 0)
        
        cards = f"""
            <div class="summary-card">
                <div class="number" style="color: #28a745;">{env_ok}/{env_total}</div>
                <div class="label">环境检查 (正常/总)</div>
            </div>
            <div class="summary-card">
                <div class="number" style="color: #667eea;">{db_ok}/{db_total}</div>
                <div class="label">数据库检查 (正常/总)</div>
            </div>
            <div class="summary-card">
                <div class="number" style="color: #17a2b8;">{api_ok}/{api_total}</div>
                <div class="label">接口巡检 (正常/总)</div>
            </div>
            <div class="summary-card">
                <div class="number" style="color: {'#dc3545' if log_findings > 0 else '#28a745'};">{log_findings}</div>
                <div class="label">日志异常数</div>
            </div>
        """
        return cards
    
    def _build_environment_section(self) -> str:
        env_results = self.results.get('environment', {})
        if not env_results:
            return ''
        
        disk_html = ''
        other_html = ''
        
        for name, result in env_results.items():
            if name == 'disk' and result.get('details', {}).get('disks'):
                disks = result['details']['disks']
                disk_items = ''
                for disk in disks:
                    percent = disk['percent_used']
                    color = '#28a745' if percent < 70 else ('#ffc107' if percent < 85 else '#dc3545')
                    disk_items += f"""
                        <div class="disk-item">
                            <div class="disk-path">{disk['path']}</div>
                            <div class="disk-bar">
                                <div class="disk-bar-fill" style="width: {percent}%; background: {color};"></div>
                            </div>
                            <div class="disk-info">
                                <span>已用: {disk['used_human']}</span>
                                <span>剩余: {disk['free_human']}</span>
                                <span style="color: {color};">{percent}%</span>
                            </div>
                        </div>
                    """
                disk_html = f"""
                    <div class="result-card {result['status']}">
                        <div class="result-header">
                            <span class="result-name">{result['name']}</span>
                            <span class="result-status {result['status']}">{get_status_text(result['status'])}</span>
                        </div>
                        <div class="result-message">{result['message']}</div>
                        <div class="disk-list">{disk_items}</div>
                    </div>
                """
            else:
                status_class = result['status']
                other_html += f"""
                    <div class="result-card {status_class}">
                        <div class="result-header">
                            <span class="result-name">{result['name']}</span>
                            <span class="result-status {status_class}">{get_status_text(result['status'])}</span>
                        </div>
                        <div class="result-message">{result['message']}</div>
                        {self._build_details_html(result)}
                    </div>
                """
        
        return f"""
        <div class="section">
            <h2>🌍 环境检查</h2>
            {disk_html}
            {other_html}
        </div>
        """
    
    def _build_database_section(self) -> str:
        db_results = self.results.get('database', {})
        if not db_results:
            return ''
        
        items_html = ''
        for name, result in db_results.items():
            status_class = result['status']
            items_html += f"""
                <div class="result-card {status_class}">
                    <div class="result-header">
                        <span class="result-name">{result['name']}</span>
                        <span class="result-status {status_class}">{get_status_text(result['status'])}</span>
                    </div>
                    <div class="result-message">{result['message']}</div>
                    {self._build_details_html(result)}
                </div>
            """
        
        return f"""
        <div class="section">
            <h2>🗄️ 数据库检查</h2>
            {items_html}
        </div>
        """
    
    def _build_api_section(self) -> str:
        api_results = self.results.get('api', {})
        if not api_results:
            return ''
        
        summary = api_results.get('summary', {})
        if not summary:
            return ''
        
        status_class = summary['status']
        api_list_html = ''
        
        for name, result in api_results.items():
            if name == 'summary':
                continue
            api_status = result['status']
            details = result.get('details', {})
            api_list_html += f"""
                <div class="api-item">
                    <div>
                        <div class="api-name">{name}</div>
                        <div class="api-url">{details.get('url', 'N/A')}</div>
                    </div>
                    <span class="result-status {api_status}">{get_status_text(api_status)}</span>
                </div>
            """
        
        return f"""
        <div class="section">
            <h2>🌐 接口巡检</h2>
            <div class="result-card {status_class}">
                <div class="result-header">
                    <span class="result-name">{summary['name']}</span>
                    <span class="result-status {status_class}">{get_status_text(summary['status'])}</span>
                </div>
                <div class="result-message">{summary['message']}</div>
                <div class="api-list">{api_list_html}</div>
            </div>
        </div>
        """
    
    def _build_log_section(self) -> str:
        log_result = self.results.get('log', {})
        scan_result = log_result.get('scan_result', {})
        
        if not scan_result:
            return f"""
        <div class="section">
            <h2>📝 日志诊断</h2>
            <div class="result-card skipped">
                <div class="result-header">
                    <span class="result-name">日志扫描</span>
                    <span class="result-status skipped">跳过</span>
                </div>
                <div class="result-message">{log_result.get('trigger_message', '无触发条件')}</div>
            </div>
        </div>
        """
        
        status_class = scan_result.get('status', Status.OK)
        findings = scan_result.get('findings', [])
        
        findings_html = ''
        for finding in findings:
            context_html = ''
            for line in finding.get('context', []):
                if '>>>' in line:
                    context_html += f'<span class="highlight">{line}</span>\n'
                else:
                    context_html += f'{line}\n'
            
            suggestion_html = ''
            if finding.get('suggestion'):
                suggestion_html = f"""
                    <div class="suggestion">
                        <div class="suggestion-title">💡 实施建议</div>
                        <div>{finding['suggestion']}</div>
                    </div>
                """
            
            findings_html += f"""
                <div class="log-finding">
                    <div class="log-finding-header">
                        <div>
                            <strong>{finding['file_name']}</strong>:{finding['line_number']}
                        </div>
                        <span class="keyword">{finding['matched_keyword']}</span>
                    </div>
                    <div class="result-message">{finding['line_content']}</div>
                    <div class="details-toggle">查看上下文 ▼</div>
                    <div class="details-content">
                        <div class="log-context">{context_html}</div>
                    </div>
                    {suggestion_html}
                </div>
            """
        
        return f"""
        <div class="section">
            <h2>📝 日志诊断</h2>
            <div class="result-card {status_class}">
                <div class="result-header">
                    <span class="result-name">日志扫描结果</span>
                    <span class="result-status {status_class}">{get_status_text(status_class)}</span>
                </div>
                <div class="result-message">
                    扫描文件: {scan_result.get('scanned_files', 0)} / {scan_result.get('total_files', 0)} |
                    发现异常: {scan_result.get('findings_count', 0)}
                </div>
                <div class="details-toggle">触发原因 ▼</div>
                <div class="details-content">
触发类型: {log_result.get('trigger_type', 'N/A')}
触发原因: {log_result.get('trigger_message', 'N/A')}
触发时间: {log_result.get('trigger_time', 'N/A')}
                </div>
            </div>
            {findings_html}
        </div>
        """
    
    def _build_details_html(self, result: Dict[str, Any]) -> str:
        details = result.get('details', {})
        if not details:
            return ''
        
        import json
        details_json = json.dumps(details, ensure_ascii=False, indent=2)
        
        return f"""
            <div class="details-toggle">查看详情 ▼</div>
            <div class="details-content">{details_json}</div>
        """
    
    def _calculate_overall_status(self) -> str:
        has_error = False
        has_warning = False
        
        for category in ['environment', 'database', 'api']:
            for name, result in self.results.get(category, {}).items():
                status = result.get('status', '')
                if status == Status.ERROR:
                    has_error = True
                elif status == Status.WARNING:
                    has_warning = True
        
        log_result = self.results.get('log', {})
        scan_result = log_result.get('scan_result', {})
        if scan_result and scan_result.get('findings_count', 0) > 0:
            has_warning = True
        
        if has_error:
            return Status.ERROR
        elif has_warning:
            return Status.WARNING
        else:
            return Status.OK
    
    def _get_status_console_color(self, status: str) -> str:
        color_map = {
            Status.OK: '\033[92m',
            Status.WARNING: '\033[93m',
            Status.ERROR: '\033[91m',
            Status.SKIPPED: '\033[90m'
        }
        return color_map.get(status, '\033[0m')
    
    def _result_to_dict(self, result: CheckResult) -> Dict[str, Any]:
        return {
            'name': result.name,
            'status': result.status,
            'message': result.message,
            'details': result.details,
            'timestamp': result.timestamp,
            'error': result.error
        }


def main():
    parser = argparse.ArgumentParser(
        description='HIS 实施辅助工具套件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                           # 使用默认配置运行所有检查
  python main.py -c my_config.json         # 使用指定配置文件
  python main.py --init-config             # 仅初始化配置文件
        '''
    )
    
    parser.add_argument(
        '-c', '--config',
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='inspection_report.html',
        help='输出报告路径 (默认: inspection_report.html)'
    )
    
    parser.add_argument(
        '--init-config',
        action='store_true',
        help='仅初始化配置文件，不执行检查'
    )
    
    args = parser.parse_args()
    
    tool = HISHelperTool(config_path=args.config)
    
    if args.init_config:
        tool.config_manager.init_default()
        print(f"配置文件已初始化: {args.config}")
        return
    
    if not tool.initialize():
        return
    
    tool.run_all_checks()
    tool.generate_html_report(output_path=args.output)
    
    print(f"\n{'='*60}")
    print(f"      任务完成总结")
    print(f"{'='*60}")
    
    overall_status = tool._calculate_overall_status()
    status_color = tool._get_status_console_color(overall_status)
    print(f"整体状态: {status_color}{get_status_text(overall_status)}\033[0m")
    print(f"HTML报告: {os.path.abspath(tool.html_report)}")


if __name__ == '__main__':
    main()
