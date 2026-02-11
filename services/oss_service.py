#!/usr/bin/env python3
"""
OSS服务 - 用于处理图片上传到MinIO兼容的对象存储
"""

import logging
import io
from typing import Optional, Union
from minio import Minio
from minio.error import S3Error
import urllib.parse
import aiohttp
import asyncio
import requests
from config import settings

logger = logging.getLogger(__name__)


class OSSService:
    """OSS服务类"""
    
    def __init__(self):
        """初始化OSS服务"""
        self.client = None
        self.bucket_name = settings.OSS_BUCKET_NAME
        self.initialized = False
    
    def _initialize_client(self):
        """延迟初始化OSS客户端"""
        if self.initialized and self.client:
            return
            
        try:
            # 解析endpoint以获取host和port
            parsed_url = urllib.parse.urlparse(settings.OSS_ENDPOINT)
            is_secure = parsed_url.scheme == 'https'
            
            self.client = Minio(
                parsed_url.netloc,
                access_key=settings.OSS_ACCESS_KEY,
                secret_key=settings.OSS_SECRET_KEY,
                secure=is_secure
            )
            
            # 确保bucket存在
            self._ensure_bucket_exists()
            self.initialized = True
            logger.info("OSS服务初始化成功")
        except Exception as e:
            logger.error(f"初始化OSS服务时出错: {e}")
            raise
    
    def _ensure_bucket_exists(self):
        """确保bucket存在，如果不存在则创建"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"创建OSS bucket: {self.bucket_name}")
            else:
                logger.debug(f"OSS bucket已存在: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"检查/创建bucket时出错: {e}")
            raise
        except Exception as e:
            logger.error(f"初始化OSS服务时出错: {e}")
            raise
    
    def upload_image_from_url(self, image_url: str, object_name: Optional[str] = None) -> Optional[str]:
        """
        从URL上传图片到OSS
        
        Args:
            image_url: 图片URL
            object_name: 对象名称，如果为None则自动生成
            
        Returns:
            str: 上传后的对象URL，如果失败则返回None
        """
        try:
            # 初始化客户端（如果尚未初始化）
            self._initialize_client()
            
            # 获取图片内容（使用同步方法避免事件循环问题）
            image_data = self._fetch_image_sync(image_url)
            
            if not image_data:
                logger.warning(f"无法获取图片内容: {image_url}")
                return None
            
            return self.upload_image_from_bytes(image_data, object_name, image_url)
        
        except Exception as e:
            logger.error(f"从URL上传图片失败 {image_url}: {e}")
            return None
    
    def _fetch_image_sync(self, image_url: str):
        """同步获取图片内容，避免异步事件循环问题"""
        try:
            logger.debug(f"开始获取图片: {image_url}")
            response = requests.get(image_url, timeout=30)
            if response.status_code == 200:
                logger.debug(f"成功获取图片: {image_url}")
                return response.content
            else:
                logger.error(f"获取图片失败，状态码: {response.status_code}, URL: {image_url}")
                return None
        except Exception as e:
            logger.error(f"获取图片时发生异常 {image_url}: {e}")
            return None
    
    def upload_image_from_bytes(self, image_data: bytes, object_name: Optional[str] = None, 
                                original_url: Optional[str] = None) -> Optional[str]:
        """
        从字节数据上传图片到OSS
        
        Args:
            image_data: 图片字节数据
            object_name: 对象名称，如果为None则自动生成
            original_url: 原始URL，用于日志记录
            
        Returns:
            str: 上传后的对象URL，如果失败则返回None
        """
        try:
            # 初始化客户端（如果尚未初始化）
            self._initialize_client()
            
            # 如果没有提供object_name，则根据URL或时间戳生成
            if not object_name:
                import hashlib
                import time
                
                if original_url:
                    # 使用URL的hash作为文件名
                    url_hash = hashlib.md5(original_url.encode()).hexdigest()[:16]
                    # 尝试获取文件扩展名
                    parsed_url = urllib.parse.urlparse(original_url)
                    path = parsed_url.path
                    ext = path.split('.')[-1] if '.' in path else 'jpg'
                    object_name = f"images/{url_hash}.{ext}"
                else:
                    # 使用时间戳生成文件名
                    timestamp = int(time.time())
                    object_name = f"images/upload_{timestamp}.jpg"
            
            logger.debug(f"开始上传图片到OSS: {object_name}")
            
            # 上传到OSS
            data = io.BytesIO(image_data)
            result = self.client.put_object(
                self.bucket_name,
                object_name,
                data,
                len(image_data)
            )
            
            # 生成访问URL
            object_url = f"{settings.OSS_ENDPOINT}/{self.bucket_name}/{object_name}"
            logger.info(f"图片上传成功: {object_name} -> {object_url}")
            
            return object_url
            
        except S3Error as e:
            logger.error(f"上传图片到OSS失败 (S3Error): {e}")
            return None
        except Exception as e:
            logger.error(f"上传图片到OSS失败: {e}")
            return None
    
    def get_object_url(self, object_name: str) -> Optional[str]:
        """
        获取对象的访问URL
        
        Args:
            object_name: 对象名称
            
        Returns:
            str: 对象访问URL，如果失败则返回None
        """
        try:
            # 初始化客户端（如果尚未初始化）
            self._initialize_client()
            
            return f"{settings.OSS_ENDPOINT}/{self.bucket_name}/{object_name}"
        except Exception as e:
            logger.error(f"获取对象URL失败: {e}")
            return None


# 创建全局OSS服务实例（延迟初始化）
oss_service = OSSService()