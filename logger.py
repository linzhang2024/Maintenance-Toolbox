#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logger Module - HIS 实施辅助工具套件智能日志诊断模块
"""

import os
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Generator, Tuple
from dataclasses import dataclass
from datetime import datetime

from utils import FileEncoder, Status, format_timestamp


@dataclass
class LogMatch:
    file_path: str
    line_number: int
    matched_keyword: str
    line_content: str
    context: List[str]
    suggestion: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class KeywordFrequency:
    keyword: str
    count: int
    files: List[str]


class LogScanner:
    def __init__(
        self,
        log_dirs: List[str],
        keywords: List[str],
        context_lines: int = 10,
        diagnostic_rules: Optional[Dict[str, str]] = None,
        log_encoding: str = 'GBK',
        tail_lines: int = 50
    ):
        self.log_dirs = log_dirs
        self.keywords = keywords
        self.context_lines = context_lines
        self.diagnostic_rules = diagnostic_rules or {}
        self.log_encoding = log_encoding
        self.tail_lines = tail_lines
        self.findings: List[LogMatch] = []
        self.keyword_counter: Counter = Counter()
        self.file_keyword_map: Dict[str, List[str]] = {}
        self.uncategorized_tails: List[Dict[str, Any]] = []
    
    def find_log_files(self) -> List[str]:
        log_files = []
        for log_dir in self.log_dirs:
            if not os.path.exists(log_dir):
                continue
            
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith(('.log', '.txt')):
                        log_files.append(os.path.join(root, file))
        
        return sorted(log_files, key=lambda f: os.path.getmtime(f), reverse=True)
    
    def read_file_with_encoding(self, file_path: str) -> List[str]:
        try:
            return list(FileEncoder.read_lines_generator(file_path, encoding=self.log_encoding))
        except Exception:
            try:
                return list(FileEncoder.read_lines_generator(file_path, encoding='utf-8'))
            except Exception:
                return list(FileEncoder.read_lines_generator(file_path))
    
    def scan_file(self, file_path: str) -> List[LogMatch]:
        matches = []
        file_keywords = []
        
        try:
            lines = self.read_file_with_encoding(file_path)
        except Exception as e:
            return matches
        
        total_lines = len(lines)
        
        if total_lines == 0:
            return matches
        
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
                    timestamp=format_timestamp()
                )
                matches.append(log_match)
                
                self.keyword_counter[matched_keyword] += 1
                file_keywords.append(matched_keyword)
        
        if file_keywords:
            self.file_keyword_map[file_path] = list(set(file_keywords))
        
        return matches
    
    def extract_tail_lines(self, file_path: str) -> List[str]:
        try:
            lines = self.read_file_with_encoding(file_path)
        except Exception:
            return []
        
        if len(lines) <= self.tail_lines:
            return lines
        
        return lines[-self.tail_lines:]
    
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
    
    def get_keyword_frequency(self) -> List[Dict[str, Any]]:
        frequency_list = []
        for keyword, count in self.keyword_counter.most_common():
            files = [f for f, kws in self.file_keyword_map.items() if keyword in kws]
            frequency_list.append({
                'keyword': keyword,
                'count': count,
                'files': [os.path.basename(f) for f in files],
                'file_paths': files
            })
        return frequency_list
    
    def run_scan(self) -> Dict[str, Any]:
        result = {
            'status': Status.OK,
            'total_files': 0,
            'scanned_files': 0,
            'findings_count': 0,
            'findings': [],
            'keyword_frequency': [],
            'uncategorized_tails': [],
            'log_encoding': self.log_encoding,
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
        result['keyword_frequency'] = self.get_keyword_frequency()
        
        if not self.findings and log_files:
            latest_files = log_files[:3]
            for file_path in latest_files:
                tail_lines = self.extract_tail_lines(file_path)
                if tail_lines:
                    self.uncategorized_tails.append({
                        'file_path': file_path,
                        'file_name': os.path.basename(file_path),
                        'total_lines': len(tail_lines),
                        'lines': tail_lines
                    })
            result['uncategorized_tails'] = self.uncategorized_tails
        
        if self.findings:
            result['status'] = Status.WARNING
            result['message'] = f'发现 {len(self.findings)} 个异常'
            result['findings'] = [self._match_to_dict(m) for m in self.findings]
        elif self.uncategorized_tails:
            result['status'] = Status.WARNING
            result['message'] = f'未发现匹配异常，已提取 {len(self.uncategorized_tails)} 个最新日志文件的末尾内容'
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
            diagnostic_rules=diagnostic_rules,
            log_encoding=log_rules.get('log_encoding', 'GBK'),
            tail_lines=log_rules.get('tail_lines', 50)
        )
    
    def analyze_triggered(
        self,
        trigger_type: str,
        trigger_message: str
    ) -> Dict[str, Any]:
        result = {
            'trigger_type': trigger_type,
            'trigger_message': trigger_message,
            'trigger_time': format_timestamp(),
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
            'keyword_frequency': [],
            'tail_lines': [],
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
            tail_lines = self.scanner.extract_tail_lines(file_path)
            
            if matches:
                result['status'] = Status.WARNING
                result['findings'] = [self.scanner._match_to_dict(m) for m in matches]
                result['keyword_frequency'] = self.scanner.get_keyword_frequency()
                result['message'] = f'发现 {len(matches)} 个匹配项'
            else:
                result['tail_lines'] = tail_lines
                result['message'] = f'未发现异常，已提取最后 {len(tail_lines)} 行'
                
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
                lines = self.scanner.read_file_with_encoding(file_path)
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        result['matches'].append({
                            'file_path': file_path,
                            'file_name': os.path.basename(file_path),
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
