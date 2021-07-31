from json.decoder import JSONDecodeError
from k40_web.laser_controller.service import Laser_Service

import pika
import time
import json
from base64 import b64encode
from k40_web.laser_controller.reporter import Reporter
from queue import Empty

def work(taskQueue, statusQueue):

    def send_msg(msg):
        statusQueue.put(msg)

    def encode_msg(msg, value=None, msg_type=0):
        data = {"content": msg}
        type_tag = {-1: "update", 0:"clear", 1:"status", 2:"information", 3:"warning", 4:"error", 5:"fieldClear", 6:"fieldWarning", 7:"FieldError"}
        data["type"] = type_tag[msg_type]
        if value is not None:
            if type(value) is bytes:
                data["value"] = b64encode(value)
            else:
                data["value"] = value

        print("sent: ", data)
        send_msg(json.dumps(data))

    class JSON_Reporter(Reporter):
        data = lambda x, y: encode_msg(x, value=y, msg_type=-1)
        clear = lambda: encode_msg("", msg_type=0)
        status = lambda x: encode_msg(x, msg_type=1)
        information = lambda x: encode_msg(x, msg_type=2)
        warning = lambda x: encode_msg(x, msg_type=3)
        error = lambda x: encode_msg(x, msg_type=4)
        fieldClear = lambda x: encode_msg(x, msg_type=5)
        fieldWarning = lambda x: encode_msg(x, msg_type=6)
        fieldError = lambda x: encode_msg(x, msg_type=7)

    service = Laser_Service.instance(JSON_Reporter)

    commands = {
        "Initialize_Laser": service.Initialize_Laser,
        "Raster_Eng": service.Raster_Eng,
        "Vector_Eng": service.Vector_Eng,
        "Vector_Cut": service.Vector_Cut,
        "Gcode_Cut": service.Gcode_Cut,
        "Raster_Vector_Eng": service.Raster_Vector_Eng,
        "Vector_Eng_Cut": service.Vector_Eng_Cut,
        "Raster_Vector_Cut": service.Raster_Vector_Cut,
        "Reload_design": service.Reload_design,
        "Home": service.Home,
        "Unlock": service.Unlock,
        "Stop": service.Stop,
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
        "Entry_Reng_feed_Callback": service.Entry_Reng_feed_Callback,
        "Entry_Veng_feed_Callback": service.Entry_Veng_feed_Callback,
        "Entry_Vcut_feed_Callback": service.Entry_Vcut_feed_Callback,
        "Entry_Step_Callback": service.Entry_Step_Callback,
        "mouse_click": service.mouse_click,
        "Open_design": service.Open_design
    }


    '''
    var_names_strings = ["include_Reng", "include_Veng", "include_Vcut", "include_Gcde",
                "include_Time", "halftone", "negate", "HomeUR", "inputCSYS", "advanced",
                "mirror", "rotate", "engraveUP", "init_home", "post_home", "post_beep",
                "post_disp", "post_exec", "pre_pr_crc", "inside_first", "comb_engrave",
                "comb_vector", "zoom2image", "rotary", "trace_w_laser", "board_name",
                "units", "Reng_feed", "Veng_feed", "Vcut_feed", "jog_step",
                "Reng_passes", "Veng_passes", "Vcut_passes", "Gcde_passes", "rast_step",
                "ht_size", "LaserXsize", "LaserYsize", "LaserXscale", "LaserYscale",
                "LaserRscale", "rapid_feed", "gotoX", "gotoY", "bezier_M1", "bezier_M2",
                "bezier_weight", "trace_gap", "trace_speed", "t_timeout", "n_timeouts",
                "ink_timeout"'''

    while True:
        try:
            body = taskQueue.get(timeout=1)
            print(" [x] Received %s" % body)
            
            try:
                message = json.loads(body)
            except JSONDecodeError:
                print(f"error decoding: {body}")
                return
            if message is None:
                print("Error: message is None.")
                return
            cmd = message["command"]
            value = message["value"]

            print(cmd)
            if cmd in commands:
                commands[cmd]()
            elif cmd in commands_with_values:
                print(value)
                if type(value) is list:
                    commands_with_values[cmd](*value)
                else:
                    commands_with_values[cmd](value)

            else:
                print("sorry i did not understand ", body)

            print(" [x] Done")

        except Empty as e:
            pass