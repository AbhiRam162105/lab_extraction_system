import time
import socket

def wait_for_service(host, port, timeout=60):
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            if time.time() - start_time > timeout:
                return False
            time.sleep(1)

if __name__ == "__main__":
    import sys
    host, port = sys.argv[1], int(sys.argv[2])
    if wait_for_service(host, port):
        print(f"Service {host}:{port} is ready")
        sys.exit(0)
    else:
        print(f"Service {host}:{port} timed out")
        sys.exit(1)
