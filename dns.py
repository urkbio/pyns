import asyncio
import socket
import aiohttp

DOH_SERVER = "https://223.5.5.5/dns-query"  # 使用 Google 的 DoH 服务器进行测试

async def handle_dns_request(data, addr, sock):
    print(f"Received DNS query from {addr}")
    headers = {
        'Content-Type': 'application/dns-message',
        'Accept': 'application/dns-message',
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DOH_SERVER, data=data, headers=headers) as resp:
                if resp.status == 200:
                    doh_response = await resp.read()
                    print(f"Received response from DoH server, sending back to {addr}")
                    sock.sendto(doh_response, addr)
                else:
                    print(f"Error: received status {resp.status} from DoH server")
    except Exception as e:
        print(f"Error while forwarding DNS request: {e}")

async def start_dns_server(local_ip="127.0.0.1", local_port=53):
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((local_ip, local_port))
    except PermissionError as e:
        print(f"Permission denied: {e}")
        return
    
    print(f"DNS forwarder running on {local_ip}:{local_port}, forwarding to DoH server: {DOH_SERVER}")

    while True:
        try:
            # 使用 recvfrom 接收数据，注意异常捕获
            data, addr = await loop.run_in_executor(None, sock.recvfrom, 512)
            asyncio.create_task(handle_dns_request(data, addr, sock))
        except ConnectionResetError as e:
            print(f"Connection reset by peer: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(start_dns_server())
    except KeyboardInterrupt:
        print("Server stopped manually.")

