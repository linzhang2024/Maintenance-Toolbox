#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Handler - HIS 实施辅助工具套件数据库处理模块
兼容 oracledb (新版驱动，Thin 模式无需 Instant Client) 和 cx_Oracle (旧版驱动)
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
ORACLE_DRIVER_MODE = None
oracle = None


try:
    import oracledb
    oracle = oracledb
    ORACLE_DRIVER_AVAILABLE = True
    ORACLE_DRIVER_NAME = 'oracledb'
    ORACLE_DRIVER_MODE = 'thin'
    
    try:
        oracledb.init_oracle_client()
        ORACLE_DRIVER_MODE = 'thick'
    except Exception:
        pass
except ImportError:
    try:
        import cx_Oracle
        oracle = cx_Oracle
        ORACLE_DRIVER_AVAILABLE = True
        ORACLE_DRIVER_NAME = 'cx_Oracle'
        ORACLE_DRIVER_MODE = 'thick'
    except ImportError:
        ORACLE_DRIVER_AVAILABLE = False
        ORACLE_DRIVER_NAME = None
        ORACLE_DRIVER_MODE = None


DATABASE_HELP_TEXT = """
================================================================================
                    🔧 Oracle 数据库驱动安装指南
================================================================================

⚠️ 检测到未安装 Oracle 数据库驱动程序。

【推荐方案：安装 oracledb（无需 Instant Client）】
    pip install oracledb
    
    ✅ 优点：
       - 纯 Python 实现，无需编译
       - Thin 模式无需安装 Oracle Instant Client
       - 支持 Python 3.6+，跨平台
       - 自动使用 Thin 模式，无需额外配置
    
    安装命令：
    pip install oracledb --upgrade
    
    验证安装：
    python -c "import oracledb; print('oracledb version:', oracledb.version)"

【备选方案：安装旧版 cx_Oracle】
    pip install cx_Oracle
    
    ⚠️ 注意：cx_Oracle 必须配置 Oracle Instant Client 环境！
    
    如果必须使用 cx_Oracle：
    1. 下载 Oracle Instant Client:
       https://www.oracle.com/database/technologies/instant-client.html
    
    2. 配置环境变量（Windows）：
       set PATH=C:\\instantclient_19_8;%PATH%
    
       或在代码中配置：
       import cx_Oracle
       cx_Oracle.init_oracle_client(lib_dir=r"C:\\instantclient_19_8")

【快速安装命令（复制粘贴即可）】
    pip install oracledb --quiet

================================================================================
"""


