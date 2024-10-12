import asyncio
import socket
import aiohttp
import hashlib
import time
import logging

# 配置
DOH_SERVER_IPS = ["172.93.220.162"]  # 阿里 DoH 服务器 IP 地址
DOH_PORT = 443  # DoH 使用的端口
CACHE_EXPIRATION = 300  # 缓存过期时间，单位秒
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 2  # 重试延迟时间（秒）

# 缓存字典，保存查询请求的响应
dns_cache = {}

# 配置日志记录
logging.basicConfig(
    filename='dns_forwarder.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def fetch_doh_response(data, session):
    """发送 DoH 请求并获取响应"""
    headers = {
        'Content-Type': 'application/dns-message',
        'Accept': 'application/dns-message',
    }
    retries = 0
    while retries < MAX_RETRIES:
        for DOH_SERVER_IP in DOH_SERVER_IPS:
            try:
                # 使用指定的 DoH IP 地址，并且通过连接器传递
                connector = aiohttp.TCPConnector(
                    ssl=True,  # 开启 SSL
                    family=socket.AF_INET,  # 强制使用 IPv4
                )

                # 创建一个新的 ClientSession，并传入连接器
                async with aiohttp.ClientSession(connector=connector) as session:
                    # 直接通过 IP 地址连接 DoH 服务器
                    url = f"https://{DOH_SERVER_IP}:{DOH_PORT}/qtP4UU_wRUY/dns-query"
                    async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            logging.info(f"Successfully fetched DNS response from DoH server {DOH_SERVER_IP}")
                            return await resp.read()
                        else:
                            logging.error(f"Error: Received status {resp.status} from DoH server {DOH_SERVER_IP}")
            except Exception as e:
                logging.error(f"Error occurred while fetching response from DoH server {DOH_SERVER_IP}: {e}")
        
        retries += 1
        logging.info(f"Retrying ({retries}/{MAX_RETRIES}) in {RETRY_DELAY} seconds...")
        await asyncio.sleep(RETRY_DELAY)

    return None

async def handle_dns_request(data, addr, sock, session):
    """处理 DNS 请求"""
    logging.info(f"Received DNS query from {addr}")

    # 计算请求的哈希值，作为缓存的键
    query_hash = hashlib.md5(data).hexdigest()

    # 如果缓存中存在该请求并且未过期，则返回缓存的数据
    if query_hash in dns_cache:
        cache_entry = dns_cache[query_hash]
        if time.time() - cache_entry['timestamp'] < CACHE_EXPIRATION:
            logging.info(f"Cache hit for query {query_hash}, sending cached response")
            sock.sendto(cache_entry['response'], addr)
            return
        else:
            logging.info(f"Cache expired for query {query_hash}, fetching new response")

    # 如果缓存中不存在或缓存已过期，则通过 DoH 服务器查询
    response = await fetch_doh_response(data, session)
    
    if response:
        # 更新缓存
        dns_cache[query_hash] = {'response': response, 'timestamp': time.time()}
        logging.info(f"Caching response for query {query_hash}")
        sock.sendto(response, addr)
    else:
        logging.error(f"Failed to get a valid response from DoH server for query {query_hash}")

async def start_dns_server(local_ip="127.0.0.1", local_port=53):
    """启动 DNS 服务器"""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((local_ip, local_port))
    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        return

    logging.info(f"DNS forwarder running on {local_ip}:{local_port}, forwarding to DoH servers at {', '.join(DOH_SERVER_IPS)}")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 接收 DNS 查询
                data, addr = await loop.run_in_executor(None, sock.recvfrom, 512)
                asyncio.create_task(handle_dns_request(data, addr, sock, session))
            except Exception as e:
                logging.error(f"Unexpected error occurred: {e}")

if __name__ == "__main__":
    try:
        # 在后台启动 DNS 服务器
        logging.info("Starting DNS server in the background...")
        asyncio.run(start_dns_server())
    except KeyboardInterrupt:
        logging.info("Server stopped manually.")


