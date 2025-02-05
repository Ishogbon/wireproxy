import html
import time
from typing import Optional, Tuple

from wireproxy.thirdparty.mitmproxy import connections, version
from wireproxy.thirdparty.mitmproxy import flow
from wireproxy.thirdparty.mitmproxy.net import http

HTTPRequest = http.Request
HTTPResponse = http.Response


class HTTPFlow(flow.Flow):
    """
    An HTTPFlow is a collection of objects representing a single HTTP
    transaction.
    """

    request: HTTPRequest
    response: Optional[HTTPResponse] = None
    error: Optional[flow.Error] = None
    """
    Note that it's possible for a Flow to have both a response and an error
    object. This might happen, for instance, when a response was received
    from the server, but there was an error sending it back to the client.
    """
    server_conn: connections.ServerConnection
    client_conn: connections.ClientConnection
    intercepted: bool = False
    """ Is this flow currently being intercepted? """
    mode: str
    """ What mode was the mitmproxy layer in when receiving this request? """

    def __init__(self, client_conn, server_conn, live=None, mode="regular"):
        super().__init__("http", client_conn, server_conn, live)
        self.mode = mode

    _stateobject_attributes = flow.Flow._stateobject_attributes.copy()
    # mypy doesn't support update with kwargs
    _stateobject_attributes.update(
        dict(request=HTTPRequest, response=HTTPResponse, mode=str)
    )

    def __repr__(self):
        s = "<HTTPFlow"
        for a in ("request", "response", "error", "client_conn", "server_conn"):
            if getattr(self, a, False):
                s += "\r\n  %s = {flow.%s}" % (a, a)
        s += ">"
        return s.format(flow=self)

    @property
    def timestamp_start(self) -> float:
        return self.request.timestamp_start

    def copy(self):
        f = super().copy()
        if self.request:
            f.request = self.request.copy()
        if self.response:
            f.response = self.response.copy()
        return f


def make_error_response(
    status_code: int,
    message: str = "",
    headers: Optional[http.Headers] = None,
) -> HTTPResponse:
    body: bytes = (
        """
        <html>
            <head>
                <title>{status_code} {reason}</title>
            </head>
            <body>
            <h1>{status_code} {reason}</h1>
            <p>{message}</p>
            </body>
        </html>
    """.strip()
        .format(
            status_code=status_code,
            reason=http.status_codes.RESPONSES.get(status_code, "Unknown"),
            message=html.escape(message),
        )
        .encode("utf8", "replace")
    )

    if not headers:
        headers = http.Headers(
            Server=version.MITMPROXY,
            Connection="close",
            Content_Length=str(len(body)),
            Content_Type="text/html",
        )

    return HTTPResponse.make(status_code, body, headers)


def make_connect_request(address: Tuple[str, int]) -> HTTPRequest:
    return HTTPRequest(
        host=address[0],
        port=address[1],
        method=b"CONNECT",
        scheme=b"",
        authority=f"{address[0]}:{address[1]}".encode(),
        path=b"",
        http_version=b"HTTP/1.1",
        headers=http.Headers(),
        content=b"",
        trailers=None,
        timestamp_start=time.time(),
        timestamp_end=time.time(),
    )


def make_connect_response(http_version):
    # Do not send any response headers as it breaks proxying non-80 ports on
    # Android emulators using the -http-mitmproxy option.
    return HTTPResponse(
        http_version,
        200,
        b"Connection established",
        http.Headers(),
        b"",
        None,
        time.time(),
        time.time(),
    )


def make_expect_continue_response():
    return HTTPResponse.make(100)
