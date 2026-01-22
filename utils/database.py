"""
数据库工具模块
提供统一的Redis、MySQL、MongoDB连接和会话管理
"""

import redis
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
import logging

logger = logging.getLogger(__name__)

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    db=settings.REDIS_DB,
    decode_responses=True
)

# MySQL连接
MYSQL_URL = f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
engine = create_engine(MYSQL_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# MongoDB连接
import urllib.parse
from pymongo import MongoClient
encoded_password = urllib.parse.quote_plus(settings.MONGO_PASSWORD)
mongo_client = MongoClient(
    f"mongodb://{settings.MONGO_USERNAME}:{encoded_password}@{settings.MONGO_HOST}:{settings.MONGO_PORT}/{settings.MONGO_DATABASE}?authSource={settings.MONGO_AUTH_DB}"
)
mongo_db = mongo_client[settings.MONGO_DATABASE]

def get_db():
    """获取MySQL数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connections():
    """测试数据库连接"""
    try:
        # 测试Redis连接
        redis_client.ping()
        logger.info("Redis连接成功")
        
        # 测试MySQL连接
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("MySQL连接成功")
        
        # 测试MongoDB连接
        mongo_client.admin.command('ping')
        logger.info("MongoDB连接成功")
        
        # 注意：不在此处测试OSS连接，因为OSS服务使用延迟初始化
        # OSS连接将在首次使用时进行测试
        
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return False