#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logger Module - HIS 实施辅助工具套件智能日志诊断模块
"""

import os
import re
from typing import List, Dict, Any, Optional, Generator, Tuple
from dataclasses import dataclass
from datetime import datetime

from utils import FileEncoder, Status


@dataclass
class LogMatch:
    file_path: str
    line_number: int
    matched_keyword: str
    line_content: str
    context: List[str]
    suggestion: Optional[str] = None
    timestamp: Optional[str] = None


class LogScanner:
    def __init__(
        self,
        log_dirs: List[str],
        keywords: List[str],
        context_lines: int = 10,
        diagnostic_rules: Optional[Dict[str, str]] = None
    ):
        self.log_dirs = log_dirs
        self.keywords = keywords
        self.context_lines = context_lines
        self.diagnostic_rules = diagnostic_rules or {}
        self.findings: List[LogMatch] = []
    
    def find_log_files(self) -> List[str]:
        log_files = []
        for log_dir in self.log_dirs:
            if not os.path.exists(log_dir):
                continue
            
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith(('.log', '.txt')):
                        log_files.append(os.path.join(root, file))
        
        return log_files
    
    def scan_file(self, file_path: str) -> List[LogMatch]:
        matches = []
        try:
            lines = list(FileEncoder.read_lines_generator(file_path))
        except Exception as e:
            return matches
        
        total_lines = len(lines)
        
        for line_num, line in enumerate(lines, 1):
            matched_keyword = self._match_keyword(line)
            if matched_keyword:
                context = self._extract_context(lines, line_num - 1, total_lines)
                suggestion = self._get_suggestion(line)
                
                log_match = LogMatch(
                    file_path=file_path,
                    line_number=line_num,
                    matched_keyword=matched_keyword,
                    line_content=line,
                    context=context,
                    suggestion=suggestion,
                    timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
                matches.append(log_match)
        
        return matches
    
    def _match_keyword(self, line: str) -> Optional[str]:
        for keyword in self.keywords:
            if keyword in line:
                return keyword
        return None
    
    def _extract_context(self, lines: List[str], idx: int, total: int) -> List[str]:
        start = max(0, idx - self.context_lines)
        end = min(total, idx + self.context_lines + 1)
        
        context = []
        for i in range(start, end):
            prefix = '>>>' if i == idx else '   '
            line_num = i + 1
            context.append(f"{prefix} [{line_num:5d}] {lines[i]}")
        
        return context
    
    def _get_suggestion(self, line: str) -> Optional[str]:
        for pattern, suggestion in self.diagnostic_rules.items():
            if pattern in line:
                return suggestion
        return None
    
    def run_scan(self) -> Dict[str, Any]:
        result = {
            'status': Status.OK,
            'total_files': 0,
            'scanned_files': 0,
            'findings_count': 0,
            'findings': [],
            'message': ''
        }
        
        log_files = self.find_log_files()
        result['total_files'] = len(log_files)
        
        if not log_files:
            result['status'] = Status.SKIPPED
            result['message'] = '未找到任何日志文件'
            return result
        
        for file_path in log_files:
            try:
                matches = self.scan_file(file_path)
                result['scanned_files'] += 1
                if matches:
                    self.findings.extend(matches)
                    result['status'] = Status.WARNING
            except Exception as e:
                continue
        
        result['findings_count'] = len(self.findings)
        
        if self.findings:
            result['status'] = Status.WARNING
            result['message'] = f'发现 {len(self.findings)} 个异常'
            result['findings'] = [self._match_to_dict(m) for m in self.findings]
        else:
            result['message'] = '日志扫描完成，未发现异常'
        
        return result
    
    def _match_to_dict(self, match: LogMatch) -> Dict[str, Any]:
        return {
            'file_path': match.file_path,
            'file_name': os.path.basename(match.file_path),
            'line_number': match.line_number,
            'matched_keyword': match.matched_keyword,
            'line_content': match.line_content,
            'context': match.context,
            'suggestion': match.suggestion,
            'timestamp': match.timestamp
        }


class LogAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        log_rules = config.get('log_rules', {})
        diagnostic_rules = config.get('diagnostic_rules', {})
        
        self.scanner = LogScanner(
            log_dirs=log_rules.get('log_dirs', []),
            keywords=log_rules.get('keywords', []),
            context_lines=log_rules.get('context_lines', 10),
            diagnostic_rules=diagnostic_rules
        )
    
    def analyze_triggered(
        self,
        trigger_type: str,
        trigger_message: str
    ) -> Dict[str, Any]:
        result = {
            'trigger_type': trigger_type,
            'trigger_message': trigger_message,
            'trigger_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'scan_result': None
        }
        
        scan_result = self.scanner.run_scan()
        result['scan_result'] = scan_result
        
        return result
    
    def quick_analyze(self, file_path: str, keyword: Optional[str] = None) -> Dict[str, Any]:
        result = {
            'file_path': file_path,
            'status': Status.OK,
            'findings': [],
            'message': ''
        }
        
        if not os.path.exists(file_path):
            result['status'] = Status.ERROR
            result['message'] = f'文件不存在: {file_path}'
            return result
        
        original_keywords = self.scanner.keywords
        if keyword:
            self.scanner.keywords = [keyword]
        
        try:
            matches = self.scanner.scan_file(file_path)
            if matches:
                result['status'] = Status.WARNING
                result['findings'] = [self.scanner._match_to_dict(m) for m in matches]
                result['message'] = f'发现 {len(matches)} 个匹配项'
            else:
                result['message'] = '未发现异常'
        except Exception as e:
            result['status'] = Status.ERROR
            result['message'] = str(e)
        finally:
            self.scanner.keywords = original_keywords
        
        return result
    
    def search_by_pattern(
        self,
        pattern: str,
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        result = {
            'pattern': pattern,
            'status': Status.OK,
            'total_files': 0,
            'matches': [],
            'message': ''
        }
        
        log_files = self.scanner.find_log_files()
        result['total_files'] = len(log_files)
        
        if not log_files:
            result['status'] = Status.SKIPPED
            result['message'] = '未找到任何日志文件'
            return result
        
        regex_flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, regex_flags)
        
        for file_path in log_files:
            try:
                lines = list(FileEncoder.read_lines_generator(file_path))
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        result['matches'].append({
                            'file_path': file_path,
                            'line_number': line_num,
                            'content': line
                        })
            except Exception:
                continue
        
        if result['matches']:
            result['status'] = Status.WARNING
            result['message'] = f'找到 {len(result["matches"])} 个匹配项'
        else:
            result['message'] = '未找到匹配项'
        
        return result
