import asyncio
import socket
import aiohttp
import hashlib
import time

# 配置
DOH_SERVER_IP = "223.5.5.5"  # DoH 服务器的 IP 地址
DOH_PORT = 443  # DoH 使用的端口
CACHE_EXPIRATION = 300  # 缓存过期时间，单位秒
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 2  # 重试延迟时间（秒）

# 缓存字典，保存查询请求的响应
dns_cache = {}

async def fetch_doh_response(data, session):
    """发送 DoH 请求并获取响应"""
    headers = {
        'Content-Type': 'application/dns-message',
        'Accept': 'application/dns-message',
    }
    retries = 0
    while retries < MAX_RETRIES:
        try:
            # 使用指定的 DoH IP 地址，并且通过连接器传递
            connector = aiohttp.TCPConnector(
                ssl=True,  # 开启 SSL
                family=socket.AF_INET,  # 强制使用 IPv4
            )

            # 创建一个新的 ClientSession，并传入连接器
            async with aiohttp.ClientSession(connector=connector) as session:
                # 直接通过 IP 地址连接 DoH 服务器
                url = f"https://{DOH_SERVER_IP}:{DOH_PORT}/dns-query"
                async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        print(f"Error: Received status {resp.status} from DoH server")
        except Exception as e:
            print(f"Error occurred while fetching response from DoH: {e}")
        
        retries += 1
        print(f"Retrying ({retries}/{MAX_RETRIES}) in {RETRY_DELAY} seconds...")
        await asyncio.sleep(RETRY_DELAY)

    return None

async def handle_dns_request(data, addr, sock, session):
    """处理 DNS 请求"""
    print(f"Received DNS query from {addr}")

    # 计算请求的哈希值，作为缓存的键
    query_hash = hashlib.md5(data).hexdigest()

    # 如果缓存中存在该请求并且未过期，则返回缓存的数据
    if query_hash in dns_cache:
        cache_entry = dns_cache[query_hash]
        if time.time() - cache_entry['timestamp'] < CACHE_EXPIRATION:
            print(f"Cache hit for query {query_hash}, sending cached response")
            sock.sendto(cache_entry['response'], addr)
            return
        else:
            print(f"Cache expired for query {query_hash}, fetching new response")

    # 如果缓存中不存在或缓存已过期，则通过 DoH 服务器查询
    response = await fetch_doh_response(data, session)
    
    if response:
        # 更新缓存
        dns_cache[query_hash] = {'response': response, 'timestamp': time.time()}
        print(f"Caching response for query {query_hash}")
        sock.sendto(response, addr)
    else:
        print("Failed to get a valid response from DoH server")

async def start_dns_server(local_ip="127.0.0.1", local_port=53):
    """启动 DNS 服务器"""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((local_ip, local_port))
    except PermissionError as e:
        print(f"Permission denied: {e}")
        return

    print(f"DNS forwarder running on {local_ip}:{local_port}, forwarding to DoH server at {DOH_SERVER_IP}:{DOH_PORT}")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 接收 DNS 查询
                data, addr = await loop.run_in_executor(None, sock.recvfrom, 512)
                asyncio.create_task(handle_dns_request(data, addr, sock, session))
            except Exception as e:
                print(f"Unexpected error occurred: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(start_dns_server())
    except KeyboardInterrupt:
        print("Server stopped manually.")

