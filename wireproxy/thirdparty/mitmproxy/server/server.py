import traceback

from wireproxy.thirdparty.mitmproxy import controller  # noqa
from wireproxy.thirdparty.mitmproxy import (
    connections,
    exceptions,
    flow,
    http,
    log,
    platform,
)
from wireproxy.thirdparty.mitmproxy.net import tcp
from wireproxy.thirdparty.mitmproxy.net.http import http1
from wireproxy.thirdparty.mitmproxy.server import config, modes, root_context
from wireproxy.thirdparty.mitmproxy.utils import human


class DummyServer:
    bound = False

    def __init__(self, config=None):
        self.config = config
        self.address = "dummy"

    def set_channel(self, channel):
        pass

    def serve_forever(self):
        pass

    def shutdown(self):
        pass


class ProxyServer(tcp.TCPServer):
    allow_reuse_address = True
    bound = True
    channel: controller.Channel

    def __init__(self, config: config.ProxyConfig) -> None:
        """
        Raises ServerException if there's a startup problem.
        """
        self.config = config
        try:
            super().__init__((config.options.listen_host, config.options.listen_port))
            if config.options.mode == "transparent":
                platform.init_transparent_mode()
        except Exception as e:
            if self.socket:
                self.socket.close()
            raise exceptions.ServerException(
                "Error starting proxy server: " + repr(e)
            ) from e

    def set_channel(self, channel):
        self.channel = channel

    def handle_client_connection(self, conn, client_address):
        h = ConnectionHandler(conn, client_address, self.config, self.channel)
        h.handle()


class ConnectionHandler:

    def __init__(self, client_conn, client_address, config, channel):
        self.config: config.ProxyConfig = config
        self.client_conn = connections.ClientConnection(
            client_conn, client_address, None
        )
        """@type: wireproxy.thirdparty.mitmproxy.server.connection.ClientConnection"""
        self.channel = channel
        """@type: wireproxy.thirdparty.mitmproxy.controller.Channel"""

    def _create_root_layer(self):
        root_ctx = root_context.RootContext(self.client_conn, self.config, self.channel)

        mode = self.config.options.mode
        if mode.startswith("upstream:"):
            if "socks" in mode:
                return modes.SocksUpstreamProxy(
                    root_ctx,
                    self.config.upstream_server,
                    self.config.options.upstream_auth,
                )
            else:
                return modes.HttpUpstreamProxy(
                    root_ctx, self.config.upstream_server.address
                )
        elif mode == "regular":
            return modes.HttpProxy(root_ctx)
        elif callable(mode):  # pragma: no cover
            return mode(root_ctx)
        else:  # pragma: no cover
            raise ValueError("Unknown mitmproxy mode: %s" % mode)

    def handle(self):
        self.log("clientconnect", "debug")

        root_layer = None
        try:
            root_layer = self._create_root_layer()
            root_layer = self.channel.ask("clientconnect", root_layer)
            if root_layer:
                root_layer()
        except exceptions.Kill:
            self.log(flow.Error.KILLED_MESSAGE, "info")
        except exceptions.ProtocolException as e:
            if isinstance(e, exceptions.ClientHandshakeException):
                self.log(
                    "Client Handshake failed. "
                    "The client may not trust Selenium Wire's certificate for {}.".format(
                        e.server
                    ),
                    "debug",
                )
                self.log(repr(e), "debug")
            elif isinstance(e, exceptions.InvalidServerCertificate):
                self.log(str(e), "warn")
                self.log(
                    "Invalid certificate, closing connection. Pass --ssl-insecure to disable validation.",
                    "warn",
                )
            else:
                if self.config.options.suppress_connection_errors:
                    self.log(repr(e), "debug")
                else:
                    self.log(str(e), "warn")

            # If an error propagates to the topmost level,
            # we send an HTTP error response, which is both
            # understandable by HTTP clients and humans.
            try:
                error_response = http.make_error_response(502, repr(e))
                self.client_conn.send(http1.assemble_response(error_response))
            except exceptions.TcpException:
                pass
        except Exception:
            self.log(traceback.format_exc(), "error")

        self.log("clientdisconnect", "debug")
        if root_layer is not None:
            self.channel.tell("clientdisconnect", root_layer)
        self.client_conn.finish()

    def log(self, msg, level):
        msg = "{}: {}".format(human.format_address(self.client_conn.address), msg)
        self.channel.tell("log", log.LogEntry(msg, level))
