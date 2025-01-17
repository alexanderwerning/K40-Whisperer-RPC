#!/usr/bin/env python
'''
This script communicates with the K40 Laser Cutter.

Copyright (C) 2017-2020 Scorch www.scorchworks.com

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
'''
try:
    import usb.core
    import usb.util
    import usb.backend.libusb0
except:
    print("Unable to load USB library (Sending data to Laser will not work.)")
import sys
import os
from k40_web.laser_controller.egv import egv
import xmlrpc.client
from time import time


#######################################################################
#  The one wire CRC algorithm is derived from the OneWire.cpp Library
#  The latest version of this library may be found at:
#  http://www.pjrc.com/teensy/td_libs_OneWire.html
#######################################################################
def OneWireCRC(line):
    crc = 0
    for i in range(len(line)):
        inbyte = line[i]
        for j in range(8):
            mix = (crc ^ inbyte) & 0x01
            crc >>= 1
            if (mix):
                crc ^= 0x8C
            inbyte >>= 1
    return crc
#######################################################################


class K40_CLASS:
    def __init__(self):
        self.dev = None
        self.n_timeouts = 10
        self.timeout = 200   # Time in milliseconds
        self.write_addr = 0x2   # Write address
        self.read_addr = 0x82  # Read address
        self.read_length = 168

        #### RESPONSE CODES ####
        self.OK = 206
        self.BUFFER_FULL = 238
        self.CRC_ERROR = 207
        self.TASK_COMPLETE = 236
        self.UNKNOWN_2 = 239  # after failed initialization followed by succesful initialization
        #######################
        self.hello = [160]
        self.unlock = [166, 0, 73, 83, 50, 80, 70, 70, 70, 70, 70, 70, 70, 70, 70,
                       70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 166, 15]
        self.home = [166, 0, 73, 80, 80, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70,
                     70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 166, 228]
        self.estop = [166, 0, 73, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70,
                      70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 166, 130]
        self.USB_Location = None

    def set_n_timeouts(self, value):
        self.n_timeouts = value

    def set_timeout(self, value):
        self.timeout = value

    def say_hello(self):
        cnt = 0
        status_timeouts = self.n_timeouts
        while cnt < status_timeouts:
            cnt = cnt+1
            try:
                self.send_packet(self.hello)
                break
            except:
                pass
        if cnt >= status_timeouts:
            return None

        response = None
        read_cnt = 0
        while response == None and read_cnt < status_timeouts:
            try:
                response = self.dev.read(
                    self.read_addr, self.read_length, self.timeout)
            except:
                response = None
                read_cnt = read_cnt + 1

        DEBUG = False
        if response != None:
            if DEBUG:
                if int(response[0]) != 255:
                    print(("0: ", response[0]))
                elif int(response[1]) != 206:
                    print(("1: ", response[1]))
                elif int(response[2]) != 111:
                    print(("2: ", response[2]))
                elif int(response[3]) != 8:
                    print(("3: ", response[3]))
                # Get a 3 if you try to initialize when already initialized
                elif int(response[4]) != 19:
                    print(("4: ", response[4]))
                elif int(response[5]) != 0:
                    print(("5: ", response[5]))
                else:
                    print((".",))

            if response[1] == self.OK or \
               response[1] == self.BUFFER_FULL or \
               response[1] == self.CRC_ERROR or \
               response[1] == self.TASK_COMPLETE or \
               response[1] == self.UNKNOWN_2:
                return response[1]
            else:
                return 9999
        else:
            return None

    def unlock_rail(self):
        self.send_packet(self.unlock)

    def e_stop(self):
        self.send_packet(self.estop)

    def home_position(self):
        self.send_packet(self.home)

    def reset_usb(self):
        self.dev.reset()

    def release_usb(self):
        usb.util.dispose_resources(self.dev)
        self.dev = None
        self.USB_Location = None

    def pause_un_pause(self):
        self.send_data([ord('P'), ord('N')], None, None, 1, True, False)

    def none_function(self, dummy, bgcolor):
        # Don't delete this function (used in send_data)
        return False

    def send_data(self, data, reporter, stop_calc, passes, preprocess_crc, wait_for_laser):
        if stop_calc == None:
            stop_calc = []
            stop_calc.append(0)
        if reporter == None:
            reporter = self.none_function

        blank = [166, 0, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70,
                 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 70, 166, 0]
        packets = []
        packet = blank[:]
        cnt = 2
        len_data = len(data)
        for j in range(passes):
            if j == 0:
                istart = 0
            else:
                istart = 1
            if passes > 1:
                if j == passes-1:
                    data[-4] = ord("F")
                else:
                    data[-4] = ord("@")
            timestamp = 0
            for i in range(istart, len_data):
                if cnt > 31:
                    packet[-1] = OneWireCRC(packet[1:len(packet)-2])
                    stamp = int(3*time())  # update every 1/3 of a second
                    if not preprocess_crc:
                        self.send_packet_w_error_checking(
                            packet, reporter, stop_calc)
                        if (stamp != timestamp):
                            timestamp = stamp  # interlock
                            reporter.status("Sending Data to Laser = %.1f%%" %
                                       (100.0*float(i)/float(len_data)))
                    else:
                        packets.append(packet)
                        if (stamp != timestamp):
                            timestamp = stamp  # interlock
                            reporter.status("Calculating CRC data and Generate Packets: %.1f%%" % (
                                100.0*float(i)/float(len_data)))
                    packet = blank[:]
                    cnt = 2

                    if stop_calc[0] == True:
                        self.stop_sending_data()
                        #raise Exception("Action Stopped by User.")
                packet[cnt] = data[i]
                cnt = cnt+1
        packet[-1] = OneWireCRC(packet[1:len(packet)-2])
        if not preprocess_crc:
            self.send_packet_w_error_checking(packet, reporter, stop_calc)
        else:
            packets.append(packet)
            reporter.status("CRC data and Packets are Ready")
        packet_cnt = 0
        for line in packets:
            reporter.clear()
            self.send_packet_w_error_checking(line, reporter, stop_calc)
            packet_cnt = packet_cnt+1.0
            reporter.status("Sending Data to Laser = %.1f%%" %
                       (100.0*packet_cnt/len(packets)))
        ##############################################################
        if wait_for_laser:
            self.wait_for_laser_to_finish(reporter, stop_calc)

    def send_packet_w_error_checking(self, line, reporter=None, stop_calc=None):
        timeout_cnt = 1
        crc_cnt = 1
        while True:
            if stop_calc[0]:
                self.stop_sending_data()

            response = self.say_hello()
            if response == self.BUFFER_FULL:
                while response == self.BUFFER_FULL:
                    response = self.say_hello()
                    reporter.clear()
                    if stop_calc[0]:
                        self.stop_sending_data()
            try:
                self.send_packet(line)
            except:
                timeout_cnt = timeout_cnt+1
                if timeout_cnt < self.n_timeouts:
                    msg = "USB Timeout #%d" % (timeout_cnt)
                    reporter.warning(msg)
                else:
                    msg = "The laser cutter is not responding (%d attempts). Press stop to stop trying!" % (
                        timeout_cnt)
                    reporter.error(msg)
                    # gui_active = update_gui(msg, bgcolor='red')
                    # if not gui_active:
                    #     msg = "The laser cutter is not responding after %d attempts." % (
                    #         timeout_cnt)
                    #     raise Exception(msg)

                if timeout_cnt > 20:
                    # try reconnect to laser
                    try:
                        self.initialize_device(self.USB_Location, False)
                    except:
                        pass

                continue
            ######################################
            response = self.say_hello()

            if response == self.CRC_ERROR:
                crc_cnt = crc_cnt+1
                if crc_cnt < self.n_timeouts:
                    msg = "Data transmission (CRC) error #%d" % (crc_cnt)
                    reporter.warning(msg)
                else:
                    msg = "There are many data transmission errors (%d). Press stop to stop trying!" % (
                        crc_cnt)
                    reporter.error(msg)
                    # gui_active = update_gui(msg, bgcolor='red')
                    # if not gui_active:
                    #     msg = "There are many data transmission errors (%d)." % (
                    #         crc_cnt)
                    #     raise Exception(msg)
                continue
            elif response == None:
                # The controller board is not reportering status. but we will
                # assume things are going OK. until we cannot transmit to the controller.
                break  # break to move on to next packet

            else:  # assume: response == self.OK:
                break  # break to move on to next packet

    def wait_for_laser_to_finish(self, reporter=None, stop_calc=None):
        FINISHED = False
        while not FINISHED:
            response = self.say_hello()
            if response == self.TASK_COMPLETE:
                FINISHED = True
                break
            elif response == None:
                msg = "Laser stopped responding after operation was complete."
                reporter.status(msg, None)
                #raise Exception(msg)
                FINISHED = True
            else:  # assume: response == self.OK:
                msg = "Waiting for the laser to finish."
                reporter.status(msg, None)
            if stop_calc[0]:
                self.stop_sending_data()

    def stop_sending_data(self):
        self.e_stop()
        raise Exception("Action Stopped by User.")

    def send_packet(self, line):
        self.dev.write(self.write_addr, line, self.timeout)

    def rapid_move(self, dxmils, dymils):
        if (dxmils != 0 or dymils != 0):
            data = []
            egv_inst = egv(target=lambda s: data.append(s))
            egv_inst.make_move_data(dxmils, dymils)
            self.send_data(data, None, None, 1, True, False)

    def initialize_device(self, USB_Location, verbose):
        try:
            self.release_usb()
        except:
            pass

        backend = usb.backend.libusb0.get_backend()
        if backend == None and os.name == 'nt':
            exedir = os.path.dirname(sys.executable)
            os.environ['PATH'] = exedir + os.pathsep + os.environ['PATH']

        # Find a laser device
        self.dev = None
        laser_cnt = 0
        if USB_Location == None:
            for device in usb.core.find(idVendor=0x1a86, idProduct=0x5512, find_all=True):
                self.dev = device
                try:
                    self.dev.set_configuration()
                    self.USB_Location = (self.dev.bus, self.dev.address)
                    break
                except:
                    pass
        else:
            self.dev = usb.core.find(
                idVendor=0x1a86, idProduct=0x5512, bus=USB_Location[0], address=USB_Location[1])
            self.USB_Location = (self.dev.bus, self.dev.address)

        if self.dev is None:
            raise Exception(
                "Laser USB Device not found. (libUSB driver may not be installed)")

        if verbose:
            print("-------------- dev --------------")
            print((self.dev))
        # set the active configuration. With no arguments, the first
        # configuration will be the active one
        try:
            self.dev.set_configuration()
        except:
            raise Exception("Unable to set USB Device configuration.")

        # get an endpoint instance
        cfg = self.dev.get_active_configuration()
        if verbose:
            print("-------------- cfg --------------")
            print(cfg)
        intf = cfg[(0, 0)]
        if verbose:
            print("-------------- intf --------------")
            print(intf)
        ep = usb.util.find_descriptor(
            intf,
            # match the first OUT endpoint
            custom_match=lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)
        if ep == None:
            raise Exception("Unable to match the USB 'OUT' endpoint.")
        if verbose:
            print("-------------- ep --------------")
            print(ep)
        # self.dev.clear_halt(ep)
        # print self.dev.get_active_configuration()
        #               dev.ctrl_transfer(bmRequestType, bRequest, wValue=0, wIndex=0, data_or_wLength = None, 2000)
        ctrlxfer = self.dev.ctrl_transfer(
            0x40,      177,   0x0102,        0,                      0, 2000)
        if verbose:
            print("---------- ctrlxfer ------------")
            print(ctrlxfer)

        return self.USB_Location


def K40_CLASS_NETWORK(address):
    return xmlrpc.client.ServerProxy(address, allow_none=True)


if __name__ == "__main__":
    k40 = K40_CLASS()
    run_laser = False

    try:
        USB_LOCATION = k40.initialize_device(verbose=False)

    # the following does not work for python 2.5
    # (RuntimeError, TypeError, NameError, StandardError):
    except RuntimeError as e:
        print(e)
        print("Exiting...")
        os._exit(0)

    print(('initialize with location=', USB_LOCATION))
    k40.initialize_device(k40.USB_Location, verbose=False)

    print(('hello', k40.say_hello()))
    # print k40.reset_position()
    # print k40.unlock_rail()
    print("DONE")