class DatabaseConnection:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ip = config.get('ip', '')
        self.port = config.get('port', 1521)
        self.service_name = config.get('service_name', '')
        self.sid = config.get('sid', '')
        self.user = config.get('user', '')
        self.password = config.get('pwd', '')
        self.connection = None
        self.instant_client_dir = config.get('instant_client_dir', None)
    
    def _init_client(self) -> Tuple[bool, str]:
        if not ORACLE_DRIVER_AVAILABLE:
            return False, "未安装 Oracle 数据库驱动"
        
        if ORACLE_DRIVER_NAME == 'oracledb':
            return True, f"使用 oracledb ({ORACLE_DRIVER_MODE} 模式)"
        
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
                'driver_mode': ORACLE_DRIVER_MODE,
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
            
            if self.sid:
                dsn = oracle.makedsn(self.ip, self.port, sid=self.sid)
            else:
                dsn = oracle.makedsn(self.ip, self.port, service_name=self.service_name)
            
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
            
            if self.sid:
                dsn = oracle.makedsn(self.ip, self.port, sid=self.sid)
            else:
                dsn = oracle.makedsn(self.ip, self.port, service_name=self.service_name)
            
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
            'error': None,
            'var_type': 'system_variable'
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
    
    def check_hearing_age_correction(self) -> Dict[str, Any]:
        result = {
            'name': '年龄修正表基础数据检查',
            'table': 'hearing_age_correction',
            'status': Status.ERROR,
            'record_count': 0,
            'message': '',
            'error': None,
            'var_type': 'hearing_age_correction'
        }
        
        if not ORACLE_DRIVER_AVAILABLE:
            result['status'] = Status.SKIPPED
            result['message'] = '未安装 Oracle 数据库驱动，跳过检查'
            return result
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                try:
                    cursor.execute("SELECT COUNT(*) FROM hearing_age_correction")
                    count = cursor.fetchone()[0]
                    result['record_count'] = count
                    
                    if count == 0:
                        result['status'] = Status.ERROR
                        result['message'] = '⚠️ 电测听年龄修正表(hearing_age_correction)为空！'
                        result['suggestion'] = '请导入年龄修正表基础数据，否则电测听小结计算值功能无法正常使用。'
                    else:
                        result['status'] = Status.OK
                        result['message'] = f'年龄修正表基础数据正常，共 {count} 条记录'
                except oracle.DatabaseError as e:
                    error_obj = e.args[0] if e.args else None
                    if error_obj and hasattr(error_obj, 'code') and error_obj.code == 942:
                        result['status'] = Status.ERROR
                        result['message'] = '⚠️ 表 hearing_age_correction 不存在！'
                        result['suggestion'] = '请联系开发商创建年龄修正表并导入基础数据。'
                    else:
                        raise
                
                cursor.close()
                
        except Exception as e:
            result['status'] = Status.ERROR
            result['message'] = str(e)
            result['error'] = str(e)
        
        return result
    
    def check_pinyin_code_empty(
        self,
        check_tables: List[str] = None
    ) -> Dict[str, Any]:
        if check_tables is None:
            check_tables = [
                {'table': 'tj_xmzd', 'name_column': 'xmmc', 'code_column': 'py_code'},
                {'table': 'tj_kszd', 'name_column': 'ksmc', 'code_column': 'py_code'},
                {'table': 'tj_yszd', 'name_column': 'ysmc', 'code_column': 'py_code'},
            ]
        
        result = {
            'name': '拼音码空值检查',
            'status': Status.OK,
            'message': '',
            'tables_checked': [],
            'empty_count': 0,
            'error': None,
            'var_type': 'pinyin_code_check'
        }
        
        if not ORACLE_DRIVER_AVAILABLE:
            result['status'] = Status.SKIPPED
            result['message'] = '未安装 Oracle 数据库驱动，跳过检查'
            return result
        
        all_empty_count = 0
        has_warning = False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for table_info in check_tables:
                    table = table_info['table']
                    name_col = table_info['name_column']
                    code_col = table_info['code_column']
                    
                    table_result = {
                        'table': table,
                        'status': Status.OK,
                        'empty_count': 0,
                        'empty_items': []
                    }
                    
                    try:
                        query = f"""
                            SELECT {name_col}, {code_col} 
                            FROM {table} 
                            WHERE {code_col} IS NULL OR {code_col} = ''
                        """
                        cursor.execute(query)
                        rows = cursor.fetchall()
                        
                        if rows:
                            table_result['status'] = Status.WARNING
                            table_result['empty_count'] = len(rows)
                            table_result['empty_items'] = [str(row[0]) for row in rows[:10]]
                            all_empty_count += len(rows)
                            has_warning = True
                            
                            if len(rows) > 10:
                                table_result['empty_items'].append(f'... 等 {len(rows)} 条')
                        
                    except oracle.DatabaseError as e:
                        error_obj = e.args[0] if e.args else None
                        if error_obj and hasattr(error_obj, 'code') and error_obj.code == 942:
                            table_result['status'] = Status.SKIPPED
                            table_result['message'] = f'表 {table} 不存在，跳过检查'
                        else:
                            table_result['status'] = Status.ERROR
                            table_result['message'] = str(e)
                    
                    result['tables_checked'].append(table_result)
                
                cursor.close()
                
                result['empty_count'] = all_empty_count
                
                if has_warning:
                    result['status'] = Status.WARNING
                    result['message'] = f'发现 {all_empty_count} 条记录拼音码为空'
                    result['suggestion'] = '请运行拼音码转换工具，为常用项目生成拼音码。'
                else:
                    result['status'] = Status.OK
                    result['message'] = '所有检查的表拼音码均正常'
                
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
        'driver_mode': ORACLE_DRIVER_MODE,
        'help_text': DATABASE_HELP_TEXT if not ORACLE_DRIVER_AVAILABLE else None
    }


def get_python_env_info() -> Dict[str, Any]:
    import sys
    import platform
    
    info = {
        'python_version': sys.version,
        'python_version_short': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'platform': platform.platform(),
        'system': platform.system(),
        'machine': platform.machine(),
        'architecture': platform.architecture()[0],
        'executable': sys.executable,
        'oracle_driver': {
            'available': ORACLE_DRIVER_AVAILABLE,
            'name': ORACLE_DRIVER_NAME,
            'mode': ORACLE_DRIVER_MODE
        },
        'installed_packages': []
    }
    
    try:
        import importlib.metadata
        installed = importlib.metadata.distributions()
        info['installed_packages'] = [
            {'name': dist.metadata['Name'], 'version': dist.version}
            for dist in installed
        ]
        info['installed_packages'].sort(key=lambda x: x['name'].lower())
    except Exception:
        try:
            import pkg_resources
            installed = pkg_resources.working_set
            info['installed_packages'] = [
                {'name': pkg.key, 'version': pkg.version}
                for pkg in installed
            ]
            info['installed_packages'].sort(key=lambda x: x['name'].lower())
        except Exception:
            info['installed_packages'] = []
            info['package_warning'] = '无法获取已安装包列表'
    
    return info
