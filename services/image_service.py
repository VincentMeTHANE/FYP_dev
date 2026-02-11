#!/usr/bin/env python3
"""
图片服务 - 处理图片验证和上传到OSS
"""

import logging
import asyncio
import aiohttp
from typing import List, Dict, Optional
from services.oss_service import oss_service

logger = logging.getLogger(__name__)


class ImageService:
    """图片服务类"""
    
    def __init__(self):
        """初始化图片服务"""
        self.oss_service = oss_service
    
    async def validate_and_upload_images(self, images: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        验证并上传图片到OSS
        
        Args:
            images: 图片列表，每个元素包含'url'和'description'字段
            
        Returns:
            List[Dict[str, str]]: 处理后的图片列表，包含原始信息和OSS URL
        """
        if not images:
            return []
        
        # 过滤和验证图片
        validated_images = await self._filter_images(images)
        
        # 上传到OSS
        uploaded_images = []
        for img in validated_images:
            oss_url = self.oss_service.upload_image_from_url(img['url'])
            if oss_url:
                img['oss_url']=oss_url
                uploaded_images.append(img)
                # uploaded_images.append({
                #     'original_url': img['url'],
                #     'oss_url': oss_url,
                #     'description': img.get('description', '')
                # })
                logger.info(f"图片上传成功: {img['url']} -> {oss_url}")
            else:
                logger.warning(f"图片上传失败: {img['url']}")
        
        return uploaded_images
    
    async def _filter_images(self, images: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        过滤图片：移除描述不符合要求或URL无法访问的图片
        
        Args:
            images: 原始图片列表
            
        Returns:
            List[Dict[str, str]]: 过滤后的图片列表
        """
        if not images:
            return []
        
        filtered_images = []
        
        # 创建验证任务
        validation_tasks = []
        for img in images:
            # 首先检查描述
            if not self._validate_image_description(img.get("description", "")):
                logger.debug(f"图片描述不符合要求，跳过: {img.get('url', '')}")
                continue
            
            # 创建URL验证任务
            validation_tasks.append({
                "img": img,
                "task": self._validate_image_url(img.get("url", ""))
            })
        
        if not validation_tasks:
            logger.info("所有图片都因描述不符合要求被过滤")
            return []
        
        # 并发执行URL验证
        logger.info(f"开始验证 {len(validation_tasks)} 个图片URL的可访问性")
        
        # 执行所有验证任务
        results = await asyncio.gather(*[task["task"] for task in validation_tasks], return_exceptions=True)
        
        # 处理验证结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.debug(f"图片URL验证异常: {validation_tasks[i]['img'].get('url', '')}")
                continue
            
            if result:  # URL可访问
                filtered_images.append(validation_tasks[i]["img"])
            else:
                logger.debug(f"图片URL不可访问，跳过: {validation_tasks[i]['img'].get('url', '')}")
        
        return filtered_images
    
    def _validate_image_description(self, description: str) -> bool:
        """
        验证图片描述是否符合要求
        
        Args:
            description: 图片描述
            
        Returns:
            bool: True表示符合要求，False表示不符合要求
        """
        if not description or not description.strip():
            return False
        
        # 检查描述长度是否大于等于10个字符
        return len(description.strip()) >= 10
    
    async def _validate_image_url(self, url: str, timeout: int = 5) -> bool:
        """
        验证图片URL是否可访问
        
        Args:
            url: 图片URL
            timeout: 超时时间（秒）
            
        Returns:
            bool: True表示可访问，False表示不可访问
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    # 检查状态码，200-299为成功
                    return 200 <= response.status < 300
        except Exception as e:
            logger.debug(f"图片URL验证失败 {url}: {str(e)}")
            return False


# 创建全局图片服务实例
image_service = ImageService()