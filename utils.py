#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utils Module - HIS 实施辅助工具套件通用工具函数
"""

import os
import json
import platform
from datetime import datetime
from typing import Generator, Optional, List, Dict, Any

DEFAULT_CONFIG = {
    "database": {
        "ip": "192.168.1.100",
        "port": 1521,
        "service_name": "ORCL",
        "user": "his_user",
        "pwd": "his_password",
        "instant_client_dir": ""
    },
    "api_list": [
        {
            "url": "http://192.168.1.100:8080/his/api/health",
            "expected_code": 200,
            "name": "健康检查接口",
            "method": "GET",
            "timeout": 10,
            "max_retries": 3,
            "verify_ssl": false
        }
    ],
    "log_rules": {
        "log_dirs": ["D:\\logs"],
        "keywords": ["ORA-", "ERROR", "Exception", "Timeout", "Failed", "连接失败"],
        "context_lines": 10,
        "log_encoding": "GBK",
        "tail_lines": 50
    },
    "env_check": {
        "disk_threshold": 80,
        "ntp_servers": ["ntp.aliyun.com", "time.windows.com", "pool.ntp.org"],
        "time_tolerance_seconds": 300,
        "final_inspect_required_items": [
            {
                "name": "一般检查",
                "item_code": "0101",
                "required": true,
                "description": "总检必检项目"
            },
            {
                "name": "心电图",
                "item_code": "0201",
                "required": true,
                "description": "总检必检项目"
            },
            {
                "name": "胸片",
                "item_code": "0301",
                "required": true,
                "description": "总检必检项目"
            }
        ],
        "system_variables": [
            {
                "name": "身份证号校验控制",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=启用身份证校验, 0=禁用"
            },
            {
                "name": "拼音码转换控制",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=启用拼音码自动转换，开启后将自动检查常用项目拼音码空值"
            },
            {
                "name": "电测听小结展示方式",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=取计算值（需要年龄修正表基础数据）, 0=取录入值"
            },
            {
                "name": "电测听结果计算方式",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=自动计算（需要计算模板基础数据）, 0=手工录入"
            },
            {
                "name": "项目结果自动关联医生",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=启用自动关联, 0=禁用"
            },
            {
                "name": "总检医生自动刷新",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=启用自动刷新, 0=禁用"
            },
            {
                "name": "默认体检类型",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "",
                "description": "系统默认体检类型代码"
            },
            {
                "name": "强制总检开关",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "1=启用强制总检, 0=禁用。开启后将检查未完成项目控制类型是否配置"
            },
            {
                "name": "总检未完成项目控制类型",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "",
                "description": "1=警告, 2=禁止。强制总检开启时需配置此项"
            },
            {
                "name": "默认体检单位",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "",
                "description": "系统默认体检单位代码"
            },
            {
                "name": "门诊收费是否启用",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "门诊收费模块开关"
            },
            {
                "name": "住院收费是否启用",
                "table": "tj_xtsz_xtbl",
                "key_column": "xtmc",
                "value_column": "xtsz",
                "expected_value": "1",
                "description": "住院收费模块开关"
            }
        ]
    },
    "diagnostic_rules": {
        "ORA-01017": "数据库用户名或密码错误，请检查 db_config 配置。",
        "ORA-12541": "监听程序未启动，请检查数据库服务器 TNS 状态和监听器服务。",
        "ORA-12170": "连接超时，请检查防火墙端口 1521 是否开放，网络是否通畅。",
        "ORA-12514": "监听程序无法解析 SERVICE_NAME，请检查 service_name 配置。",
        "ORA-03135": "连接失去联系，可能是网络中断或数据库服务重启。",
        "ORA-28001": "密码已过期，请使用 ALTER USER 语句修改密码。",
        "ConnectTimeout": "网络连接超时，请检查防火墙端口是否开放，网络是否通畅。",
        "Connection refused": "连接被拒绝，请检查目标服务是否启动，端口是否正确。",
        "Permission denied": "文件读写权限不足，请尝试以管理员身份运行或修改目录权限。",
        "Timeout": "操作超时，请检查网络连接和服务状态。"
    }
}


class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = None
    
    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            self.init_default()
            return self.config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self._validate_config()
            return self.config
        except json.JSONDecodeError:
            try:
                with open(self.config_path, 'r', encoding='gbk') as f:
                    self.config = json.load(f)
                self._validate_config()
                return self.config
            except Exception as e:
                raise ValueError(f"配置文件格式错误: {e}")
    
    def init_default(self) -> None:
        self.config = DEFAULT_CONFIG.copy()
        self.save()
    
    def save(self) -> None:
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def _validate_config(self) -> None:
        required_keys = ['database', 'api_list', 'log_rules', 'env_check']
        for key in required_keys:
            if key not in self.config:
                self.config[key] = DEFAULT_CONFIG[key]
        
        if 'diagnostic_rules' not in self.config:
            self.config['diagnostic_rules'] = DEFAULT_CONFIG['diagnostic_rules']


class FileEncoder:
    ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    
    @staticmethod
    def detect_encoding(file_path: str) -> str:
        for encoding in FileEncoder.ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read(1024)
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        return 'latin-1'
    
    @staticmethod
    def read_lines_generator(
        file_path: str, 
        encoding: Optional[str] = None
    ) -> Generator[str, None, None]:
        if encoding is None:
            encoding = FileEncoder.detect_encoding(file_path)
        
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                for line in f:
                    yield line.rstrip('\n')
        except Exception as e:
            raise IOError(f"无法读取文件 {file_path}: {e}")
    
    @staticmethod
    def read_all_lines(file_path: str, encoding: Optional[str] = None) -> List[str]:
        return list(FileEncoder.read_lines_generator(file_path, encoding))


class DiskChecker:
    @staticmethod
    def get_disk_usage(path: str) -> Dict[str, Any]:
        if platform.system() == 'Windows':
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path),
                None,
                ctypes.byref(total_bytes),
                ctypes.byref(free_bytes)
            )
            free = free_bytes.value
            total = total_bytes.value
            used = total - free
        else:
            statvfs = os.statvfs(path)
            free = statvfs.f_frsize * statvfs.f_bavail
            total = statvfs.f_frsize * statvfs.f_blocks
            used = total - free
        
        percent_used = (used / total * 100) if total > 0 else 0
        
        return {
            'path': path,
            'total': total,
            'used': used,
            'free': free,
            'percent_used': round(percent_used, 2),
            'total_human': DiskChecker._bytes_to_human(total),
            'used_human': DiskChecker._bytes_to_human(used),
            'free_human': DiskChecker._bytes_to_human(free)
        }
    
    @staticmethod
    def _bytes_to_human(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    @staticmethod
    def check_all_disks(threshold: int = 80) -> List[Dict[str, Any]]:
        disks = []
        if platform.system() == 'Windows':
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        usage = DiskChecker.get_disk_usage(drive)
                        usage['status'] = 'warning' if usage['percent_used'] >= threshold else 'ok'
                        disks.append(usage)
                    except Exception:
                        pass
        else:
            for mount in ['/', '/home', '/var']:
                if os.path.exists(mount):
                    try:
                        usage = DiskChecker.get_disk_usage(mount)
                        usage['status'] = 'warning' if usage['percent_used'] >= threshold else 'ok'
                        disks.append(usage)
                    except Exception:
                        pass
        return disks


class TimeChecker:
    @staticmethod
    def get_local_time() -> datetime:
        return datetime.now()
    
    @staticmethod
    def get_ntp_time(server: str = "ntp.aliyun.com", port: int = 123) -> Optional[datetime]:
        import socket
        import struct
        
        NTP_PACKET_FORMAT = "!12I"
        NTP_DELTA = 2208988800
        NTP_TIMEOUT = 5
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(NTP_TIMEOUT)
            
            data = b'\x1b' + 47 * b'\0'
            sock.sendto(data, (server, port))
            data, _ = sock.recvfrom(1024)
            sock.close()
            
            unpacked = struct.unpack(NTP_PACKET_FORMAT, data[0:struct.calcsize(NTP_PACKET_FORMAT)])
            ntp_time = unpacked[10] + float(unpacked[11]) / 2**32
            ntp_time -= NTP_DELTA
            
            return datetime.fromtimestamp(ntp_time)
        except Exception:
            return None
    
    @staticmethod
    def check_time_sync(
        ntp_servers: List[str], 
        tolerance_seconds: int = 300
    ) -> Dict[str, Any]:
        local_time = TimeChecker.get_local_time()
        result = {
            'local_time': local_time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'ok',
            'ntp_time': None,
            'time_diff_seconds': 0,
            'message': ''
        }
        
        for server in ntp_servers:
            ntp_time = TimeChecker.get_ntp_time(server)
            if ntp_time:
                time_diff = abs((local_time - ntp_time).total_seconds())
                result['ntp_time'] = ntp_time.strftime('%Y-%m-%d %H:%M:%S')
                result['time_diff_seconds'] = round(time_diff, 2)
                
                if time_diff > tolerance_seconds:
                    result['status'] = 'warning'
                    result['message'] = f"时间差超过容忍值 {tolerance_seconds} 秒"
                else:
                    result['message'] = "时间同步正常"
                
                return result
        
        result['status'] = 'error'
        result['message'] = "无法连接到任何 NTP 服务器"
        return result


class Status:
    OK = 'ok'
    WARNING = 'warning'
    ERROR = 'error'
    SKIPPED = 'skipped'


def get_status_color(status: str) -> str:
    color_map = {
        Status.OK: '#28a745',
        Status.WARNING: '#ffc107',
        Status.ERROR: '#dc3545',
        Status.SKIPPED: '#6c757d'
    }
    return color_map.get(status, '#6c757d')


def get_status_text(status: str) -> str:
    text_map = {
        Status.OK: '正常',
        Status.WARNING: '警告',
        Status.ERROR: '异常',
        Status.SKIPPED: '跳过'
    }
    return text_map.get(status, '未知')


def format_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
