"""
SQLAlchemy 2.0 声明式基类
所有 ORM 模型继承此类
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass
