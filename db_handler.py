#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Handler - HIS 实施辅助工具套件数据库处理模块
兼容 oracledb (新版驱动) 和 cx_Oracle (旧版驱动)
"""

import os
import platform
import socket
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

from utils import Status, format_timestamp


ORACLE_DRIVER_AVAILABLE = False
ORACLE_DRIVER_NAME = None
oracle = None

try:
    import oracledb
    oracle = oracledb
    ORACLE_DRIVER_AVAILABLE = True
    ORACLE_DRIVER_NAME = 'oracledb'
except ImportError:
    try:
        import cx_Oracle
        oracle = cx_Oracle
        ORACLE_DRIVER_AVAILABLE = True
        ORACLE_DRIVER_NAME = 'cx_Oracle'
    except ImportError:
        ORACLE_DRIVER_AVAILABLE = False
        ORACLE_DRIVER_NAME = None


DATABASE_HELP_TEXT = """
================================================================================
                    🔧 数据库驱动安装指南
================================================================================

检测到未安装 Oracle 数据库驱动程序。以下是安装说明：

【方案一：安装新版 oracledb（推荐）】
    pip install oracledb
    
    新版 oracledb 支持两种模式：
    1. Thin 模式（无需 Instant Client）：直接连接，推荐
    2. Thick 模式（需 Instant Client）：支持更多高级功能

【方案二：安装旧版 cx_Oracle】
    pip install cx_Oracle
    
    注意：cx_Oracle 必须配置 Oracle Instant Client 环境

【配置 Instant Client（如使用 Thick 模式或 cx_Oracle）】

1. 下载 Oracle Instant Client：
   访问：https://www.oracle.com/database/technologies/instant-client.html
   下载与您的 Python 架构（32位/64位）匹配的版本

2. 解压到指定目录（例如）：
   Windows: C:\\instantclient_19_8
   Linux:   /opt/oracle/instantclient_19_8
   macOS:   /Users/<user>/Downloads/instantclient_19_8

3. 配置环境变量：

   Windows:
   - 将 Instant Client 目录添加到 PATH 系统环境变量
   - 或在代码中初始化：
     import cx_Oracle
     cx_Oracle.init_oracle_client(lib_dir=r"C:\\instantclient_19_8")

   Linux:
   export LD_LIBRARY_PATH=/opt/oracle/instantclient_19_8:$LD_LIBRARY_PATH
   export PATH=/opt/oracle/instantclient_19_8:$PATH

   macOS:
   export DYLD_LIBRARY_PATH=/Users/<user>/Downloads/instantclient_19_8:$DYLD_LIBRARY_PATH

【验证安装】
    python -c "import oracledb; print(oracledb.version)"
    或
    python -c "import cx_Oracle; print(cx_Oracle.version)"

