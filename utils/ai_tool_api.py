import requests
from typing import Literal,Dict, Any
import logging,json
from urllib.parse import urlparse
logger = logging.getLogger(__name__)


def convert_markdown_to_format(md_content: str,
                               convert_type: Literal['docx', 'pptx', 'xlsx', 'epub', 'code', 'html']) -> bytes:
    """
    将 Markdown 转换为指定格式的二进制文件流

    Args:
        md_content: Markdown 文本内容
        convert_type: 转换目标格式 (docx, pptx, xlsx, epub, code, html)

    Returns:
        bytes: 二进制文件数据

    Raises:
        requests.RequestException: 请求异常
        ValueError: 参数错误
    """
    # 固定的API配置
    url = "http://1.94.230.254:32721/copilot-tool/markdown/markdown_to_anything"
    auth_token = "********************"  # 写死的认证令牌

    # 构建请求头
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {auth_token}'
    }

    # 构建请求体
    payload = {
        "md_content": md_content,
        "convert_type": convert_type
    }

    try:
        logger.info(f"请求体: {payload}")
        # 发送请求
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logger.debug(f"响应状态码: {response}")

        # 检查HTTP状态码
        if response.status_code == 200:
            return response.content
        elif response.status_code == 400:
            raise ValueError(f"请求参数错误: {response.text}")
        elif response.status_code == 401:
            raise ValueError("认证失败，请检查认证令牌")
        elif response.status_code == 403:
            raise ValueError("权限不足，无法访问该资源")
        elif response.status_code == 429:
            raise ValueError("请求频率过高，请稍后再试")
        elif response.status_code >= 500:
            raise ValueError(f"服务器内部错误: {response.status_code}")
        else:
            raise ValueError(f"未知错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        raise ValueError("请求超时，请检查网络连接或稍后再试")
    except requests.exceptions.ConnectionError:
        raise ValueError("连接错误，请检查网络连接或服务器地址")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"请求异常: {str(e)}")
    except Exception as e:
        logger.error(f"转换过程中发生未知错误: {str(e)}")
        raise ValueError(f"转换过程中发生未知错误: {str(e)}")


def call_template_padding_api(
        file_url: str,
        padding_rules: Dict[str, Any],
        minio_client=None  # 可选的MinIO客户端实例
) -> Dict[str, Any]:
    """
    调用模板填充接口

    Args:
        file_url: 文件URL（可以是MinIO地址，如 "minio/bucket/object.docx"）或普通HTTP URL
        padding_rules: 填充规则JSON对象
        minio_client: MinIO客户端实例（可选）

    Returns:
        Dict[str, Any]: 接口响应结果

    Raises:
        Exception: 请求失败时抛出异常
    """
    try:
        # 1. 获取文件内容
        file_content: bytes
        file_name: str

        if minio_client and file_url.startswith("minio://"):
            parsed_url = urlparse(file_url)
            bucket_name = parsed_url.netloc
            object_name = parsed_url.path.lstrip('/')

            logger.info(f"从MinIO下载文件: bucket={bucket_name}, object={object_name}")
            file_content = minio_client.get_object(bucket_name, object_name).read()
            file_name = object_name.split("/")[-1]
        else:
            logger.info(f"从HTTP URL下载文件: {file_url}")
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            file_content = response.content
            file_name = file_url.split('/')[-1].split('?')[0]

        # 2. 准备请求数据
        api_url = "http://1.94.230.254:32721/copilot-tool/template/padding"

        files = {
            'file': (file_name, file_content,
                     'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
            'paddingRules': (None, json.dumps(padding_rules))
        }

        data = {}

        # 3. 发送POST请求
        logger.info(f"向API发送请求: {api_url}")
        response = requests.post(api_url, files=files, data=data, timeout=60)

        # 先检查HTTP状态码
        response.raise_for_status()

        return response.content

    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求异常: {str(e)}")
        raise Exception(f"网络请求异常: {str(e)}")
    except Exception as e:
        logger.error(f"处理文件或请求时发生错误: {str(e)}")
        raise Exception(f"处理文件或请求时发生错误: {str(e)}")



# 使用示例
if __name__ == "__main__":
    # 使用你提供的示例数据
    http_file_url = "http://192.168.113.53:9000/deep-research/template/%E5%85%AC%E5%8F%B8%E5%AE%A2%E6%88%B7%E7%94%BB%E5%83%8F%E5%8F%8A%E9%A3%8E%E9%99%A9%E6%8E%92%E6%9F%A5%E6%8A%A5%E5%91%8A20251022-%E6%A8%A1%E7%89%88.docx"
    padding_rules_data = {
        "key_1_8": "hello world",
        "key_2_1_md": "科目xxxx"
    }

    try:
        result = call_template_padding_api(http_file_url, padding_rules_data)
        print("接口调用成功:", result)
    except Exception as e:
        print("调用失败:", str(e))