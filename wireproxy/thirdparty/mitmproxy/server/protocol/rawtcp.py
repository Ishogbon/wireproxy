import socket

from OpenSSL import SSL

import wireproxy.thirdparty.mitmproxy.net.tcp
from wireproxy.thirdparty.mitmproxy import exceptions, tcp
from wireproxy.thirdparty.mitmproxy import flow
from wireproxy.thirdparty.mitmproxy.server.protocol import base


class RawTCPLayer(base.Layer):
    chunk_size = 4096

    def __init__(self, ctx, ignore=False):
        self.ignore = ignore
        super().__init__(ctx)

    def __call__(self):
        self.connect()

        if not self.ignore:
            f = tcp.TCPFlow(self.client_conn, self.server_conn, self)
            self.channel.ask("tcp_start", f)

        buf = memoryview(bytearray(self.chunk_size))

        client = self.client_conn.connection
        server = self.server_conn.connection
        conns = [client, server]

        # https://github.com/openssl/openssl/issues/6234
        for conn in conns:
            if isinstance(conn, SSL.Connection) and hasattr(SSL._lib, "SSL_clear_mode"):
                SSL._lib.SSL_clear_mode(conn._ssl, SSL._lib.SSL_MODE_AUTO_RETRY)

        try:
            while not self.channel.should_exit.is_set():
                r = wireproxy.thirdparty.mitmproxy.net.tcp.ssl_read_select(conns, 10)
                for conn in r:
                    dst = server if conn == client else client
                    try:
                        size = conn.recv_into(buf, self.chunk_size)
                    except (SSL.WantReadError, SSL.WantWriteError):
                        continue
                    if not size:
                        conns.remove(conn)
                        # Shutdown connection to the other peer
                        if isinstance(conn, SSL.Connection):
                            # We can't half-close a connection, so we just close everything here.
                            # Sockets will be cleaned up on a higher level.
                            return
                        else:
                            dst.shutdown(socket.SHUT_WR)

                        if len(conns) == 0:
                            return
                        continue

                    tcp_message = tcp.TCPMessage(dst == server, buf[:size].tobytes())
                    if not self.ignore:
                        f.messages.append(tcp_message)
                        self.channel.ask("tcp_message", f)
                    dst.sendall(tcp_message.content)

        except (socket.error, exceptions.TcpException, SSL.Error) as e:
            if not self.ignore:
                f.error = flow.Error(
                    "TCP connection closed unexpectedly: {}".format(repr(e))
                )
                self.channel.tell("tcp_error", f)
        finally:
            if not self.ignore:
                self.channel.tell("tcp_end", f)
