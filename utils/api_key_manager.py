from sqlalchemy.orm import Session
from sqlalchemy import and_, text
from models.models import TavilyKey, TavilyKeyResponse
from utils.database import SessionLocal
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class APIKeyManager:
    """API Key管理器，负责管理Tavily API Key的分配和计数"""
    
    def __init__(self):
        """初始化API Key管理器，不需要额外的初始化参数"""
        pass
    
    def get_available_key(self) -> Optional[TavilyKeyResponse]:
        """
        获取一个可用的API Key，并增加使用计数
        
        Returns:
            TavilyKeyResponse: 可用的API Key信息，如果没有可用key返回None
        """
        # 创建固定的数据库会话
        db = SessionLocal()
        
        try:
            # 从数据库中查找可用的key
            # 条件：is_available=True 且 remaining>0
            # 按remaining降序排列，优先使用剩余次数多的key
            available_key = db.query(TavilyKey).filter(
                and_(
                    TavilyKey.is_available == True,    # 标记为可用
                    TavilyKey.remaining > 0            # 还有剩余次数
                )
            ).order_by(TavilyKey.remaining.asc()).first()
            
            # 如果没有找到可用的key
            if not available_key:
                logger.warning("没有可用的Tavily API Key")
                return None
            
            logger.debug("get available_key result：" + str(available_key))
            # 使用原生 SQL 更新使用计数和剩余次数
            update_sql = text("""
                UPDATE tavily_key 
                SET usage_count = usage_count + 2, 
                    remaining = remaining - 2,
                    is_available = CASE WHEN remaining - 1 <= 0 THEN 0 ELSE 1 END
                WHERE api_key = :api_key
            """)
            
            result = db.execute(update_sql, {"api_key": available_key.api_key})
            db.commit()

            logger.debug("UPDATE tavily_key result：" + str(available_key))
            
            # 检查是否更新成功
            if result.rowcount == 0:
                logger.warning(f"API Key {available_key.api_key[:10]}... 更新失败")
                return None
            
            # 重新查询更新后的数据
            updated_key = db.query(TavilyKey).filter(TavilyKey.api_key == available_key.api_key).first()
            
            if updated_key.remaining <= 0:
                logger.info(f"API Key {updated_key.api_key[:10]}... 已达到使用限制，标记为不可用")
            
            # 返回响应对象
            return TavilyKeyResponse(
                id=updated_key.id,
                api_key=updated_key.api_key,
                usage_count=updated_key.usage_count,
                remaining=updated_key.remaining,
                is_available=updated_key.is_available
            )
            
        except Exception as e:
            logger.error(f"获取API Key时发生错误: {e}")
            # 发生异常时回滚事务
            db.rollback()
            return None
        finally:
            # 确保数据库会话被关闭
            db.close()
    

    def add_keys(self, api_keys: List[str]) -> int:
        """
        批量添加API Key
        
        Args:
            api_keys: API Key列表
            
        Returns:
            int: 成功添加的key数量
        """
        # 创建固定的数据库会话
        db = SessionLocal()
        added_count = 0
        
        try:
            for api_key in api_keys:
                # 检查key是否已存在
                existing_key = db.query(TavilyKey).filter(TavilyKey.api_key == api_key).first()
                if existing_key:
                    logger.warning(f"API Key {api_key[:10]}... 已存在，跳过")
                    continue
                
                # 添加新key
                new_key = TavilyKey(
                    api_key=api_key,
                    usage_count=0,
                    remaining=1000,
                    is_available=True
                )
                db.add(new_key)
                added_count += 1
            
            db.commit()
            logger.info(f"成功添加 {added_count} 个API Key")
            
        except Exception as e:
            logger.error(f"添加API Key时发生错误: {e}")
            db.rollback()
        finally:
            # 确保数据库会话被关闭
            db.close()
        
        return added_count
    
    def get_key_status(self) -> dict:
        """
        获取所有key的状态统计
        
        Returns:
            dict: 状态统计信息
        """
        # 创建固定的数据库会话
        db = SessionLocal()
        
        try:
            total_keys = db.query(TavilyKey).count()
            available_keys = db.query(TavilyKey).filter(
                and_(
                    TavilyKey.is_available == True,
                    TavilyKey.remaining > 0
                )
            ).count()
            
            exhausted_keys = db.query(TavilyKey).filter(
                TavilyKey.remaining <= 0
            ).count()
            
            from sqlalchemy import func
            total_usage = db.query(func.sum(TavilyKey.usage_count)).scalar() or 0
            
            return {
                "total_keys": total_keys,
                "available_keys": available_keys,
                "exhausted_keys": exhausted_keys,
                "total_usage": total_usage,
                "availability_rate": f"{available_keys/total_keys*100:.2f}%" if total_keys > 0 else "0%"
            }
            
        except Exception as e:
            logger.error(f"获取key状态时发生错误: {e}")
            return {}
        finally:
            # 确保数据库会话被关闭
            db.close()
    
    def reset_key_usage(self, key_id: int) -> bool:
        """
        重置指定key的使用次数
        
        Args:
            key_id: Key ID
            
        Returns:
            bool: 是否成功重置
        """
        # 创建固定的数据库会话
        db = SessionLocal()
        
        try:
            key = db.query(TavilyKey).filter(TavilyKey.id == key_id).first()
            if not key:
                logger.warning(f"未找到ID为 {key_id} 的API Key")
                return False
            
            key.usage_count = 0
            key.remaining = 1000
            key.is_available = True
            
            db.commit()
            
            logger.info(f"成功重置API Key {key.api_key[:10]}... 的使用次数")
            return True
            
        except Exception as e:
            logger.error(f"重置key使用次数时发生错误: {e}")
            db.rollback()
            return False
        finally:
            # 确保数据库会话被关闭
            db.close()


# 全局实例
api_key_manager = APIKeyManager()