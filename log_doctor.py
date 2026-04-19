#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log Doctor - 服务器日志快速诊断工具
用于HIS系统实施人员快速诊断日志中的问题
"""

import os
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style
from datetime import datetime

init(autoreset=True)

DIAGNOSTIC_RULES = {
    'ORA-01017': '数据库用户名或密码错误，请检查 db_config。',
    'ORA-12541': '监听程序未启动，请检查数据库服务器 TNS 状态。',
    'ConnectTimeout': '网络连接超时，请检查防火墙端口是否开放。',
    'Permission denied': '文件读写权限不足，请尝试以管理员身份运行或修改目录权限。',
}

ERROR_KEYWORDS = [
    'ERROR',
    'Exception',
    'ORA-',
    'Timeout',
    'Failed',
    '连接失败',
]

CONTEXT_LINES = 10


class LogDoctor:
    def __init__(self, directory, context_lines=CONTEXT_LINES):
        self.directory = directory
        self.context_lines = context_lines
        self.findings = []
    
    def find_log_files(self):
        log_files = []
        for root, dirs, files in os.walk(self.directory):
            for file in files:
                if file.endswith('.log') or file.endswith('.txt'):
                    log_files.append(os.path.join(root, file))
        return log_files
    
    def analyze_file(self, file_path):
        file_findings = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"{Fore.YELLOW}无法读取文件 {file_path}: {e}{Style.RESET_ALL}")
            return file_findings
        
        total_lines = len(lines)
        for i, line in enumerate(lines):
            for keyword in ERROR_KEYWORDS:
                if keyword in line:
                    start = max(0, i - self.context_lines)
                    end = min(total_lines, i + self.context_lines + 1)
                    
                    context = []
                    for j in range(start, end):
                        prefix = '>>>' if j == i else '   '
                        line_num = j + 1
                        context_line = f"{prefix} [{line_num:5d}] {lines[j].rstrip()}"
                        context.append(context_line)
                    
                    suggestion = self._get_suggestion(line)
                    
                    file_findings.append({
                        'file': file_path,
                        'line_number': i + 1,
                        'keyword': keyword,
                        'line_content': line.strip(),
                        'context': '\n'.join(context),
                        'suggestion': suggestion
                    })
                    break
        
        return file_findings
    
    def _get_suggestion(self, line):
        for error_pattern, suggestion in DIAGNOSTIC_RULES.items():
            if error_pattern in line:
                return suggestion
        return None
    
    def run_analysis(self, max_workers=None):
        log_files = self.find_log_files()
        if not log_files:
            print(f"{Fore.YELLOW}未找到任何 .log 或 .txt 文件{Style.RESET_ALL}")
            return
        
        print(f"{Fore.CYAN}发现 {len(log_files)} 个日志文件，开始并行分析...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self.analyze_file, file_path): file_path 
                for file_path in log_files
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    file_findings = future.result()
                    if file_findings:
                        self.findings.extend(file_findings)
                        print(f"{Fore.GREEN}✓ 分析完成: {file_path} (发现 {len(file_findings)} 个问题){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.GREEN}✓ 分析完成: {file_path} (无异常){Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}✗ 分析失败: {file_path} - {e}{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}分析完成！共发现 {len(self.findings)} 个问题{Style.RESET_ALL}")
        
        if self.findings:
            self._print_findings()
            self._generate_report()
    
    def _print_findings(self):
        for idx, finding in enumerate(self.findings, 1):
            print(f"\n{Fore.RED}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.RED}【问题 {idx}】{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}文件: {Style.RESET_ALL}{finding['file']}")
            print(f"{Fore.YELLOW}行号: {Style.RESET_ALL}{finding['line_number']}")
            print(f"{Fore.YELLOW}关键字: {Style.RESET_ALL}{finding['keyword']}")
            print(f"{Fore.YELLOW}内容: {Style.RESET_ALL}{finding['line_content']}")
            
            if finding['suggestion']:
                print(f"\n{Fore.GREEN}💡 建议: {Style.RESET_ALL}{finding['suggestion']}")
            
            print(f"\n{Fore.CYAN}上下文: {Style.RESET_ALL}")
            for line in finding['context'].split('\n'):
                if '>>>' in line:
                    print(f"{Fore.RED}{line}{Style.RESET_ALL}")
                else:
                    print(line)
    
    def _generate_report(self):
        report_file = os.path.join(self.directory, 'diagnostic_report.md')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write('# Log Doctor 诊断报告\n\n')
            f.write(f'**生成时间**: {timestamp}\n\n')
            f.write(f'**扫描目录**: {self.directory}\n\n')
            f.write(f'**发现问题总数**: {len(self.findings)}\n\n')
            f.write('---\n\n')
            
            for idx, finding in enumerate(self.findings, 1):
                f.write(f'## 问题 {idx}\n\n')
                f.write(f'- **文件**: `{finding["file"]}`\n')
                f.write(f'- **行号**: {finding["line_number"]}\n')
                f.write(f'- **关键字**: `{finding["keyword"]}`\n')
                f.write(f'- **内容**: {finding["line_content"]}\n\n')
                
                if finding['suggestion']:
                    f.write(f'### 💡 实施建议\n\n')
                    f.write(f'**{finding["suggestion"]}**\n\n')
                
                f.write('### 上下文\n\n')
                f.write('```\n')
                f.write(finding['context'])
                f.write('\n```\n\n')
                f.write('---\n\n')
        
        print(f"\n{Fore.GREEN}📄 诊断报告已生成: {report_file}{Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(
        description='Log Doctor - 服务器日志快速诊断工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python log_doctor.py                    # 扫描当前目录
  python log_doctor.py -d /var/logs      # 扫描指定目录
  python log_doctor.py -d D:\\logs        # Windows下扫描指定目录
  python log_doctor.py -c 5               # 自定义上下文行数为5
        '''
    )
    
    parser.add_argument(
        '-d', '--directory',
        default='.',
        help='要扫描的目录路径 (默认: 当前目录)'
    )
    
    parser.add_argument(
        '-c', '--context',
        type=int,
        default=CONTEXT_LINES,
        help=f'上下文行数 (默认: {CONTEXT_LINES})'
    )
    
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=None,
        help='并行工作线程数 (默认: CPU核心数)'
    )
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"{Fore.RED}错误: 目录 '{args.directory}' 不存在{Style.RESET_ALL}")
        return
    
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}            Log Doctor - 日志诊断工具{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}扫描目录: {args.directory}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}上下文行数: {args.context}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    doctor = LogDoctor(args.directory, context_lines=args.context)
    doctor.run_analysis(max_workers=args.workers)


if __name__ == '__main__':
    main()
