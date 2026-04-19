#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HIS 实施辅助工具套件 - 主程序入口
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List

from utils import ConfigManager, Status, get_status_color, get_status_text, format_timestamp
from checker import EnvironmentScanner, ApiChecker, DatabaseChecker, CheckResult, PortProbe
from logger import LogAnalyzer
from db_handler import get_driver_info, DATABASE_HELP_TEXT


class HISHelperTool:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config_manager = ConfigManager(config_path)
        self.config = None
        self.results = {}
        self.log_analyzer = None
        self.html_report = None
        self.driver_info = get_driver_info()
    
    def initialize(self) -> bool:
        print(f"{'='*60}")
        print(f"      HIS 实施辅助工具套件 v1.1")
        print(f"{'='*60}")
        print(f"[{format_timestamp()}] 初始化...")
        
        print(f"[{format_timestamp()}] Oracle 驱动: {'可用' if self.driver_info['available'] else '未安装'}", end='')
        if self.driver_info['driver_name']:
            print(f" ({self.driver_info['driver_name']})")
        else:
            print("")
            print(f"  💡 提示: 请安装 oracledb 或 cx_Oracle 以启用数据库检查")
        
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
            'log': {},
            'driver_info': self.driver_info
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
        
        if not self.driver_info['available']:
            print(f"  ⚠️  未安装 Oracle 驱动，跳过数据库检查")
            print(f"  💡 请查看报告中的 '环境修复建议' 板块了解安装方法")
            
            self.results['database'] = {
                'connection': {
                    'name': '数据库连接检查',
                    'status': Status.SKIPPED,
                    'message': '未安装 Oracle 数据库驱动',
                    'details': {'driver_info': self.driver_info},
                    'timestamp': format_timestamp()
                },
                'time_diff': {
                    'name': '数据库时间差检查',
                    'status': Status.SKIPPED,
                    'message': '未安装 Oracle 数据库驱动',
                    'details': {'driver_info': self.driver_info},
                    'timestamp': format_timestamp()
                }
            }
            print(f"[{format_timestamp()}] [数据库检查] 完成 (已跳过)")
            return
        
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
            if result.suggestion:
                print(f"     💡 建议: {result.suggestion}")
        
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
                    
                    details = result.details
                    if details.get('port_scan'):
                        port_scan = details['port_scan']
                        print(f"       📡 端口探测 ({port_scan['host']}):")
                        for port_str, port_info in port_scan['ports'].items():
                            port_status = "✅ 开放" if port_info['open'] else "❌ 关闭/过滤"
                            print(f"         端口 {port_str}: {port_status}")
        
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
            keyword_freq = scan_result.get('keyword_frequency', [])
            uncategorized = scan_result.get('uncategorized_tails', [])
            
            if findings_count > 0:
                print(f"[{format_timestamp()}] [日志诊断] 发现 {findings_count} 个异常")
                if keyword_freq:
                    print(f"  📊 关键词频率统计:")
                    for item in keyword_freq[:5]:
                        print(f"     {item['keyword']}: {item['count']} 次")
                
                for finding in scan_result.get('findings', []):
                    print(f"  - {finding['file_name']}:{finding['line_number']} - {finding['matched_keyword']}")
                    if finding.get('suggestion'):
                        print(f"    💡 建议: {finding['suggestion']}")
            elif uncategorized:
                print(f"[{format_timestamp()}] [日志诊断] 未发现匹配异常，已提取 {len(uncategorized)} 个最新日志文件的末尾内容")
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
        .section h3 {{
            font-size: 16px;
            color: #495057;
            margin: 20px 0 15px 0;
            padding-left: 10px;
            border-left: 3px solid #ffc107;
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
            max-height: 400px;
            overflow-y: auto;
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
        .fix-guide {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        .fix-guide h4 {{
            color: #856404;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ffeaa7;
        }}
        .fix-guide pre {{
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 15px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 13px;
            white-space: pre-wrap;
        }}
        .fix-guide ol {{
            margin-left: 20px;
            color: #856404;
        }}
        .fix-guide ol li {{
            margin-bottom: 10px;
            line-height: 1.6;
        }}
        .freq-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
            border-radius: 6px;
            overflow: hidden;
        }}
        .freq-table th, .freq-table td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        .freq-table th {{
            background: #667eea;
            color: white;
            font-weight: bold;
        }}
        .freq-table tr:hover {{ background: #f8f9fa; }}
        .freq-badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            background: #dc3545;
            color: white;
            font-weight: bold;
            font-size: 12px;
        }}
        .port-scan {{
            margin-top: 10px;
            padding: 10px;
            background: white;
            border-radius: 6px;
        }}
        .port-item {{
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }}
        .port-item:last-child {{ border-bottom: none; }}
        .port-open {{ color: #28a745; font-weight: bold; }}
        .port-closed {{ color: #dc3545; font-weight: bold; }}
        .uncategorized-box {{
            background: #f8f9fa;
            border: 1px dashed #6c757d;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .uncategorized-header {{
            color: #6c757d;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .uncategorized-content {{
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px;
            border-radius: 6px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 11px;
            overflow-x: auto;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre;
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
        {self._build_fix_guide_section()}
        
        <div class="footer">
            HIS 实施辅助工具套件 v1.1 | 报告生成于 {self.results.get('run_time', '未知')}
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
        
        driver_available = self.driver_info.get('available', False)
        driver_status = "✅ 已安装" if driver_available else "❌ 未安装"
        driver_name = self.driver_info.get('driver_name', '')
        if driver_name:
            driver_status += f" ({driver_name})"
        
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
            <div class="summary-card">
                <div class="number" style="font-size: 14px; line-height: 1.4;">{driver_status}</div>
                <div class="label">Oracle 驱动</div>
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
            suggestion = result.get('details', {}).get('suggestion', '') or result.get('suggestion', '')
            
            suggestion_html = ''
            if suggestion:
                suggestion_html = f"""
                    <div class="suggestion">
                        <div class="suggestion-title">💡 实施建议</div>
                        <div>{suggestion}</div>
                    </div>
                """
            
            items_html += f"""
                <div class="result-card {status_class}">
                    <div class="result-header">
                        <span class="result-name">{result['name']}</span>
                        <span class="result-status {status_class}">{get_status_text(result['status'])}</span>
                    </div>
                    <div class="result-message">{result['message']}</div>
                    {suggestion_html}
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
            
            port_scan_html = ''
            if details.get('port_scan'):
                port_scan = details['port_scan']
                port_items = ''
                for port_str, port_info in port_scan['ports'].items():
                    port_status = 'port-open' if port_info['open'] else 'port-closed'
                    port_text = '✅ 开放' if port_info['open'] else '❌ 关闭/过滤'
                    port_items += f"""
                        <div class="port-item">
                            <span>端口 {port_str}</span>
                            <span class="{port_status}">{port_text}</span>
                        </div>
                    """
                port_scan_html = f"""
                    <div class="port-scan">
                        <div style="font-weight: bold; margin-bottom: 8px; color: #667eea;">
                            📡 端口探测 ({port_scan['host']})
                        </div>
                        {port_items}
                    </div>
                """
            
            api_list_html += f"""
                <div class="api-item">
                    <div>
                        <div class="api-name">{name}</div>
                        <div class="api-url">{details.get('url', 'N/A')}</div>
                        {port_scan_html}
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
        keyword_freq = scan_result.get('keyword_frequency', [])
        uncategorized = scan_result.get('uncategorized_tails', [])
        
        freq_html = ''
        if keyword_freq:
            freq_rows = ''
            for item in keyword_freq:
                freq_rows += f"""
                    <tr>
                        <td>{item['keyword']}</td>
                        <td><span class="freq-badge">{item['count']}</span></td>
                        <td>{', '.join(item['files'][:3])}{'...' if len(item['files']) > 3 else ''}</td>
                    </tr>
                """
            freq_html = f"""
                <h3>📊 关键词频率统计</h3>
                <table class="freq-table">
                    <thead>
                        <tr>
                            <th>关键词</th>
                            <th>出现次数</th>
                            <th>涉及文件</th>
                        </tr>
                    </thead>
                    <tbody>
                        {freq_rows}
                    </tbody>
                </table>
            """
        
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
        
        uncategorized_html = ''
        if uncategorized:
            uncategorized_html = '<h3>📋 未分类异常（最新日志末尾）</h3>'
            for tail in uncategorized:
                lines_content = '\n'.join(tail['lines'])
                uncategorized_html += f"""
                    <div class="uncategorized-box">
                        <div class="uncategorized-header">
                            📄 {tail['file_name']} (最后 {tail['total_lines']} 行)
                        </div>
                        <div class="uncategorized-content">{lines_content}</div>
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
                    发现异常: {scan_result.get('findings_count', 0)} |
                    编码: {scan_result.get('log_encoding', '自动检测')}
                </div>
                <div class="details-toggle">触发原因 ▼</div>
                <div class="details-content">
触发类型: {log_result.get('trigger_type', 'N/A')}
触发原因: {log_result.get('trigger_message', 'N/A')}
触发时间: {log_result.get('trigger_time', 'N/A')}
                </div>
            </div>
            {freq_html}
            {findings_html}
            {uncategorized_html}
        </div>
        """
    
    def _build_fix_guide_section(self) -> str:
        if self.driver_info.get('available'):
            return ''
        
        help_text = DATABASE_HELP_TEXT.strip()
        
        return f"""
        <div class="section">
            <h2>🔧 环境修复建议</h2>
            <div class="fix-guide">
                <h4>⚠️ Oracle 数据库驱动未安装</h4>
                <p style="margin-bottom: 15px; color: #856404;">
                    检测到未安装 Oracle 数据库驱动，以下是安装指南：
                </p>
                <pre>{help_text}</pre>
            </div>
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
            'error': result.error,
            'suggestion': result.suggestion
        }


def main():
    parser = argparse.ArgumentParser(
        description='HIS 实施辅助工具套件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                           # 使用默认配置运行所有检查
  python main.py -c my_config.json         # 使用指定配置文件
  python main.py -o report_2024.html      # 自定义输出报告名称
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
