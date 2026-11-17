import socket

for port in [8080, 8813, 8000, 3000, 5000]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    res = s.connect_ex(('127.0.0.1', port))
    s.close()
    print(f"Port {port}: {'OPEN' if res == 0 else 'CLOSED'}")

