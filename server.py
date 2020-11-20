# laser server
from nano_library import K40_CLASS
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
import getopt
import sys

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

class Server(object):
    def __init__(self, hostport):
        self.server = SimpleXMLRPCServer(hostport, requestHandler=RequestHandler, allow_none=True)

    def register_function(self, function, name=None):
        def _function(args, kwargs):
            return function(*args, **kwargs)
        _function.__name__ = function.__name__
        self.server.register_function(_function, name)

    def serve_forever(self):
        self.server.serve_forever()


class DummyObject:
    def _dispatch(self, method, params):
        print(method, params)


if __name__ == "__main__":
    opts, args = None, None
    dry_run = len(sys.argv) > 1 and sys.argv[1] in ["-d", "--dry"]

    while True:
        # Create server
        with Server(8000) as server:
            if dry_run:
                k40 = DummyObject()
            else:
                k40 = K40_CLASS()

            server.register_function(k40.n_timeouts)
            server.register_function(k40.timeout)
            server.register_function(k40.rapid_move)
            server.register_function(k40.send_data)
            server.register_function(k40.home_position)
            server.register_function(k40.reset_usb)
            server.register_function(k40.pause_un_pause)
            server.register_function(k40.release_usb)
            server.register_function(k40.initialize_device)
            server.register_function(k40.say_hello)
            server.register_function(k40.unlock_rail)

            # Run the server's main loop
            server.serve_forever()

        print("Server crashed. Restarting...")