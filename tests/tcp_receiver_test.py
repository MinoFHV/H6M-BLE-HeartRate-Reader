import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 8888))

with s:
    while True:
        data = s.recv(1024)
        if not data:
            break
        print("Received:", data.decode().strip())