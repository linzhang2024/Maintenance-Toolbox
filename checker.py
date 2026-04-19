#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checker Module - HIS 实施辅助工具套件核心检查模块
包含：环境扫描、接口巡检、数据库检查
"""

import os
import platform
import socket
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from utils import DiskChecker, TimeChecker, Status, format_timestamp
from db_handler import DatabaseConnection, get_driver_info


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: Dict[str, Any]
    timestamp: str
    error: Optional[str] = None
    suggestion: Optional[str] = None


class PortProbe:
    COMMON_PORTS = [80, 443, 1521, 8080, 8443, 22, 3389]
    
    @staticmethod
    def probe_port(host: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
        result = {
            'host': host,
            'port': port,
            'open': False,
            'error': None,
            'response_time_ms': None
        }
        
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            sock_result = sock.connect_ex((host, port))
            elapsed = (time.time() - start_time) * 1000
            result['response_time_ms'] = round(elapsed, 2)
            
            if sock_result == 0:
                result['open'] = True
            else:
                result['error'] = f"连接被拒绝 (errno={sock_result})"
            
            sock.close()
        except socket.timeout:
            result['error'] = '连接超时'
        except socket.gaierror:
            result['error'] = '无法解析主机名'
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    @staticmethod
    def probe_host(host: str, ports: Optional[List[int]] = None) -> Dict[str, Any]:
        if ports is None:
            ports = PortProbe.COMMON_PORTS
        
        result = {
            'host': host,
            'scan_time': format_timestamp(),
            'ports': {}
        }
        
        for port in ports:
            port_result = PortProbe.probe_port(host, port)
            result['ports'][str(port)] = port_result
        
        return result
    
    @staticmethod
    def extract_host_from_url(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if parsed.hostname:
                return parsed.hostname
            
            match = re.search(r'://([^:/]+)', url)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None


class EnvironmentScanner:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.env_config = config.get('env_check', {})
        self.db_config = config.get('database', {})
    
    def check_all(self) -> Dict[str, CheckResult]:
        results = {}
        
        results['disk'] = self.check_disk_space()
        results['time_sync'] = self.check_time_sync()
        results['system_vars'] = self.check_system_variables()
        
        return results
    
    def check_disk_space(self) -> CheckResult:
        threshold = self.env_config.get('disk_threshold', 80)
        
        try:
            disks = DiskChecker.check_all_disks(threshold)
            
            if not disks:
                return CheckResult(
                    name='磁盘空间检查',
                    status=Status.SKIPPED,
                    message='无法获取磁盘信息',
                    details={'disks': []},
                    timestamp=format_timestamp()
                )
            
            all_ok = all(d['status'] == 'ok' for d in disks)
            status = Status.OK if all_ok else Status.WARNING
            
            warning_disks = [d for d in disks if d['status'] != 'ok']
            message = f'已检查 {len(disks)} 个磁盘'
            if warning_disks:
                message += f'，{len(warning_disks)} 个磁盘空间使用率超过 {threshold}%'
            
            return CheckResult(
                name='磁盘空间检查',
                status=status,
                message=message,
                details={'threshold': threshold, 'disks': disks},
                timestamp=format_timestamp()
            )
        except Exception as e:
            return CheckResult(
                name='磁盘空间检查',
                status=Status.ERROR,
                message='检查失败',
                details={},
                timestamp=format_timestamp(),
                error=str(e)
            )
    
    def check_time_sync(self) -> CheckResult:
        ntp_servers = self.env_config.get('ntp_servers', ['ntp.aliyun.com'])
        tolerance = self.env_config.get('time_tolerance_seconds', 300)
        
        try:
            time_result = TimeChecker.check_time_sync(ntp_servers, tolerance)
            
            status_map = {
                'ok': Status.OK,
                'warning': Status.WARNING,
                'error': Status.ERROR
            }
            
            return CheckResult(
                name='时间同步检查',
                status=status_map.get(time_result['status'], Status.ERROR),
                message=time_result['message'],
                details=time_result,
                timestamp=format_timestamp()
            )
        except Exception as e:
            return CheckResult(
                name='时间同步检查',
                status=Status.ERROR,
                message='检查失败',
                details={},
                timestamp=format_timestamp(),
                error=str(e)
            )
    
    def check_system_variables(self) -> CheckResult:
        system_vars = self.env_config.get('system_variables', [])
        
        if not system_vars:
            return CheckResult(
                name='系统变量检查',
                status=Status.SKIPPED,
                message='未配置需要检查的系统变量',
                details={'variables': []},
                timestamp=format_timestamp()
            )
        
        driver_info = get_driver_info()
        if not driver_info['available']:
            return CheckResult(
                name='系统变量检查',
                status=Status.SKIPPED,
                message='未安装 Oracle 数据库驱动，跳过检查',
                details={'variables': [], 'driver_info': driver_info},
                timestamp=format_timestamp()
            )
        
        results = []
        all_ok = True
        
        db_conn = DatabaseConnection(self.db_config)
        
        for var in system_vars:
            var_result = db_conn.check_system_variable(
                table=var.get('table', 'tj_xtsz_xtbl'),
                key_column=var.get('key_column', 'xtmc'),
                value_column=var.get('value_column', 'xtsz'),
                var_name=var.get('name', ''),
                expected_value=var.get('expected_value')
            )
            var_result['description'] = var.get('description', '')
            results.append(var_result)
            
            if var_result.get('status') not in ['ok', 'skipped']:
                all_ok = False
        
        status = Status.OK if all_ok else Status.WARNING
        
        return CheckResult(
            name='系统变量检查',
            status=status,
            message=f'已检查 {len(results)} 个系统变量',
            details={'variables': results},
            timestamp=format_timestamp()
        )


class ApiChecker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_list = config.get('api_list', [])
    
    def check_all(self, max_workers: int = 10) -> Dict[str, CheckResult]:
        if not self.api_list:
            return {
                'summary': CheckResult(
                    name='接口巡检',
                    status=Status.SKIPPED,
                    message='未配置任何接口',
                    details={'apis': []},
                    timestamp=format_timestamp()
                )
            }
        
        results = {}
        all_ok = True
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_api = {
                executor.submit(self._check_single_api, api): api 
                for api in self.api_list
            }
            
            for future in as_completed(future_to_api):
                api = future_to_api[future]
                api_name = api.get('name', api.get('url', '未知接口'))
                
                try:
                    result = future.result()
                    results[api_name] = result
                    if result.status != Status.OK:
                        all_ok = False
                except Exception as e:
                    results[api_name] = CheckResult(
                        name=api_name,
                        status=Status.ERROR,
                        message='检查异常',
                        details={'url': api.get('url')},
                        timestamp=format_timestamp(),
                        error=str(e)
                    )
                    all_ok = False
        
        summary = CheckResult(
            name='接口巡检',
            status=Status.OK if all_ok else Status.ERROR,
            message=f'已巡检 {len(self.api_list)} 个接口',
            details={
                'total': len(self.api_list),
                'success': sum(1 for r in results.values() if r.status == Status.OK),
                'failed': sum(1 for r in results.values() if r.status != Status.OK)
            },
            timestamp=format_timestamp()
        )
        
        results['summary'] = summary
        return results
    
    def _check_single_api(self, api_config: Dict[str, Any]) -> CheckResult:
        url = api_config.get('url', '')
        expected_code = api_config.get('expected_code', 200)
        method = api_config.get('method', 'GET').upper()
        timeout = api_config.get('timeout', 10)
        max_retries = api_config.get('max_retries', 0)
        verify_ssl = api_config.get('verify_ssl', True)
        api_name = api_config.get('name', url)
        
        details = {
            'url': url,
            'method': method,
            'expected_code': expected_code,
            'start_time': format_timestamp(),
            'max_retries': max_retries,
            'verify_ssl': verify_ssl,
            'response_time_ms': None,
            'actual_code': None,
            'response_body': None,
            'port_scan': None
        }
        
        attempt = 0
        last_error = None
        
        while attempt <= max_retries:
            try:
                start_time = time.time()
                
                if not verify_ssl:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                if method == 'GET':
                    response = requests.get(url, timeout=timeout, verify=verify_ssl)
                elif method == 'POST':
                    response = requests.post(url, timeout=timeout, verify=verify_ssl)
                else:
                    response = requests.request(method, url, timeout=timeout, verify=verify_ssl)
                
                elapsed = (time.time() - start_time) * 1000
                details['response_time_ms'] = round(elapsed, 2)
                details['actual_code'] = response.status_code
                details['end_time'] = format_timestamp()
                details['attempts'] = attempt + 1
                
                if response.status_code == expected_code:
                    return CheckResult(
                        name=api_name,
                        status=Status.OK,
                        message=f'接口正常，响应时间: {details["response_time_ms"]}ms (尝试 {attempt + 1} 次)',
                        details=details,
                        timestamp=format_timestamp()
                    )
                else:
                    try:
                        details['response_body'] = response.text[:500]
                    except Exception:
                        pass
                    
                    last_error = f'返回码不匹配: 期望={expected_code}, 实际={response.status_code}'
                    
            except requests.exceptions.Timeout as e:
                last_error = f'请求超时 ({timeout}秒)'
                details['error_type'] = 'Timeout'
                
                host = PortProbe.extract_host_from_url(url)
                if host:
                    details['port_scan'] = PortProbe.probe_host(host)
                
            except requests.exceptions.SSLError as e:
                last_error = f'SSL 证书验证失败'
                details['error_type'] = 'SSLError'
                details['suggestion'] = '可尝试设置 verify_ssl: false 跳过证书验证'
                
            except requests.exceptions.ConnectionError as e:
                last_error = f'连接失败: {str(e)[:100]}'
                details['error_type'] = 'ConnectionError'
                
                host = PortProbe.extract_host_from_url(url)
                if host:
                    details['port_scan'] = PortProbe.probe_host(host)
                
            except Exception as e:
                last_error = f'请求异常: {str(e)[:100]}'
                details['error_type'] = 'Exception'
            
            attempt += 1
            if attempt <= max_retries:
                time.sleep(1)
        
        details['attempts'] = attempt
        return CheckResult(
            name=api_name,
            status=Status.ERROR,
            message=f'{last_error} (已尝试 {attempt} 次)',
            details=details,
            timestamp=format_timestamp(),
            error=last_error
        )


class DatabaseChecker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_config = config.get('database', {})
    
    def check_connection(self) -> CheckResult:
        driver_info = get_driver_info()
        
        if not driver_info['available']:
            return CheckResult(
                name='数据库连接检查',
                status=Status.SKIPPED,
                message='未安装 Oracle 数据库驱动',
                details={'driver_info': driver_info},
                timestamp=format_timestamp()
            )
        
        db_conn = DatabaseConnection(self.db_config)
        test_result = db_conn.test_connection()
        
        status = test_result.get('status', Status.ERROR)
        message = test_result.get('message', '')
        
        return CheckResult(
            name='数据库连接检查',
            status=status,
            message=message,
            details=test_result.get('details', {}),
            timestamp=format_timestamp(),
            error=test_result.get('error'),
            suggestion=test_result.get('suggestion')
        )
    
    def check_time_diff(self) -> CheckResult:
        driver_info = get_driver_info()
        
        if not driver_info['available']:
            return CheckResult(
                name='数据库时间差检查',
                status=Status.SKIPPED,
                message='未安装 Oracle 数据库驱动',
                details={'driver_info': driver_info},
                timestamp=format_timestamp()
            )
        
        db_conn = DatabaseConnection(self.db_config)
        time_result = db_conn.check_time_diff()
        
        status = time_result.get('status', Status.ERROR)
        message = time_result.get('message', '')
        
        return CheckResult(
            name='数据库时间差检查',
            status=status,
            message=message,
            details=time_result.get('details', {}),
            timestamp=format_timestamp(),
            error=time_result.get('error')
        )
