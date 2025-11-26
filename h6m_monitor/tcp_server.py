import asyncio
from typing import Callable, Set


class HeartRateTCPServer:
    def __init__(self, host: str, port: int, get_latest_hr: Callable[[], int]):
        self.host = host
        self.port = port
        self.get_latest_hr = get_latest_hr

        self.tcp_clients: Set[asyncio.StreamWriter] = set()
        self.server: asyncio.AbstractServer | None = None
        self.broadcast_task: asyncio.Task | None = None

    async def handle_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("New TCP client connected.")
        self.tcp_clients.add(writer)

        try:
            while True:
                await asyncio.sleep(0.1) # Keep TCP Connection alive
        except Exception:
            pass
        finally:
            if writer in self.tcp_clients:
                self.tcp_clients.remove(writer)
            writer.close()
            await writer.wait_closed()
            print("TCP client disconnected.")

    async def _broadcast_loop(self):
        while True:
            if self.tcp_clients:
                hr = self.get_latest_hr()
                message = f"{hr}\n".encode()
                for writer in list(self.tcp_clients):
                    try:
                        writer.write(message)
                        await writer.drain()
                    except Exception:
                        if writer in self.tcp_clients:
                            self.tcp_clients.remove(writer)
                        writer.close()
                        await writer.wait_closed()
            await asyncio.sleep(1)

    async def start(self):
        self.server = await asyncio.start_server(
            lambda r, w: asyncio.create_task(self.handle_tcp_client(r, w)),
            self.host,
            self.port,
        )
        print(f"TCP server started on {self.host}:{self.port}")
        self.broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self):
        if self.broadcast_task:
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except asyncio.CancelledError:
                pass

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print("TCP server stopped.")
