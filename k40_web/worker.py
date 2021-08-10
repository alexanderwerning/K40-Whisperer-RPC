from json.decoder import JSONDecodeError
from k40_web.laser_controller.service import Laser_Service


import json
from base64 import b64encode
from k40_web.laser_controller.reporter import Reporter
from queue import Empty

from zmq import Context, Poller, PUB, SUB, SUBSCRIBE, POLLIN
from threading import Thread
from queue import Queue, Empty
import time

context = Context()
task_socket = context.socket(SUB)
task_socket.setsockopt(SUBSCRIBE, b"")
task_socket.bind("tcp://127.0.0.1:6660")
status_socket = context.socket(PUB)
status_socket.bind("tcp://127.0.0.1:5556")
task_poller = Poller()
task_poller.register(task_socket, POLLIN)


def send_msg(msg):
    status_socket.send_string(msg)

def encode_msg(msg, value=None, msg_type=0):
    data = {"content": msg}
    type_tag = {-1: "update", 0:"clear", 1:"status", 2:"information", 3:"warning", 4:"error", 5:"fieldClear", 6:"fieldWarning", 7:"fieldError"}
    data["type"] = type_tag[msg_type]
    if value is not None:
        if type(value) is bytes:
            data["value"] = b64encode(value)
        else:
            data["value"] = value

    print("sent: ", msg)
    send_msg(json.dumps(data))

class JSON_Reporter(Reporter):
    def data(x, y):
        encode_msg(x, value=y, msg_type=-1)

    def clear():
        encode_msg("", msg_type=0)

    def status(x):
        encode_msg(x, msg_type=1)

    def information(x):
        encode_msg(x, msg_type=2)

    def warning(x):
        encode_msg(x, msg_type=3)

    def error(x):
        encode_msg(x, msg_type=4)

    def fieldClear(x):
        encode_msg(x, msg_type=5)

    def fieldWarning(x):
        encode_msg(x, msg_type=6)

    def fieldError(x):
        encode_msg(x, msg_type=7)

service = Laser_Service.instance(JSON_Reporter)
cmd_queue = Queue()

def service_fn():
    while True:
        try:
            cmd = cmd_queue.get(timeout=3)
            if cmd == "exit":
                break
            cmd()
        except Empty:
            pass

service_thread = Thread(target=service_fn)
service_thread.start()

commands = {
    "Initialize_Laser": service.Initialize_Laser,
    "Raster_Eng": service.Raster_Eng,
    "Vector_Eng": service.Vector_Eng,
    "Vector_Cut": service.Vector_Cut,
    "Gcode_Cut": service.Gcode_Cut,
    "Raster_Vector_Eng": service.Raster_Vector_Eng,
    "Vector_Eng_Cut": service.Vector_Eng_Cut,
    "Raster_Vector_Cut": service.Raster_Vector_Cut,
    "Reload_design": service.reload_design,
    "Home": service.Home,
    "Unlock": service.Unlock,
    "Pause": service.Pause,
    "Move_Right": service.Move_Right,
    "Move_Left": service.Move_Left,
    "Move_Up": service.Move_Up,
    "Move_Down": service.Move_Down,
    "Move_UL": service.Move_UL,
    "Move_UC": service.Move_UC,
    "Move_UR": service.Move_UR,
    "Move_CL": service.Move_CL,
    "Move_CC": service.Move_CC,
    "Move_CR": service.Move_CR,
    "Move_LR": service.Move_LR,
    "Move_LL": service.Move_LL,
    "Move_LC": service.Move_LC,
}

commands_with_values = {
    "mouse_click": service.mouse_click,
    "Open_design": service.open_design
}


'''
var_names_strings = [ "board_name",
            "units", 
            "ht_size", 
            
'''
try:
    while True:
        events = dict(task_poller.poll(3))
        if task_socket not in events or events[task_socket] != POLLIN:
            continue
        body = task_socket.recv_string()
        print(" [x] Received %s" % body)
        
        try:
            message = json.loads(body)
        except JSONDecodeError:
            print(f"error decoding: {body}")
            continue
        if message is None:
            print("Error: message is None.")
            continue
        cmd = message["command"]

        print(cmd)
        if cmd == "Stop":
            service.Stop()
        elif cmd in commands:
            cmd_queue.put(commands[cmd])
        elif cmd in commands_with_values:
            value = message["parameter"]
            print(value)
            if type(value) is list:
                cmd_queue.put(lambda: commands_with_values[cmd](*value))
            else:
                cmd_queue.put(lambda: commands_with_values[cmd](value))
        elif cmd == "get":
            param_name = message["key"]
            JSON_Reporter.data(param_name, getattr(service, param_name))
        elif cmd == "set":
            param_name = message["key"]
            param_value = message["value"]
            try:
                setter_fn = getattr(service, "set_"+param_name)
                cmd_queue.put(lambda: setter_fn(param_value))
            except AttributeError as e:
                print(e)
                JSON_Reporter.error(f"{param_name} does not exist")
            #JSON_Reporter.data(param_name, getattr(service, param_name)) # this should be handled by set var function
        else:
            print("sorry i did not understand ", body)
except KeyboardInterrupt:
    cmd_queue.put("exit")
    service_thread.join()
    print("bye!")