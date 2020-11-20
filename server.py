# laser server
from nano_library import K40_CLASS
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
import getopt
import sys

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)


class DummyObject:
    def _dispatch(self, method, params):
        print(method, params)


if __name__ == "__main__":
    opts, args = None, None
    dry_run = len(sys.argv) > 1 and sys.argv[1] in ["-d", "--dry"]

    while True:
        # Create server
        with SimpleXMLRPCServer(('localhost', 8000), requestHandler=RequestHandler, allow_none=True) as server:
            if dry_run:
                k40 = DummyObject()
            else:
                k40 = K40_CLASS()

            server.register_instance(k40)

            # Run the server's main loop
            server.serve_forever()

        print("Server crashed. Restarting...")