================================================================================
"""


class DatabaseConnection:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ip = config.get('ip', '')
        self.port = config.get('port', 1521)
        self.service_name = config.get('service_name', '')
        self.user = config.get('user', '')
        self.password = config.get('pwd', '')
        self.connection = None
        self.instant_client_dir = config.get('instant_client_dir', None)
    
    def _init_client(self) -> Tuple[bool, str]:
        if not ORACLE_DRIVER_AVAILABLE:
            return False, "未安装 Oracle 数据库驱动"
        
        if ORACLE_DRIVER_NAME == 'cx_Oracle' and self.instant_client_dir:
            try:
                oracle.init_oracle_client(lib_dir=self.instant_client_dir)
                return True, f"已初始化 Instant Client: {self.instant_client_dir}"
            except Exception as e:
                return False, f"初始化 Instant Client 失败: {e}"
        
        return True, f"使用驱动: {ORACLE_DRIVER_NAME}"
    
    def test_connection(self) -> Dict[str, Any]:
        result = {
            'status': Status.ERROR,
            'message': '',
            'details': {
                'driver_available': ORACLE_DRIVER_AVAILABLE,
                'driver_name': ORACLE_DRIVER_NAME,
                'start_time': format_timestamp(),
                'connect_time_ms': None,
                'db_time': None
            },
            'error': None,
            'help_text': None
        }
        
        if not ORACLE_DRIVER_AVAILABLE:
            result['status'] = Status.SKIPPED
            result['message'] = '未安装 Oracle 数据库驱动'
            result['help_text'] = DATABASE_HELP_TEXT
            return result
        
        import time
        
        try:
            init_ok, init_msg = self._init_client()
            result['details']['init_message'] = init_msg
            
            if not init_ok:
                result['message'] = init_msg
                result['error'] = init_msg
                return result
            
            start_time = time.time()
            
            dsn = oracle.makedsn(
                self.ip,
                self.port,
                service_name=self.service_name
            )
            
            self.connection = oracle.connect(
                user=self.user,
                password=self.password,
                dsn=dsn
            )
            
            elapsed = (time.time() - start_time) * 1000
            result['details']['connect_time_ms'] = round(elapsed, 2)
            
            cursor = self.connection.cursor()
            cursor.execute("SELECT SYSDATE FROM DUAL")
            db_time = cursor.fetchone()[0]
            result['details']['db_time'] = str(db_time)
            result['details']['end_time'] = format_timestamp()
            
            cursor.close()
            self.connection.close()
            self.connection = None
            
            result['status'] = Status.OK
            result['message'] = f'连接正常，耗时: {result["details"]["connect_time_ms"]}ms'
            
        except oracle.DatabaseError as e:
            error_obj = e.args[0] if e.args else None
            if error_obj:
                error_code = getattr(error_obj, 'code', 'UNKNOWN')
                error_message = getattr(error_obj, 'message', str(e))
                result['error'] = f"ORA-{error_code}"
                result['message'] = f'数据库错误: {error_code} - {error_message}'
                
                suggestion = self._get_error_suggestion(error_code)
                if suggestion:
                    result['suggestion'] = suggestion
            else:
                result['error'] = str(e)
                result['message'] = f'数据库错误: {e}'
        
        except socket.timeout:
            result['error'] = 'Timeout'
            result['message'] = '连接超时，请检查网络和防火墙'
        
        except Exception as e:
            result['error'] = str(e)
            result['message'] = f'连接异常: {e}'
        
        return result
    
    def _get_error_suggestion(self, error_code) -> Optional[str]:
        suggestions = {
            1017: '用户名或密码错误，请检查配置文件中的 user 和 pwd。',
            12541: '监听程序未启动，请检查数据库服务器的 TNS 监听器状态。',
            12514: '监听程序无法解析请求的 SERVICE_NAME，请检查 service_name 配置。',
            12170: '连接超时，请检查防火墙端口 1521 是否开放，网络是否通畅。',
            28001: '密码已过期，请使用 ALTER USER 语句修改密码。',
            28002: '密码即将过期，请联系 DBA 修改密码。',
            3135: '连接失去联系，可能是网络中断或数据库服务重启。',
            12505: '监听程序不知道当前在 TNS 连接描述符中给出的 SID，请检查配置。',
            12154: '无法解析指定的连接标识符，请检查 TNS 配置。',
        }
        return suggestions.get(error_code)
    
    @contextmanager
    def get_connection(self):
        if not ORACLE_DRIVER_AVAILABLE:
            raise ImportError("Oracle 数据库驱动未安装")
        
        try:
            init_ok, _ = self._init_client()
            if not init_ok:
                raise ConnectionError("无法初始化 Oracle 客户端")
            
            dsn = oracle.makedsn(
                self.ip,
                self.port,
                service_name=self.service_name
            )
            
            self.connection = oracle.connect(
                user=self.user,
                password=self.password,
                dsn=dsn
            )
            
            yield self.connection
            
        finally:
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
                self.connection = None
    
    def check_system_variable(
        self,
        table: str,
        key_column: str,
        value_column: str,
        var_name: str,
        expected_value: Optional[str] = None
    ) -> Dict[str, Any]:
        result = {
            'name': var_name,
            'table': table,
            'status': Status.ERROR,
            'actual_value': None,
            'expected_value': expected_value or '',
            'message': '',
            'error': None
        }
        
        if not ORACLE_DRIVER_AVAILABLE:
            result['status'] = Status.SKIPPED
            result['message'] = '未安装 Oracle 数据库驱动，跳过检查'
            return result
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = f"SELECT {value_column} FROM {table} WHERE {key_column} = :1"
                cursor.execute(query, (var_name,))
                row = cursor.fetchone()
                
                if row:
                    result['actual_value'] = str(row[0]) if row[0] is not None else ''
                else:
                    result['status'] = Status.WARNING
                    result['message'] = f'未找到变量: {var_name}'
                    cursor.close()
                    return result
                
                cursor.close()
                
                if expected_value and result['actual_value'] != expected_value:
                    result['status'] = Status.WARNING
                    result['message'] = f'值不匹配: 期望={expected_value}, 实际={result["actual_value"]}'
                else:
                    result['status'] = Status.OK
                    result['message'] = '检查通过'
                
        except Exception as e:
            result['status'] = Status.ERROR
            result['message'] = str(e)
            result['error'] = str(e)
        
        return result
    
    def check_time_diff(self) -> Dict[str, Any]:
        result = {
            'status': Status.ERROR,
            'message': '',
            'details': {
                'start_time': format_timestamp(),
                'local_time': None,
                'db_time': None,
                'time_diff_seconds': 0
            },
            'error': None
        }
        
        if not ORACLE_DRIVER_AVAILABLE:
            result['status'] = Status.SKIPPED
            result['message'] = '未安装 Oracle 数据库驱动'
            return result
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT SYSDATE FROM DUAL")
                db_time = cursor.fetchone()[0]
                local_time = datetime.now()
                
                time_diff = abs((local_time - db_time).total_seconds())
                
                result['details']['local_time'] = local_time.strftime('%Y-%m-%d %H:%M:%S')
                result['details']['db_time'] = str(db_time)
                result['details']['time_diff_seconds'] = round(time_diff, 2)
                
                cursor.close()
                
                result['status'] = Status.OK
                result['message'] = f'时间差: {time_diff:.2f}秒'
                
        except Exception as e:
            result['status'] = Status.ERROR
            result['message'] = str(e)
            result['error'] = str(e)
        
        return result


def get_driver_info() -> Dict[str, Any]:
    return {
        'available': ORACLE_DRIVER_AVAILABLE,
        'driver_name': ORACLE_DRIVER_NAME,
        'help_text': DATABASE_HELP_TEXT if not ORACLE_DRIVER_AVAILABLE else None
    }
