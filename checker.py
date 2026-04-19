#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checker Module - HIS 实施辅助工具套件核心检查模块
包含：环境扫描、接口巡检、数据库检查
"""

import os
import platform
import socket
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import requests

from utils import DiskChecker, TimeChecker, Status, format_timestamp


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: Dict[str, Any]
    timestamp: str
    error: Optional[str] = None


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
        
        results = []
        all_ok = True
        
        for var in system_vars:
            var_result = self._check_single_variable(var)
            results.append(var_result)
            if var_result.get('status') != 'ok':
                all_ok = False
        
        status = Status.OK if all_ok else Status.WARNING
        
        return CheckResult(
            name='系统变量检查',
            status=status,
            message=f'已检查 {len(results)} 个系统变量',
            details={'variables': results},
            timestamp=format_timestamp()
        )
    
    def _check_single_variable(self, var_config: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            'name': var_config.get('name', '未知变量'),
            'table': var_config.get('table', ''),
            'status': 'ok',
            'actual_value': None,
            'expected_value': var_config.get('expected_value', ''),
            'message': ''
        }
        
        if not self.db_config:
            result['status'] = 'skipped'
            result['message'] = '未配置数据库连接'
            return result
        
        try:
            import cx_Oracle
            dsn = cx_Oracle.makedsn(
                self.db_config['ip'],
                self.db_config['port'],
                service_name=self.db_config['service_name']
            )
            connection = cx_Oracle.connect(
                user=self.db_config['user'],
                password=self.db_config['pwd'],
                dsn=dsn
            )
            cursor = connection.cursor()
            
            table = var_config.get('table', 'tj_xtsz_xtbl')
            key_column = var_config.get('key_column', 'xtmc')
            value_column = var_config.get('value_column', 'xtsz')
            var_name = var_config.get('name', '')
            
            query = f"SELECT {value_column} FROM {table} WHERE {key_column} = :1"
            cursor.execute(query, (var_name,))
            row = cursor.fetchone()
            
            if row:
                result['actual_value'] = str(row[0]) if row[0] else ''
            else:
                result['status'] = 'warning'
                result['message'] = f'未找到变量: {var_name}'
                return result
            
            cursor.close()
            connection.close()
            
            expected = var_config.get('expected_value', '')
            if expected and result['actual_value'] != expected:
                result['status'] = 'warning'
                result['message'] = f'值不匹配: 期望={expected}, 实际={result["actual_value"]}'
            else:
                result['message'] = '检查通过'
            
        except ImportError:
            result['status'] = 'skipped'
            result['message'] = '未安装 cx_Oracle 库，无法检查数据库变量'
        except Exception as e:
            result['status'] = 'error'
            result['message'] = str(e)
        
        return result


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
        api_name = api_config.get('name', url)
        
        details = {
            'url': url,
            'method': method,
            'expected_code': expected_code,
            'start_time': format_timestamp(),
            'response_time_ms': None,
            'actual_code': None,
            'response_body': None
        }
        
        try:
            import time
            start_time = time.time()
            
            if method == 'GET':
                response = requests.get(url, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, timeout=timeout)
            else:
                response = requests.request(method, url, timeout=timeout)
            
            elapsed = (time.time() - start_time) * 1000
            details['response_time_ms'] = round(elapsed, 2)
            details['actual_code'] = response.status_code
            details['end_time'] = format_timestamp()
            
            if response.status_code == expected_code:
                return CheckResult(
                    name=api_name,
                    status=Status.OK,
                    message=f'接口正常，响应时间: {details["response_time_ms"]}ms',
                    details=details,
                    timestamp=format_timestamp()
                )
            else:
                try:
                    details['response_body'] = response.text[:500]
                except Exception:
                    pass
                
                return CheckResult(
                    name=api_name,
                    status=Status.ERROR,
                    message=f'返回码不匹配: 期望={expected_code}, 实际={response.status_code}',
                    details=details,
                    timestamp=format_timestamp()
                )
        
        except requests.exceptions.Timeout:
            return CheckResult(
                name=api_name,
                status=Status.ERROR,
                message=f'请求超时 ({timeout}秒)',
                details=details,
                timestamp=format_timestamp(),
                error='Timeout'
            )
        except requests.exceptions.ConnectionError as e:
            return CheckResult(
                name=api_name,
                status=Status.ERROR,
                message='连接失败',
                details=details,
                timestamp=format_timestamp(),
                error=str(e)
            )
        except Exception as e:
            return CheckResult(
                name=api_name,
                status=Status.ERROR,
                message='请求异常',
                details=details,
                timestamp=format_timestamp(),
                error=str(e)
            )


class DatabaseChecker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_config = config.get('database', {})
    
    def check_connection(self) -> CheckResult:
        if not self.db_config:
            return CheckResult(
                name='数据库连接检查',
                status=Status.SKIPPED,
                message='未配置数据库连接信息',
                details={},
                timestamp=format_timestamp()
            )
        
        details = {
            'ip': self.db_config.get('ip'),
            'port': self.db_config.get('port'),
            'service_name': self.db_config.get('service_name'),
            'user': self.db_config.get('user'),
            'start_time': format_timestamp()
        }
        
        try:
            import cx_Oracle
            import time
            
            start_time = time.time()
            
            dsn = cx_Oracle.makedsn(
                self.db_config['ip'],
                self.db_config['port'],
                service_name=self.db_config['service_name']
            )
            
            connection = cx_Oracle.connect(
                user=self.db_config['user'],
                password=self.db_config['pwd'],
                dsn=dsn
            )
            
            cursor = connection.cursor()
            cursor.execute("SELECT SYSDATE FROM DUAL")
            db_time = cursor.fetchone()[0]
            
            elapsed = (time.time() - start_time) * 1000
            details['connect_time_ms'] = round(elapsed, 2)
            details['db_time'] = str(db_time)
            details['end_time'] = format_timestamp()
            
            cursor.close()
            connection.close()
            
            return CheckResult(
                name='数据库连接检查',
                status=Status.OK,
                message=f'连接正常，耗时: {details["connect_time_ms"]}ms',
                details=details,
                timestamp=format_timestamp()
            )
        
        except ImportError:
            return CheckResult(
                name='数据库连接检查',
                status=Status.SKIPPED,
                message='未安装 cx_Oracle 库，无法检查数据库',
                details=details,
                timestamp=format_timestamp()
            )
        except cx_Oracle.DatabaseError as e:
            error_obj, = e.args
            return CheckResult(
                name='数据库连接检查',
                status=Status.ERROR,
                message=f'数据库错误: {error_obj.code} - {error_obj.message}',
                details=details,
                timestamp=format_timestamp(),
                error=f"ORA-{error_obj.code}"
            )
        except Exception as e:
            return CheckResult(
                name='数据库连接检查',
                status=Status.ERROR,
                message='连接异常',
                details=details,
                timestamp=format_timestamp(),
                error=str(e)
            )
    
    def check_time_diff(self) -> CheckResult:
        if not self.db_config:
            return CheckResult(
                name='数据库时间差检查',
                status=Status.SKIPPED,
                message='未配置数据库连接信息',
                details={},
                timestamp=format_timestamp()
            )
        
        details = {
            'start_time': format_timestamp()
        }
        
        try:
            import cx_Oracle
            
            dsn = cx_Oracle.makedsn(
                self.db_config['ip'],
                self.db_config['port'],
                service_name=self.db_config['service_name']
            )
            
            connection = cx_Oracle.connect(
                user=self.db_config['user'],
                password=self.db_config['pwd'],
                dsn=dsn
            )
            
            cursor = connection.cursor()
            cursor.execute("SELECT SYSDATE FROM DUAL")
            db_time = cursor.fetchone()[0]
            local_time = datetime.now()
            
            time_diff = abs((local_time - db_time).total_seconds())
            
            details['local_time'] = local_time.strftime('%Y-%m-%d %H:%M:%S')
            details['db_time'] = str(db_time)
            details['time_diff_seconds'] = round(time_diff, 2)
            details['tolerance'] = self.config.get('env_check', {}).get('time_tolerance_seconds', 300)
            
            cursor.close()
            connection.close()
            
            tolerance = details['tolerance']
            if time_diff <= tolerance:
                return CheckResult(
                    name='数据库时间差检查',
                    status=Status.OK,
                    message=f'时间同步正常，差值: {time_diff:.2f}秒',
                    details=details,
                    timestamp=format_timestamp()
                )
            else:
                return CheckResult(
                    name='数据库时间差检查',
                    status=Status.WARNING,
                    message=f'时间差超过容忍值: {time_diff:.2f}秒 > {tolerance}秒',
                    details=details,
                    timestamp=format_timestamp()
                )
        
        except ImportError:
            return CheckResult(
                name='数据库时间差检查',
                status=Status.SKIPPED,
                message='未安装 cx_Oracle 库，无法检查数据库',
                details=details,
                timestamp=format_timestamp()
            )
        except Exception as e:
            return CheckResult(
                name='数据库时间差检查',
                status=Status.ERROR,
                message='检查失败',
                details=details,
                timestamp=format_timestamp(),
                error=str(e)
            )
