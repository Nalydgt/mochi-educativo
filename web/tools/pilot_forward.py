"""Loopback-only SSH forwarding using the already verified Paramiko transport."""
import socketserver,threading

def serve(transport,web=True):
    servers=[]
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True
    for local,remote in ([(3000,3010),(54321,54321)] if web else [(54321,54321)]):
        def handler_for(port):
            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    channel=transport.open_channel('direct-tcpip',('127.0.0.1',port),self.client_address,timeout=10)
                    if not channel:return
                    def pump(source,target):
                        try:
                            while True:
                                data=source.recv(65536)
                                if not data:break
                                target.sendall(data)
                        except (OSError,EOFError):pass
                        finally:
                            try:target.shutdown(1)
                            except (OSError,AttributeError):pass
                    thread=threading.Thread(target=pump,args=(channel,self.request),daemon=True);thread.start()
                    try:pump(self.request,channel);thread.join(timeout=5)
                    finally:channel.close()
            return Handler
        server=Server(('127.0.0.1',local),handler_for(remote));servers.append(server)
        threading.Thread(target=server.serve_forever,daemon=True).start()
    print('PELUQO privado: http://localhost:3000/expedicion',flush=True)
    try:
        while transport.is_active():threading.Event().wait(1)
    except KeyboardInterrupt:pass
    finally:
        for server in servers:server.shutdown();server.server_close()
