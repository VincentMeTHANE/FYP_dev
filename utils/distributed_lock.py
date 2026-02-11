import time
import uuid
import asyncio
from typing import Optional
from utils.database import redis_client
import logging

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


class RedisDistributedLock:
    """Redis分布式锁实现，功能等同于Java中的Redisson分布式锁"""
    
    def __init__(self, key: str, timeout: int = 30, retry_interval: float = 0.1):
        """
        初始化分布式锁
        
        Args:
            key: 锁的键名
            timeout: 锁的超时时间（秒）
            retry_interval: 重试间隔（秒）
        """
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.identifier = str(uuid.uuid4())
        self.acquired = False
    
    def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """
        获取锁
        
        Args:
            blocking: 是否阻塞等待
            timeout: 等待超时时间
            
        Returns:
            bool: 是否成功获取锁
        """
        # 计算最终超时时间点
        end_time = time.time() + (timeout or self.timeout) if timeout is not None else None
        
        # 循环尝试获取锁
        while True:
            # 使用Redis SET命令的NX和EX选项实现原子性加锁
            # NX: 只在键不存在时设置值
            # EX: 设置键的过期时间（秒）
            result = redis_client.set(
                self.key,              # 锁的键名
                self.identifier,       # 唯一标识符，用于确保只有持有锁的进程能释放锁
                nx=True,              # 只在键不存在时设置
                ex=self.timeout       # 设置过期时间，防止死锁
            )
            
            # 如果设置成功，说明获取锁成功
            if result:
                self.acquired = True
                logger.debug(f"成功获取锁: {self.key}")
                return True
            
            # 如果不是阻塞模式，直接返回失败
            if not blocking:
                return False
                
            # 检查是否超时
            if end_time and time.time() >= end_time:
                logger.warning(f"获取锁超时: {self.key}")
                return False
                
            # 等待一段时间后重试
            time.sleep(self.retry_interval)
    
    def release(self) -> bool:
        """
        释放锁
        
        Returns:
            bool: 是否成功释放锁
        """
        if not self.acquired:
            return False
        
        # 使用Lua脚本确保原子性释放锁
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = redis_client.eval(lua_script, 1, self.key, self.identifier)
            if result:
                self.acquired = False
                logger.debug(f"成功释放锁: {self.key}")
                return True
            else:
                logger.warning(f"释放锁失败，锁可能已被其他进程持有: {self.key}")
                return False
        except Exception as e:
            logger.error(f"释放锁时发生错误: {e}")
            return False
    
    def extend(self, additional_time: int = None) -> bool:
        """
        延长锁的过期时间
        
        Args:
            additional_time: 额外的时间（秒），默认为原超时时间
            
        Returns:
            bool: 是否成功延长
        """
        if not self.acquired:
            return False
        
        extension = additional_time or self.timeout
        
        # 使用Lua脚本确保原子性延长锁
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("EXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        
        try:
            result = redis_client.eval(lua_script, 1, self.key, self.identifier, extension)
            if result:
                logger.debug(f"成功延长锁: {self.key}, 延长时间: {extension}秒")
                return True
            else:
                logger.warning(f"延长锁失败，锁可能已被其他进程持有: {self.key}")
                return False
        except Exception as e:
            logger.error(f"延长锁时发生错误: {e}")
            return False
    
    def is_locked(self) -> bool:
        """
        检查锁是否被持有
        
        Returns:
            bool: 锁是否被持有
        """
        try:
            return redis_client.exists(self.key) == 1
        except Exception as e:
            logger.error(f"检查锁状态时发生错误: {e}")
            return False
    
    def __enter__(self):
        """支持with语句"""
        if not self.acquire():
            raise RuntimeError(f"无法获取锁: {self.key}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持with语句"""
        self.release()


class AsyncRedisDistributedLock:
    """异步版本的Redis分布式锁"""
    
    def __init__(self, key: str, timeout: int = 30, retry_interval: float = 0.1):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.identifier = str(uuid.uuid4())
        self.acquired = False
    
    async def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """异步获取锁"""
        end_time = time.time() + (timeout or self.timeout) if timeout is not None else None
        
        while True:
            result = redis_client.set(
                self.key,
                self.identifier,
                nx=True,
                ex=self.timeout
            )
            
            if result:
                self.acquired = True
                logger.debug(f"成功获取锁: {self.key}")
                return True
            
            if not blocking:
                return False
                
            if end_time and time.time() >= end_time:
                logger.warning(f"获取锁超时: {self.key}")
                return False
                
            await asyncio.sleep(self.retry_interval)
    
    async def release(self) -> bool:
        """异步释放锁"""
        if not self.acquired:
            return False
        
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = redis_client.eval(lua_script, 1, self.key, self.identifier)
            if result:
                self.acquired = False
                logger.debug(f"成功释放锁: {self.key}")
                return True
            else:
                logger.warning(f"释放锁失败: {self.key}")
                return False
        except Exception as e:
            logger.error(f"释放锁时发生错误: {e}")
            return False
    
    async def __aenter__(self):
        """支持async with语句"""
        if not await self.acquire():
            raise RuntimeError(f"无法获取锁: {self.key}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """支持async with语句"""
        await self.release()


def create_lock(key: str, timeout: int = 30, retry_interval: float = 0.1) -> RedisDistributedLock:
    """创建分布式锁实例"""
    return RedisDistributedLock(key, timeout, retry_interval)


def create_async_lock(key: str, timeout: int = 30, retry_interval: float = 0.1) -> AsyncRedisDistributedLock:
    """创建异步分布式锁实例"""
    return AsyncRedisDistributedLock(key, timeout, retry_interval)