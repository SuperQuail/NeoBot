"""SQLite数据库连接和表管理"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ColumnType(str, Enum):
    """SQLite列类型"""
    INTEGER = "INTEGER"
    TEXT = "TEXT"
    REAL = "REAL"
    BLOB = "BLOB"
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"  # SQLite实际上使用INTEGER存储布尔值


@dataclass
class Column:
    """表列定义"""
    name: str
    type: ColumnType
    primary_key: bool = False
    autoincrement: bool = False
    not_null: bool = False
    default: Optional[Any] = None
    unique: bool = False

    def to_sql(self) -> str:
        """生成列定义SQL"""
        parts = [self.name, self.type.value]

        if self.primary_key:
            parts.append("PRIMARY KEY")
        if self.autoincrement:
            parts.append("AUTOINCREMENT")
        if self.not_null:
            parts.append("NOT NULL")
        if self.default is not None:
            if isinstance(self.default, str):
                parts.append(f"DEFAULT '{self.default}'")
            else:
                parts.append(f"DEFAULT {self.default}")
        if self.unique:
            parts.append("UNIQUE")

        return " ".join(parts)


@dataclass
class Table:
    """表定义"""
    name: str
    columns: List[Column]

    def to_create_sql(self) -> str:
        """生成CREATE TABLE语句"""
        columns_sql = ", ".join(col.to_sql() for col in self.columns)
        return f"CREATE TABLE IF NOT EXISTS {self.name} ({columns_sql})"

    def get_column_names(self) -> List[str]:
        """获取所有列名"""
        return [col.name for col in self.columns]


class Database:
    """SQLite数据库连接管理器"""

    def __init__(self, db_path: Union[str, Path]):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """建立数据库连接"""
        if self.connection is None:
            self.connection = sqlite3.connect(str(self.db_path))
            # 启用外键约束
            self.connection.execute("PRAGMA foreign_keys = ON")
            # 使用行工厂返回字典
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> sqlite3.Connection:
        """上下文管理器入口"""
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """执行SQL语句"""
        conn = self.connect()
        return conn.execute(sql, params)

    def commit(self):
        """提交事务"""
        if self.connection:
            self.connection.commit()

    def rollback(self):
        """回滚事务"""
        if self.connection:
            self.connection.rollback()

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
        """
        cursor = self.execute(sql, (table_name,))
        return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表的列信息"""
        # 使用PRAGMA table_info获取列信息
        cursor = self.execute(f"PRAGMA table_info({table_name})")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": row[3],
                "default": row[4],
                "pk": row[5]
            })
        return columns

    def get_column_names(self, table_name: str) -> List[str]:
        """获取表的列名列表"""
        columns = self.get_table_columns(table_name)
        return [col["name"] for col in columns]

    def create_table(self, table: Table):
        """创建表"""
        sql = table.to_create_sql()
        self.execute(sql)
        self.commit()
        logger.info(f"表 {table.name} 创建成功")

    def ensure_table(self, table: Table):
        """确保表存在且具有正确的列结构"""
        if not self.table_exists(table.name):
            self.create_table(table)
            return

        # 检查现有表的列
        existing_columns = self.get_column_names(table.name)
        expected_columns = table.get_column_names()

        # 找出缺失的列
        missing_columns = [col for col in expected_columns if col not in existing_columns]

        if missing_columns:
            # 添加缺失的列
            for col_name in missing_columns:
                # 找到对应的列定义
                col_def = next(col for col in table.columns if col.name == col_name)
                self.add_column(table.name, col_def)

            logger.info(f"表 {table.name} 已更新，添加了缺失的列: {missing_columns}")
        else:
            logger.debug(f"表 {table.name} 结构正确，无需更新")

    def add_column(self, table_name: str, column: Column):
        """向表添加新列"""
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column.to_sql()}"
        self.execute(sql)
        self.commit()
        logger.debug(f"已向表 {table_name} 添加列 {column.name}")

    def initialize_tables(self, tables: List[Table]):
        """初始化所有表"""
        logger.info("开始初始化数据库表...")
        for table in tables:
            self.ensure_table(table)
        logger.info("数据库表初始化完成")


# 预定义的表结构
def get_default_tables() -> List[Table]:
    """获取默认的表定义"""
    tables = []

    # USER_DATA 表
    user_data_table = Table(
        name="USER_DATA",
        columns=[
            Column("user_id", ColumnType.TEXT, primary_key=True),
            Column("nick_name", ColumnType.TEXT),
            Column("relation_ship", ColumnType.TEXT),
            Column("profile", ColumnType.TEXT),
            Column("birthday", ColumnType.TEXT),
            Column("sex", ColumnType.TEXT),
            Column("city", ColumnType.TEXT),
            Column("country", ColumnType.TEXT),  # 注意: 用户输入的是counrty，这里修正为country
            Column("labs", ColumnType.TEXT),
            Column("remark", ColumnType.TEXT),
            Column("age", ColumnType.INTEGER),
            Column("long_nick", ColumnType.TEXT),
        ]
    )
    tables.append(user_data_table)

    # GROUP_DATA 表
    group_data_table = Table(
        name="GROUP_DATA",
        columns=[
            Column("group_id", ColumnType.TEXT, primary_key=True),
            Column("group_name", ColumnType.TEXT),
            Column("profile", ColumnType.TEXT),
            Column("is_quite", ColumnType.BOOLEAN, default=0),  # 可能是is_quiet的拼写错误，但保持原样
        ]
    )
    tables.append(group_data_table)

    # EMOJI_DATA 表
    emoji_data_table = Table(
        name="EMOJI_DATA",
        columns=[
            Column("hash", ColumnType.TEXT, primary_key=True),
            Column("description", ColumnType.TEXT),
            Column("path", ColumnType.TEXT),
        ]
    )
    tables.append(emoji_data_table)

    # IMAGES_DATA 表
    images_data_table = Table(
        name="IMAGES_DATA",
        columns=[
            Column("name", ColumnType.TEXT),
            Column("hash", ColumnType.TEXT, primary_key=True),
            Column("description", ColumnType.TEXT),
            Column("path", ColumnType.TEXT),
        ]
    )
    tables.append(images_data_table)

    # LLM_USAGES 表
    llm_usages_table = Table(
        name="LLM_USAGES",
        columns=[
            Column("name", ColumnType.TEXT, primary_key=True),
            Column("input_tokens", ColumnType.INTEGER, default=0),
            Column("output_tokens", ColumnType.INTEGER, default=0),
            Column("total_cost", ColumnType.REAL, default=0.0),
        ]
    )
    tables.append(llm_usages_table)

    # MARRIAGE_DATA 表
    marriage_data_table = Table(
        name="MARRIAGE_DATA",
        columns=[
            Column("user_id", ColumnType.TEXT, primary_key=True),
            Column("is_divorce", ColumnType.BOOLEAN, default=0),  # 修正拼写: is_divocre -> is_divorce
            Column("marriage_time", ColumnType.TEXT),
            Column("marriage_profile", ColumnType.TEXT),
        ]
    )
    tables.append(marriage_data_table)

    # EVENT_DATA 表
    event_data_table = Table(
        name="EVENT_DATA",
        columns=[
            Column("event_id", ColumnType.TEXT, primary_key=True),
            Column("event_message", ColumnType.TEXT),
            Column("embedded_data", ColumnType.TEXT),
        ]
    )
    tables.append(event_data_table)

    return tables


def get_database_path() -> Path:
    """获取数据库文件路径"""
    from neobot_app.core.constants import DATA_DIR
    return DATA_DIR / "neobot.db"


def create_database_instance() -> Database:
    """创建数据库实例"""
    db_path = get_database_path()
    db = Database(db_path)
    # 初始化默认表
    db.initialize_tables(get_default_tables())
    return db


# 全局数据库实例
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """获取全局数据库实例（单例模式）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = create_database_instance()
    return _db_instance


if __name__ == "__main__":
    # 测试代码
    db = get_db()
    print(f"数据库路径: {db.db_path}")
    print("数据库初始化完成")
