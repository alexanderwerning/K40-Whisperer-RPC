#!/usr/bin/python
"""
    K40 Whisperer

    Copyright (C) <2017-2020>  <Scorch>
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
from PIL import ImageOps
import PIL
from time import time
import os
from k40_web.laser_controller.utils import *
from k40_web.laser_controller.nano_library import K40_CLASS
from k40_web.laser_controller.egv import egv
from k40_web.laser_controller.ecoords import ECoord
import json
from pathlib import Path
from math import *
import traceback
import sys

from pathlib import Path
from k40_web.laser_controller.filereader import Open_SVG, Open_DXF, Open_G_Code

version = '0.52'
title_text = "K40 Whisperer V"+version

MAXINT = sys.maxsize


try:
    os.chdir(os.path.dirname(__file__))
except:
    pass

config_path = "./config_init.json"

################################################################################
class Vector():
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def aslist(self):
        return [self.x, self.y]

Position = Vector
Dimensions = Vector

class Scale():
    def __init__(self, x, y, r=0):
        self.x = x
        self.y = y
        self.r = r
    
    def aslist(self):
        return [self.x, self.y, self.r]

class DesignTransform():
    def __init__(self, rotate, mirror, negate, halftone, ht_size):
        self.rotate = rotate
        self.mirror = mirror
        self.negate = negate
        self.halftone = halftone
        self.ht_size = ht_size

class BezierSettings():
    def __init__(self, bezier_weight, bezier_M1, bezier_M2):
        self.bezier_weight = bezier_weight
        self.bezier_M1 = bezier_M1
        self.bezier_M2 = bezier_M2

# we work with mm and mm/s internally, but allow for display in inch and in/min
class DisplayUnits():
    def __init__(self, isMetric=True):
        self.isMetric = (isMetric == "mm" or (type(isMetric) == bool and isMetric == True))

    def length_unit(self):
        return "mm" if self.isMetric else "in"
    
    def length_scale(self):
        return 1 if self.isMetric else 25.4
    
    def velocity_unit(self):
        return "mm/s" if self.isMetric else "in/min"
    
    def velocity_scale(self):
        return 1 if self.isMetric else 60.0/25.4
    
    def time_scale(self):
        return 1 if self.isMetric else 60 # min vs s

class SVG_Settings():
    def __init__(self, inkscape_path, ink_timeout, default_pxpi, default_viewbox):
        self.inkscape_path = inkscape_path
        self.ink_timeout = ink_timeout
        self.default_pxpi = default_pxpi
        self.default_viewbox = default_viewbox

class Laser_Service():
    _instance = None
    def __init__(self):
        raise RuntimeError('call instance()')
    
    @classmethod
    def instance(cls, reporter):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            self = cls._instance
            self.w = 780
            self.h = 490
            self.x = -1
            self.y = -1
            self.init_vars()
            self.reporter = reporter
            self.reporter.status("Welcome to K40 Whisperer")
        return cls._instance

    def resetPath(self):
        self.RengData = ECoord()
        self.VengData = ECoord()
        self.VcutData = ECoord()
        self.GcodeData = ECoord()
        self.SCALE = 1
        self.Design_bounds = (0, 0, 0, 0)
        self.UI_image = None
        # if self.HomeUR:
        self.move_head_window_temporary(Position(0.0, 0.0))
        # else:
        #    self.move_head_window_temporary(0.0,0.0)

        self.pos_offset = Vector(0.0, 0.0)
    
    def loadConfig(self):
        with open(Path(config_path), "r") as f:
            config = json.load(f)
        for var, val in config.items():
            setattr(self, var, val)

    def init_vars(self):
        self.loadConfig()
        self.initComplete = 0
        self.stop = [True]

        self.k40 = None
        self.run_time = 0

        self.HOME_DIR = os.path.expanduser("~")

        if not os.path.isdir(self.HOME_DIR):
            self.HOME_DIR = ""

        self.DESIGN_FILE = (self.HOME_DIR+"/None")
        self.EGV_FILE = None

        self.aspect_ratio = 0
        self.laser_pos = Position(0,0)
        # convert config list to vector
        self.laser_bed_size = Dimensions(self.laser_bed_size_[0], self.laser_bed_size_[1])
        self.laser_scale = Scale(self.laser_scale_[0], self.laser_scale_[1], self.LaserRscale)

        self.design_transform = DesignTransform(self.rotate,
                                                self.mirror,
                                                self.negate,
                                                self.halftone,
                                                self.ht_size)

        self.bezier_settings = BezierSettings(self.bezier_weight, self.bezier_M1, self.bezier_M2)
        self.svg_settings = SVG_Settings(inkscape_path="", ink_timeout=self.ink_timeout, default_pxpi=96.0, default_viewbox=(0,0,500,500))

        self.PlotScale = 1.0
        self.GUI_Disabled = False

        self.RengData = ECoord()
        self.VengData = ECoord()
        self.VcutData = ECoord()
        self.GcodeData = ECoord()
        self.SCALE = 1
        self.Design_bounds = (0, 0, 0, 0)
        self.UI_image = None
        self.pos_offset = Position(0,0)
        self.inkscape_warning = False
        

        self.units = DisplayUnits(self.unit_name)

        self.min_vector_speed = 1.1  # in/min
        self.min_raster_speed = 12  # in/min


################################################################################


    def entry_set(self, field, calc_flag=0, new=0):
        if calc_flag == 0 and new == 0:
            try:
                self.reporter.fieldWarning(field)
                self.reporter.warning(" Recalculation required.")
            except:
                pass
        elif calc_flag == 3:
            try:
                self.reporter.fieldError(field)
                self.reporter.error(" Value should be a number. ")
            except:
                pass
        elif calc_flag == 2:
            try:
                self.reporter.fieldError(field)
            except:
                pass
        elif (calc_flag == 0 or calc_flag == 1) and new == 1:
            try:
                self.reporter.status(" ")
                self.reporter.fieldClear(field)
            except:
                pass
        elif (calc_flag == 1) and new == 0:
            try:
                self.reporter.status(" ")
                self.reporter.fieldClear(field)
            except:
                pass

        elif (calc_flag == 0 or calc_flag == 1) and new == 2:
            return 0
        return 1

    def Quit_Click(self, event):
        self.reporter.status("Exiting!")
        self.Release_USB()
    
    def mouse_click(self, x_display_unit, y_display_unit):
        x_mm = x_display_unit / self.units.length_scale()
        y_mm = y_display_unit / self.units.length_scale()
        MAXX = float(self.laser_bed_size.x)
        MINY = -float(self.laser_bed_size.y)
        new_x = round(x_mm * MAXX, 3)
        new_y = round(y_mm * MINY, 3)
        old_x = round(self.laser_pos.x, 3)
        old_y = round(self.laser_pos.y, 3)
        dx = new_x-old_x
        dy = new_y-old_y
        if self.HomeUR:
            dx = -dx
        self.laser_pos.x, self.laser_pos.y = self.XY_in_bounds(dx, dy)
        DXmils = round((self.laser_pos.x - old_x)*1000.0, 0)
        DYmils = round((self.laser_pos.y - old_y)*1000.0, 0)

        if self.Send_Rapid_Move(DXmils, DYmils):
            self.reporter.data("laser_pos", self.laser_pos.aslist())
            self.menu_View_Refresh()

    def XY_in_bounds(self, dx_mm, dy_mm, no_size=False):
        MINX = 0.0
        MAXY = 0.0
        MAXX = float(self.laser_bed_size.x)
        MINY = -float(self.laser_bed_size.y)

        if (self.inputCSYS and self.RengData.image == None) or no_size:
            xmin, xmax, ymin, ymax = 0.0, 0.0, 0.0, 0.0
        else:
            xmin, xmax, ymin, ymax = self.Get_Design_Bounds()

        X = self.laser_pos.x + dx_mm
        Y = self.laser_pos.y + dy_mm
        ################
        dx = xmax-xmin
        dy = ymax-ymin
        if X < MINX:
            X = MINX
        if X+dx > MAXX:
            X = MAXX-dx

        if Y-dy < MINY:
            Y = MINY+dy
        if Y > MAXY:
            Y = MAXY
        ################
        if not no_size:
            XOFF = self.pos_offset.x
            YOFF = self.pos_offset.y
            if X+XOFF < MINX:
                X = X + (MINX-(X+XOFF))
            if X+XOFF > MAXX:
                X = X - ((X+XOFF)-MAXX)
            if Y+YOFF < MINY:
                Y = Y + (MINY-(Y+YOFF))
            if Y+YOFF > MAXY:
                Y = Y - ((Y+YOFF)-MAXY)
        ################
        X = round(X, 3)
        Y = round(Y, 3)
        return X, Y

    def refreshTime(self):
        if not self.include_Time:
            return
        if self.units == 'in':
            factor = 60.0
        else:
            factor = 25.4

        Raster_eng_feed = float(self.Reng_feed) / factor
        Vector_eng_feed = float(self.Veng_feed) / factor
        Vector_cut_feed = float(self.Vcut_feed) / factor

        Raster_eng_passes = float(self.Reng_passes)
        Vector_eng_passes = float(self.Veng_passes)
        Vector_cut_passes = float(self.Vcut_passes)
        Gcode_passes = float(self.Gcde_passes)

        rapid_feed = 100.0 / 25.4   # 100 mm/s move feed to be confirmed

        if self.RengData.rpaths:
            Reng_time = 0
        else:
            Reng_time = None
        Veng_time = 0
        Vcut_time = 0

        if self.RengData.len != None:
            # these equations are a terrible hack based on measured raster engraving times
            # to be fixed someday
            if Raster_eng_feed*60.0 <= 300:
                accel_time = 8.3264*(Raster_eng_feed*60.0)**(-0.7451)
            else:
                accel_time = 2.5913*(Raster_eng_feed*60.0)**(-0.4795)

            t_accel = self.RengData.n_scanlines * accel_time
            Reng_time = ((self.RengData.len)/Raster_eng_feed) * \
                Raster_eng_passes + t_accel
        if self.VengData.len != None:
            Veng_time = (self.VengData.len / Vector_eng_feed +
                         self.VengData.move / rapid_feed) * Vector_eng_passes
        if self.VcutData.len != None:
            Vcut_time = (self.VcutData.len / Vector_cut_feed +
                         self.VcutData.move / rapid_feed) * Vector_cut_passes

        Gcode_time = self.GcodeData.gcode_time * Gcode_passes

        self.Reng_time.set("Raster Engrave: %s" %
                           (format_time(Reng_time)))
        self.Veng_time.set("Vector Engrave: %s" %
                           (format_time(Veng_time)))
        self.Vcut_time.set("    Vector Cut: %s" %
                           (format_time(Vcut_time)))
        self.Gcde_time.set("         Gcode: %s" %
                           (format_time(Gcode_time)))

        ##########################################
        cszw = int(self.PreviewCanvas.cget("width"))
        cszh = int(self.PreviewCanvas.cget("height"))
        HUD_vspace = 15
        HUD_X = cszw-5
        HUD_Y = cszh-5

        w = int(self.master.winfo_width())
        h = int(self.master.winfo_height())
        HUD_X2 = w-20
        HUD_Y2 = h-75

        self.PreviewCanvas.delete("HUD")
        self.calc_button.place_forget()

        if self.GcodeData.ecoords == []:
            self.PreviewCanvas.create_text(
                HUD_X, HUD_Y, fill="red", text=self.Vcut_time, anchor="se", tags="HUD")
            self.PreviewCanvas.create_text(
                HUD_X, HUD_Y-HUD_vspace, fill="blue", text=self.Veng_time, anchor="se", tags="HUD")

            if (Reng_time == None):
                self.calc_button.place(
                    x=HUD_X2, y=HUD_Y2, width=120+20, height=17, anchor="se")
            else:
                self.calc_button.place_forget()
                self.PreviewCanvas.create_text(HUD_X, HUD_Y-HUD_vspace*2, fill="black",
                                               text=self.Reng_time, anchor="se", tags="HUD")
        else:
            self.PreviewCanvas.create_text(
                HUD_X, HUD_Y, fill="black", text=self.Gcde_time, anchor="se", tags="HUD")
        ##########################################

    def Settings_ReLoad_Click(self, event):
        win_id = self.grab_current()

    def Close_Current_Window_Click(self, event=None):
        current_name = event.widget.winfo_parent()
        win_id = event.widget.nametowidget(current_name)
        win_id.destroy()

    # Left Column #
    #############################
    def Entry_Reng_feed_Check(self):
        try:
            value = float(self.Reng_feed)
            vfactor = (25.4/60.0)/self.feed_factor()
            low_limit = self.min_raster_speed*vfactor
            if value < low_limit:
                self.reporter.status(
                    " Feed Rate should be greater than or equal to %f " % (low_limit))
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Reng_feed_Callback(self, value):
        self.Reng_feed = value
        self.entry_set("Reng_feed",
                       self.Entry_Reng_feed_Check(), new=1)
    #############################

    def Entry_Veng_feed_Check(self):
        try:
            value = float(self.Veng_feed)
            vfactor = (25.4/60.0)/self.feed_factor()
            low_limit = self.min_vector_speed*vfactor
            if value < low_limit:
                self.reporter.status(
                    " Feed Rate should be greater than or equal to %f " % (low_limit))
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Veng_feed_Callback(self, value):
        self.Veng_feed = value
        self.entry_set("Veng_feed",
                       self.Entry_Veng_feed_Check(), new=1)
    #############################

    def Entry_Vcut_feed_Check(self):
        try:
            value = float(self.Vcut_feed)
            vfactor = (25.4/60.0)/self.feed_factor()
            low_limit = self.min_vector_speed*vfactor
            if value < low_limit:
                self.reporter.status(
                    " Feed Rate should be greater than or equal to %f " % (low_limit))
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Vcut_feed_Callback(self, value):
        self.Vcut_feed = value
        self.entry_set("Vcut_feed",
                       self.Entry_Vcut_feed_Check(), new=1)

    #############################
    def Entry_Step_Check(self):
        try:
            value = float(self.jog_step)
            if value <= 0.0:
                self.reporter.status(" Step should be greater than 0.0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Step_Callback(self, varName, index, mode):
        self.entry_set("Step", self.Entry_Step_Check(), new=1)

    #############################

    def Entry_GoToX_Check(self):
        try:
            value = float(self.gotoX)
            if (value < 0.0) and (not self.HomeUR):
                self.reporter.status(" Value should be greater than 0.0 ")
                return 2  # Value is invalid number
            elif (value > 0.0) and self.HomeUR:
                self.reporter.status(" Value should be less than 0.0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_GoToX_Callback(self, varName, index, mode):
        self.entry_set("GoToX", self.Entry_GoToX_Check(), new=1)

    #############################
    def Entry_GoToY_Check(self):
        try:
            value = float(self.gotoY)
            if value > 0.0:
                self.reporter.status(" Value should be less than 0.0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_GoToY_Callback(self, varName, index, mode):
        self.entry_set("GoToY", self.Entry_GoToY_Check(), new=1)

    #############################
    def Entry_Rstep_Check(self):
        try:
            value = get_raster_step_1000in(self.rast_step)
            if value <= 0 or value > 63:
                self.reporter.status(
                    " Step should be between 0.001 and 0.063 in")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Rstep_Callback(self, varName, index, mode):
        self.RengData.reset_path()
        self.refreshTime()
        self.entry_set("Rstep", self.Entry_Rstep_Check(), new=1)

##    ###########################

#############################
    # End Left Column #
#############################
    def bezier_weight_Callback(self, varName=None, index=None, mode=None):
        self.Reset_RasterPath_and_Update_Time()
        self.bezier_plot()

    def bezier_M1_Callback(self, varName=None, index=None, mode=None):
        self.Reset_RasterPath_and_Update_Time()
        self.bezier_plot()

    def bezier_M2_Callback(self, varName=None, index=None, mode=None):
        self.Reset_RasterPath_and_Update_Time()
        self.bezier_plot()

    def bezier_plot(self):
        self.BezierCanvas.delete('bez')

        #self.BezierCanvas.create_line( 5,260-0,260,260-255,fill="black", capstyle="round", width = 2, tags='bez')
        M1 = float(self.bezier_M1)
        M2 = float(self.bezier_M2)
        w = float(self.bezier_weight)
        num = 10
        x, y = generate_bezier(M1, M2, w, n=num)
        for i in range(0, num):
            self.BezierCanvas.create_line(5+x[i], 260-y[i], 5+x[i+1], 260-y[i+1], fill="black",
                                          capstyle="round", width=2, tags='bez')
        self.BezierCanvas.create_text(
            128, 0, text="Output Level vs. Input Level", anchor="n", tags='bez')

    #############################

    def Entry_Ink_Timeout_Check(self):
        try:
            value = float(self.ink_timeout)
            if value < 0.0:
                self.reporter.status(" Timeout should be 0 or greater")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Ink_Timeout_Callback(self, varName, index, mode):
        self.entry_set("Ink_Timeout",
                       self.Entry_Ink_Timeout_Check(), new=1)

    #############################

    def Entry_Timeout_Check(self):
        try:
            value = float(self.t_timeout)
            if value <= 0.0:
                self.reporter.status(" Timeout should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Timeout_Callback(self, varName, index, mode):
        self.entry_set("Timeout", self.Entry_Timeout_Check(), new=1)

    #############################
    def Entry_N_Timeouts_Check(self):
        try:
            value = float(self.n_timeouts)
            if value <= 0.0:
                self.reporter.status(" N_Timeouts should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_N_Timeouts_Callback(self, varName, index, mode):
        self.entry_set("N_Timeouts",
                       self.Entry_N_Timeouts_Check(), new=1)

    #############################
    def Entry_N_EGV_Passes_Check(self):
        try:
            value = int(self.n_egv_passes)
            if value < 1:
                self.reporter.status(" EGV passes should be 1 or higher")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_N_EGV_Passes_Callback(self, varName, index, mode):
        self.entry_set("N_EGV_Passes",
                       self.Entry_N_EGV_Passes_Check(), new=1)

    #############################
    def Entry_Laser_Area_Width_Check(self):
        try:
            value = float(self.laser_bed_size.x)
            if value <= 0.0:
                self.reporter.status(" Width should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Laser_Area_Width_Callback(self, varName, index, mode):
        self.entry_set("Laser_Area_Width",
                       self.Entry_Laser_Area_Width_Check(), new=1)

    #############################
    def Entry_Laser_Area_Height_Check(self):
        try:
            value = float(self.laser_bed_size.y)
            if value <= 0.0:
                self.reporter.status(" Height should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Laser_Area_Height_Callback(self, varName, index, mode):
        self.entry_set("Laser_Area_Height",
                       self.Entry_Laser_Area_Height_Check(), new=1)

    #############################

    def Entry_Laser_X_Scale_Check(self):
        try:
            value = float(self.laser_pos.xscale)
            if value <= 0.0:
                self.reporter.status(
                    " X scale factor should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.Reset_RasterPath_and_Update_Time()
        return 0         # Value is a valid number

    def Entry_Laser_X_Scale_Callback(self, varName, index, mode):
        self.entry_set("Laser_X_Scale",
                       self.Entry_Laser_X_Scale_Check(), new=1)
    #############################

    def Entry_Laser_Y_Scale_Check(self):
        try:
            value = float(self.laser_pos.yscale)
            if value <= 0.0:
                self.reporter.status(
                    " Y scale factor should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.Reset_RasterPath_and_Update_Time()
        return 0         # Value is a valid number

    def Entry_Laser_Y_Scale_Callback(self, varName, index, mode):
        self.entry_set(self.Entry_Laser_Y_Scale,
                       self.Entry_Laser_Y_Scale_Check(), new=1)

    #############################
    def Entry_Laser_R_Scale_Check(self):
        try:
            value = float(self.laser_scale.r)
            if value <= 0.0:
                self.reporter.status(
                    " Rotary scale factor should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.Reset_RasterPath_and_Update_Time()
        return 0         # Value is a valid number

    def Entry_Laser_R_Scale_Callback(self, varName, index, mode):
        self.entry_set("Laser_R_Scale",
                       self.Entry_Laser_R_Scale_Check(), new=1)

    #############################
    def Entry_Laser_Rapid_Feed_Check(self):
        try:
            value = float(self.rapid_feed)
            vfactor = (25.4/60.0)/self.feed_factor()
            low_limit = 1.0*vfactor
            if value != 0 and value < low_limit:
                self.reporter.status(
                    " Rapid feed should be greater than or equal to %f (or 0 for default speed) " % (low_limit))
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        return 0         # Value is a valid number

    def Entry_Laser_Rapid_Feed_Callback(self, varName, index, mode):
        self.entry_set("Laser_Rapid_Feed",
                       self.Entry_Laser_Rapid_Feed_Check(), new=1)

    # Advanced Column #
    #############################
    def Entry_Reng_passes_Check(self):
        try:
            value = int(self.Reng_passes)
            if value < 1:
                self.reporter.status(
                    " Number of passes should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Reng_passes_Callback(self, varName, index, mode):
        self.entry_set("Reng_passes",
                       self.Entry_Reng_passes_Check(), new=1)
    #############################

    def Entry_Veng_passes_Check(self):
        try:
            value = int(self.Veng_passes)
            if value < 1:
                self.reporter.status(
                    " Number of passes should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Veng_passes_Callback(self, varName, index, mode):
        self.entry_set(self.Entry_Veng_passes,
                       self.Entry_Veng_passes_Check(), new=1)
    #############################

    def Entry_Vcut_passes_Check(self):
        try:
            value = int(self.Vcut_passes)
            if value < 1:
                self.reporter.status(
                    " Number of passes should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Vcut_passes_Callback(self, varName, index, mode):
        self.entry_set("Vcut_passes",
                       self.Entry_Vcut_passes_Check(), new=1)

    #############################
    def Entry_Gcde_passes_Check(self):
        try:
            value = int(self.Gcde_passes)
            if value < 1:
                self.reporter.status(
                    " Number of passes should be greater than 0 ")
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Gcde_passes_Callback(self, varName, index, mode):
        self.entry_set("Gcde_passes",
                       self.Entry_Gcde_passes_Check(), new=1)

    #############################

    def Entry_Trace_Gap_Check(self):
        try:
            value = float(self.trace_gap)
        except:
            return 3     # Value not a number
        self.menu_View_Refresh()
        return 0         # Value is a valid number

    def Entry_Trace_Gap_Callback(self, varName, index, mode):
        self.entry_set("Trace_Gap",
                       self.Entry_Trace_Gap_Check(), new=1)

    #############################

    def Entry_Trace_Speed_Check(self):
        try:
            value = float(self.trace_speed)
            vfactor = (25.4/60.0)/self.feed_factor()
            low_limit = self.min_vector_speed*vfactor
            if value < low_limit:
                self.reporter.status(
                    " Feed Rate should be greater than or equal to %f " % (low_limit))
                return 2  # Value is invalid number
        except:
            return 3     # Value not a number
        self.refreshTime()
        return 0         # Value is a valid number

    def Entry_Trace_Speed_Callback(self, varName, index, mode):
        self.entry_set("Trace_Speed",
                       self.Entry_Trace_Speed_Check(), new=1)

    #############################
    def Inkscape_Path_Click(self, event):
        self.Inkscape_Path_Message()
        win_id = self.grab_current()
        newfontdir = askopenfilename(filetypes=[("Executable Files", ("inkscape.exe", "*inkscape*")),
                                                ("All Files", "*")],
                                     initialdir=self.inkscape_path)
        if newfontdir != "" and newfontdir != ():
            if type(newfontdir) is not str:
                newfontdir = newfontdir.encode("utf-8")
            self.inkscape_path.set(newfontdir)

        try:
            win_id.withdraw()
            win_id.deiconify()
        except:
            pass

    def Inkscape_Path_Message(self, event=None):
        if self.inkscape_warning == False:
            self.inkscape_warning = True
            msg1 = "Beware:"
            msg2 = "Most people should leave the 'Inkscape Executable' entry field blank. "
            msg3 = "K40 Whisperer will find Inkscape in one of the the standard locations after you install Inkscape."
            self.reporter.information(msg1+" "+msg2+msg3)

    def Reload_design(self):
        self.Open_design(self.DESIGN_FILE)

    def Open_design(self, filename):
        if self.GUI_Disabled:
            self.reporter.status("Busy")
            return
        filepath = Path(filename)

        if not filepath.is_file():
            self.reporter.error("File not found.")
            return

        fileExtension = filepath.suffix
        self.reporter.status(f"Opening '{filepath.name}'")
        TYPE = fileExtension.upper()
        if TYPE == '.DXF':
            self.resetPath()
            result = Open_DXF(filepath, self.design_scale, self.reporter)
            if result is not None:
                (self.VcutData,
                self.VengData,
                self.RengData,
                self.Design_bounds) = result
        elif TYPE == '.SVG':
            self.resetPath()
            result = Open_SVG(filepath,
                            self.design_scale,
                            self.svg_settings,
                            self.reporter)
            if result is not None:
                (self.VcutData,
                self.VengData,
                self.RengData,
                self.Design_bounds) = result
        elif TYPE == '.EGV':
            self.EGV_Send_Window(filepath)
        else:
            self.resetPath()
            result = Open_G_Code(filepath,
                                self.reporter)
            if result is not None:
                (self.GcodeData,
                self.Design_bounds) = result

        self.DESIGN_FILE = filepath
        
        self.Plot_Data()

    def menu_File_Raster_Engrave(self):
        self.menu_File_save_EGV(operation_type="Raster_Eng")

    def menu_File_Vector_Engrave(self):
        self.menu_File_save_EGV(operation_type="Vector_Eng")

    def menu_File_Vector_Cut(self):
        self.menu_File_save_EGV(operation_type="Vector_Cut")

    def menu_File_G_Code(self):
        self.menu_File_save_EGV(operation_type="Gcode_Cut")

    def menu_File_Raster_Vector_Engrave(self):
        self.menu_File_save_EGV(operation_type="Raster_Eng-Vector_Eng")

    def menu_File_Vector_Engrave_Cut(self):
        self.menu_File_save_EGV(operation_type="Vector_Eng-Vector_Cut")

    def menu_File_Raster_Vector_Cut(self):
        self.menu_File_save_EGV(
            operation_type="Raster_Eng-Vector_Eng-Vector_Cut")

    def menu_File_save_EGV(self, operation_type=None, default_name="out.EGV"):
        self.stop[0] = False
        if DEBUG:
            start = time()
        fileName, fileExtension = os.path.splitext(self.DESIGN_FILE)
        init_file = os.path.basename(fileName)
        default_name = init_file+"_"+operation_type

        if self.EGV_FILE != None:
            init_dir = os.path.dirname(self.EGV_FILE)
        else:
            init_dir = os.path.dirname(self.DESIGN_FILE)

        if (not os.path.isdir(init_dir)):
            init_dir = self.HOME_DIR

        fileName, fileExtension = os.path.splitext(default_name)
        init_file = os.path.basename(fileName)

        filename = asksaveasfilename(defaultextension='.EGV',
                                     filetypes=[("EGV File", "*.EGV")],
                                     initialdir=init_dir,
                                     initialfile=init_file)

        if filename != '' and filename != ():

            if operation_type.find("Raster_Eng") > -1:
                self.make_raster_coords()
            else:
                self.reporter.warning("No raster data to engrave")

            self.send_data(operation_type=operation_type,
                           output_filename=filename)
            self.EGV_FILE = filename
        if DEBUG:
            print(("time = %d seconds" % (int(time()-start))))
        self.stop[0] = True

    def menu_File_Open_EGV(self):
        init_dir = os.path.dirname(self.DESIGN_FILE)
        if (not os.path.isdir(init_dir)):
            init_dir = self.HOME_DIR
        fileselect = askopenfilename(filetypes=[("Engraver Files", ("*.egv", "*.EGV")),
                                                ("All Files", "*")],
                                     initialdir=init_dir)
        if fileselect != '' and fileselect != ():
            self.resetPath()
            self.DESIGN_FILE = fileselect
            self.EGV_Send_Window(fileselect)

    def Open_EGV(self, filemname, n_passes=1):
        self.stop[0] = False
        EGV_data = []
        value1 = ""
        value2 = ""
        value3 = ""
        value4 = ""
        data = ""
        # value1 and value2 are the absolute y and x starting positions
        # value3 and value4 are the absolute y and x end positions
        with open(filemname) as f:
            while True:
                # Skip header
                c = f.read(1)
                while c != "%" and c:
                    c = f.read(1)
                # Read 1st Value
                c = f.read(1)
                while c != "%" and c:
                    value1 = value1 + c
                    c = f.read(1)
                y_start_mils = int(value1)*self.design_scale
                # Read 2nd Value
                c = f.read(1)
                while c != "%" and c:
                    value2 = value2 + c
                    c = f.read(1)
                x_start_mils = int(value2)*self.design_scale
                # Read 3rd Value
                c = f.read(1)
                while c != "%" and c:
                    value3 = value3 + c
                    c = f.read(1)
                y_end_mils = int(value3)*self.design_scale
                # Read 4th Value
                c = f.read(1)
                while c != "%" and c:
                    value4 = value4 + c
                    c = f.read(1)
                x_end_mils = int(value4)*self.design_scale
                break

            # Read Data
            while True:
                c = f.read(1)
                if not c:
                    break
                if c == '\n' or c == ' ' or c == '\r':
                    pass
                else:
                    data = data+"%c" % c
                    EGV_data.append(ord(c)*self.design_scale)

        if ((x_end_mils != 0) or (y_end_mils != 0)):
            n_passes = 1
        else:
            x_start_mils = 0
            y_start_mils = 0

        try:
            self.send_egv_data(EGV_data, n_passes)
        except MemoryError as e:
            msg1 = "Memory Error:"
            msg2 = "Memory Error:  Out of Memory."
            self.reporter.error(msg2)

        except Exception as e:
            print(e)
            msg1 = "Sending Data Stopped: "
            msg2 = "%s" % (e)
            if msg2 == "":
                formatted_lines = traceback.format_exc().splitlines()
            self.reporter.error((msg1+msg2).split("\n")[0])

        # rapid move back to starting position
        dxmils = -(x_end_mils - x_start_mils)
        dymils = y_end_mils - y_start_mils
        self.Send_Rapid_Move(dxmils, dxmils)
        self.stop[0] = True

    #####################################################################
    def make_raster_coords(self):
        make_raster_coords(self.RengData, self.laser_scale, self.design_transform, self.isRotary, self.bezier_settings, self.reporter, self.rast_step)

    ##########################################################################

    def Get_Design_Bounds(self):
        if self.rotate:
            ymin = self.Design_bounds[0]
            ymax = self.Design_bounds[1]
            xmin = -self.Design_bounds[3]
            xmax = -self.Design_bounds[2]
        else:
            xmin, xmax, ymin, ymax = self.Design_bounds
        return (xmin, xmax, ymin, ymax)
    
    def move_head_window_temporary(self, offset):
        if self.GUI_Disabled:
            return
        dx_inches = round(offset.x, 3)
        dy_inches = round(offset.y, 3)
        Xnew, Ynew = self.XY_in_bounds(dx_inches, dy_inches, no_size=True)

        pos_offset_X = round((Xnew-self.laser_pos.x), 3)
        pos_offset_Y = round((Ynew-self.laser_pos.y), 3)
        new_pos_offset = Position(pos_offset_X, pos_offset_Y)

        if self.inputCSYS and self.RengData.image == None:
            new_pos_offset = Position(0, 0)
            xdist = -self.pos_offset.x
            ydist = -self.pos_offset.y
        else:
            xdist = -self.pos_offset.x + new_pos_offset.x
            ydist = -self.pos_offset.y + new_pos_offset.y

        if self.k40 != None:
            if self.Send_Rapid_Move(xdist*1000, ydist*1000):
                self.pos_offset = new_pos_offset
                self.reporter.data("pos_offset", self.pos_offset.aslist())
        else:
            self.pos_offset = new_pos_offset
            self.reporter.data("pos_offset", self.pos_offset.aslist())


    def Move_in_design_space(self, relative_x_offset, relative_y_offset):
        xmin, xmax, ymin, ymax = self.Get_Design_Bounds()

        if self.HomeUR:
            relative_x_offset = 1-relative_x_offset

        x_offset = round(relative_x_offset * (xmax-xmin), 3)
        y_offset = round(relative_y_offset * (ymax-ymin), 3)

        Xnew = self.laser_pos.x + x_offset
        Ynew = self.laser_pos.y + y_offset
        if (Xnew <= self.laser_bed_size.x+.001
            and Ynew >= -self.laser_bed_size.y-.001):
            self.move_head_window_temporary(Position(x_offset, -y_offset))

    def Move_UL(self, dummy=None):
        self.Move_in_design_space(0, 0)

    def Move_UC(self, dummy=None):
        self.Move_in_design_space(0.5, 0)

    def Move_UR(self, dummy=None):
        self.Move_in_design_space(1, 0)

    def Move_CL(self, dummy=None):
        self.Move_in_design_space(0, 0.5)

    def Move_CC(self, dummy=None):
        self.Move_in_design_space(0.5, 0.5)

    def Move_CR(self, dummy=None):
        self.Move_in_design_space(1, 0.5)

    def Move_LL(self, dummy=None):
        self.Move_in_design_space(0, 1)

    def Move_LC(self, dummy=None):
        self.Move_in_design_space(0.5, 1)

    def Move_LR(self, dummy=None):
        self.Move_in_design_space(1, 1)

    def Move_Arbitrary(self, MoveX, MoveY, dummy=None):
        if self.GUI_Disabled:
            self.reporter.status("Busy")
            return
        if self.HomeUR:
            DX = -MoveX
        else:
            DX = MoveX
        DY = MoveY
        NewXpos = self.pos_offset.x+DX
        NewYpos = self.pos_offset.y+DY
        self.move_head_window_temporary(Position(NewXpos, NewYpos))

    def Move_Arb_Step(self, dx, dy):
        if self.GUI_Disabled:
            self.reporter.status("Busy")
            return
        if self.units == "in":
            dx_inches = round(dx,3)
            dy_inches = round(dy,3)
        else:
            dx_inches = round(dx/25.4,3)
            dy_inches = round(dy/25.4,3)
        self.Move_Arbitrary(dx_inches, dy_inches)

    def Move_Arb_Right(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Move_Arb_Step(JOG_STEP, 0)

    def Move_Arb_Left(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Move_Arb_Step(-JOG_STEP, 0)

    def Move_Arb_Up(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Move_Arb_Step(0, JOG_STEP)

    def Move_Arb_Down(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Move_Arb_Step(0, -JOG_STEP)

    ####################################################

    def Move_Right(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Rapid_Move(JOG_STEP, 0)

    def Move_Left(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Rapid_Move(-JOG_STEP, 0)

    def Move_Up(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Rapid_Move(0, JOG_STEP)

    def Move_Down(self, dummy=None):
        JOG_STEP = float(self.jog_step)
        self.Rapid_Move(0, -JOG_STEP)

    def Rapid_Move(self, dx, dy):
        if self.GUI_Disabled:
            self.reporter.status("Busy")
            return
        if self.units == "in":
            dx_inches = round(dx, 3)
            dy_inches = round(dy, 3)
        else:
            dx_inches = round(dx/25.4, 3)
            dy_inches = round(dy/25.4, 3)

        if (self.HomeUR):
            dx_inches = -dx_inches

        Xnew, Ynew = self.XY_in_bounds(dx_inches, dy_inches)
        dxmils = (Xnew - self.laser_pos.x)*1000.0
        dymils = (Ynew - self.laser_pos.y)*1000.0

        if self.k40 == None:
            self.laser_pos.x = Xnew
            self.laser_pos.y = Ynew
            self.reporter.data("laser_pos", self.laser_pos.aslist())
            self.menu_View_Refresh()
            self.reporter.error("Laser not initialized")
        elif self.Send_Rapid_Move(dxmils, dymils):
            self.laser_pos.x = Xnew
            self.laser_pos.y = Ynew
            self.reporter.data("laser_pos", self.laser_pos.aslist())
            self.menu_View_Refresh()

    def Send_Rapid_Move(self, dxmils, dymils):
        try:
            if self.k40 != None:
                Xscale = self.laser_scale.x
                Yscale = self.laser_scale.y
                if self.isRotary:
                    Rscale = self.laser_scale.r
                    Yscale = Yscale*Rscale

                if Xscale != 1.0 or Yscale != 1.0:
                    dxmils = int(round(dxmils * Xscale))
                    dymils = int(round(dymils * Yscale))
                self.k40.set_n_timeouts(10)

                if self.isRotary and float(self.rapid_feed):
                    self.slow_jog(int(dxmils), int(dymils))
                else:
                    self.k40.rapid_move(int(dxmils), int(dymils))

                return True
            else:
                return True
        # except StandardError as e:
        except Exception as e:
            msg1 = "Rapid Move Failed: "
            msg2 = "%s" % (e)
            if msg2 == "":
                formatted_lines = traceback.format_exc().splitlines()
            self.reporter.error((msg1+msg2).split("\n")[0])
            return False

    def slow_jog(self, dxmils, dymils):
        if int(dxmils) == 0 and int(dymils) == 0:
            return
        self.stop[0] = False
        Rapid_data = []
        Rapid_inst = egv(target=lambda s: Rapid_data.append(s))
        Rapid_feed = float(self.rapid_feed)*self.feed_factor()
        Rapid_inst.make_egv_rapid(
            dxmils, dymils, Feed=Rapid_feed, board_name=self.board_name)
        self.send_egv_data(Rapid_data, 1, None)
        self.stop[0] = True

    def set_gui(self, new_state="normal"):
        self.reporter.data("set_gui:", new_state)
        print("set_gui", new_state)
        pass
        # if new_state == "normal":
        #     self.GUI_Disabled = False
        # else:
        #     self.GUI_Disabled = True

        # try:
        #     self.menuBar.entryconfigure("File", state=new_state)
        #     self.menuBar.entryconfigure("View", state=new_state)
        #     self.menuBar.entryconfigure("Tools", state=new_state)
        #     self.menuBar.entryconfigure("Settings", state=new_state)
        #     self.menuBar.entryconfigure("Help", state=new_state)
        #     self.PreviewCanvas.configure(state=new_state)

        #     for w in self.master.winfo_children():
        #         try:
        #             w.configure(state=new_state)
        #         except:
        #             pass
        #     self.Stop_Button.configure(state="normal")
        #     #self.statusbar.configure(state="normal")
        #     #self.master.update()
        # except:
        #     if DEBUG:
        #         self.reporter.error(traceback.format_exc())

    def Vector_Cut(self, output_filename=None):
        self.Prepare_for_laser_run("Vector Cut: Processing Vector Data.")
        if self.VcutData.ecoords != []:
            self.send_data("Vector_Cut", output_filename)
        else:
            self.reporter.warning("No vector data to cut")
        self.Finish_Job()

    def Vector_Eng(self, output_filename=None):
        self.Prepare_for_laser_run("Vector Engrave: Processing Vector Data.")
        if self.VengData.ecoords != []:
            self.send_data("Vector_Eng", output_filename)
        else:
            self.reporter.warning("No vector data to engrave")
        self.Finish_Job()

    def Trace_Eng(self, output_filename=None):
        self.Prepare_for_laser_run("Boundary Trace: Processing Data.")
        
        self.trace_coords = self.make_trace_path()

        if self.trace_coords != []:
            self.send_data("Trace_Eng", output_filename)
        else:
            self.reporter.warning("No trace data to follow")
        self.Finish_Job()

    def Raster_Eng(self, output_filename=None):
        self.Prepare_for_laser_run("Raster Engraving: Processing Image Data.")
        try:
            self.make_raster_coords()
            if self.RengData.ecoords != []:
                self.send_data("Raster_Eng", output_filename)
            else:
                self.reporter.warning("No raster data to engrave")

        except MemoryError as e:
            msg1 = "Memory Error:"
            msg2 = "Memory Error:  Out of Memory."
            self.reporter.status(msg2)

        except Exception as e:
            msg1 = "Making Raster Data Stopped: "
            msg2 = "%s" % (e)
            self.reporter.error((msg1+msg2).split("\n")[0])
        self.Finish_Job()

    def Raster_Vector_Eng(self, output_filename=None):
        self.Prepare_for_laser_run(
            "Raster Engraving: Processing Image and Vector Data.")
        try:
            self.make_raster_coords()
            if self.RengData.ecoords != [] or self.VengData.ecoords != []:
                self.send_data("Raster_Eng+Vector_Eng", output_filename)
            else:
                self.reporter.warning("No data to engrave")
        except Exception as e:
            msg1 = "Preparing Data Stopped: "
            msg2 = "%s" % (e)
            self.reporter.error((msg1+msg2).split("\n")[0])
        self.Finish_Job()

    def Vector_Eng_Cut(self, output_filename=None):
        self.Prepare_for_laser_run("Vector Cut: Processing Vector Data.")
        if self.VcutData.ecoords != [] or self.VengData.ecoords != []:
            self.send_data("Vector_Eng+Vector_Cut", output_filename)
        else:
            self.reporter.warning("No vector data.")
        self.Finish_Job()

    def Raster_Vector_Cut(self, output_filename=None):
        self.Prepare_for_laser_run(
            "Raster Engraving: Processing Image and Vector Data.")
        try:
            self.make_raster_coords()
            if self.RengData.ecoords != [] or self.VengData.ecoords != [] or self.VcutData.ecoords != []:
                self.send_data(
                    "Raster_Eng+Vector_Eng+Vector_Cut", output_filename)
            else:
                self.reporter.warning("No data to engrave/cut")
        except Exception as e:
            msg1 = "Preparing Data Stopped: "
            msg2 = "%s" % (e)
            self.reporter.error((msg1+msg2).split("\n")[0])
        self.Finish_Job()

    def Gcode_Cut(self, output_filename=None):
        self.Prepare_for_laser_run("G Code Cutting.")
        if self.GcodeData.ecoords != []:
            self.send_data("Gcode_Cut", output_filename)
        else:
            self.reporter.warning("No g-code data to cut")
        self.Finish_Job()

    def Prepare_for_laser_run(self, msg):
        self.stop[0] = False
        self.move_head_window_temporary(Position(0, 0))
        self.set_gui("disabled")
        self.reporter.information(msg)
        #self.master.update()

    def Finish_Job(self, event=None):
        self.set_gui("normal")
        self.stop[0] = True
        if self.post_home:
            self.Unlock()

        stderr = ''
        stdout = ''
        if self.post_exec:
            cmd = [self.batch_path]
            from subprocess import PIPE, Popen
            proc = Popen(cmd, shell=True, stdin=None, stdout=PIPE, stderr=PIPE)
            stdout, stderr = proc.communicate()

        if self.post_disp or stderr != '':
            minutes = floor(self.run_time / 60)
            seconds = self.run_time - minutes*60
            msg = "Job Ended.\nRun Time = %02d:%02d" % (minutes, seconds)
            if stdout != '':
                msg = msg+'\n\nBatch File Output:\n'+stdout
            if stderr != '':
                msg = msg+'\n\nBatch File Errors:\n'+stderr
            self.run_time = 0
            self.reporter.status(msg)

    def make_trace_path(self):
        if self.inputCSYS and self.RengData.image == None:
            bounds = 0.0, 0.0, 0.0, 0.0
        else:
            bounds = self.Get_Design_Bounds()
        
        Vcut_coords = self.VcutData.ecoords
        Veng_coords = self.VengData.ecoords
        Gcode_coords = self.GcodeData.ecoords
        if self.mirror or self.rotate:
            Vcut_coords = self.mirror_rotate_vector_coords(Vcut_coords)
            Veng_coords = self.mirror_rotate_vector_coords(Veng_coords)
            Gcode_coords = self.mirror_rotate_vector_coords(Gcode_coords)
        
        if self.RengData.ecoords == []:
            self.make_raster_coords()
        return make_trace_path(bounds, self.laser_scale, self.RengData, Vcut_coords, Veng_coords, Gcode_coords, self.trace_gap, self.design_transform, self.isRotary)

    ################################################################################

    def mirror_rotate_vector_coords(self, coords):
        xmin = self.Design_bounds[0]
        xmax = self.Design_bounds[1]
        coords_rotate_mirror = []

        for i in range(len(coords)):
            coords_rotate_mirror.append(coords[i][:])
            if self.mirror:
                if self.inputCSYS and self.RengData.image == None:
                    coords_rotate_mirror[i][0] = -coords_rotate_mirror[i][0]
                else:
                    coords_rotate_mirror[i][0] = xmin + \
                        xmax-coords_rotate_mirror[i][0]

            if self.rotate:
                x = coords_rotate_mirror[i][0]
                y = coords_rotate_mirror[i][1]
                coords_rotate_mirror[i][0] = -y
                coords_rotate_mirror[i][1] = x

        return coords_rotate_mirror

    def feed_factor(self):
        if self.units == 'in':
            feed_factor = 25.4/60.0
        else:
            feed_factor = 1.0
        return feed_factor

    def send_data(self, operation_type=None, output_filename=None):
        num_passes = 0
        if self.k40 == None and output_filename == None:
            self.reporter.error("Laser Cutter is not Initialized...")
            return
        try:
            feed_factor = self.units.velocity_scale()
            if self.inputCSYS and self.RengData.image == None:
                xmin, xmax, ymin, ymax = 0.0, 0.0, 0.0, 0.0
            else:
                xmin, xmax, ymin, ymax = self.Get_Design_Bounds()

            startx = xmin
            starty = ymax

            if self.HomeUR:
                FlipXoffset = abs(xmax-xmin)
                if self.rotate:
                    startx = -xmin
            else:
                FlipXoffset = 0

            if self.isRotary:
                Rapid_Feed = float(self.rapid_feed)*feed_factor
            else:
                Rapid_Feed = 0.0

            Raster_Eng_data = []
            Vector_Eng_data = []
            Trace_Eng_data = []
            Vector_Cut_data = []
            G_code_Cut_data = []

            if (operation_type.find("Vector_Cut") > -1) and (self.VcutData.ecoords != []):
                Feed_Rate = float(self.Vcut_feed)*feed_factor
                self.reporter.status("Vector Cut: Determining Cut Order....")
                #self.master.update()
                if not self.VcutData.sorted and self.inside_first:
                    self.VcutData.set_ecoords(self.optimize_paths(
                        self.VcutData.ecoords), data_sorted=True)

                self.reporter.status("Generating EGV data...")
                #self.master.update()

                Vcut_coords = self.VcutData.ecoords
                if self.mirror or self.rotate:
                    Vcut_coords = self.mirror_rotate_vector_coords(Vcut_coords)

                Vcut_coords, startx, starty = scale_vector_coords(
                    Vcut_coords, startx, starty, self.laser_scale, self.isRotary)
                Vector_Cut_egv_inst = egv(
                    target=lambda s: Vector_Cut_data.append(s))
                Vector_Cut_egv_inst.make_egv_data(
                    Vcut_coords,
                    startX=startx,
                    startY=starty,
                    Feed=Feed_Rate,
                    board_name=self.board_name,
                    Raster_step=0,
                    reporter=self.reporter,
                    stop_calc=self.stop,
                    FlipXoffset=FlipXoffset,
                    Rapid_Feed_Rate=Rapid_Feed,
                    use_laser=True
                )

            if (operation_type.find("Vector_Eng") > -1) and (self.VengData.ecoords != []):
                Feed_Rate = float(self.Veng_feed)*feed_factor
                self.reporter.status(
                    "Vector Engrave: Determining Cut Order....")
                ##self.master.update()
                if not self.VengData.sorted and self.inside_first:
                    self.VengData.set_ecoords(self.optimize_paths(
                        self.VengData.ecoords, inside_check=False), data_sorted=True)
                self.reporter.status("Generating EGV data...")
                #self.master.update()

                Veng_coords = self.VengData.ecoords
                if self.mirror or self.rotate:
                    Veng_coords = self.mirror_rotate_vector_coords(Veng_coords)

                Veng_coords, startx, starty = self.scale_vector_coords(
                    Veng_coords, startx, starty, self.laser_scale, self.isRotary)
                Vector_Eng_egv_inst = egv(
                    target=lambda s: Vector_Eng_data.append(s))
                Vector_Eng_egv_inst.make_egv_data(
                    Veng_coords,
                    startX=startx,
                    startY=starty,
                    Feed=Feed_Rate,
                    board_name=self.board_name,
                    Raster_step=0,
                    reporter=self.reporter,
                    stop_calc=self.stop,
                    FlipXoffset=FlipXoffset,
                    Rapid_Feed_Rate=Rapid_Feed,
                    use_laser=True
                )

            if (operation_type.find("Trace_Eng") > -1) and (self.trace_coords != []):
                Feed_Rate = float(self.trace_speed)*feed_factor
                laser_on = self.trace_w_laser
                self.reporter.status("Generating EGV data...")
                #self.master.update()
                Trace_Eng_egv_inst = egv(
                    target=lambda s: Trace_Eng_data.append(s))
                Trace_Eng_egv_inst.make_egv_data(
                    self.trace_coords,
                    startX=startx,
                    startY=starty,
                    Feed=Feed_Rate,
                    board_name=self.board_name,
                    Raster_step=0,
                    reporter=self.reporter,
                    stop_calc=self.stop,
                    FlipXoffset=FlipXoffset,
                    Rapid_Feed_Rate=Rapid_Feed,
                    use_laser=laser_on
                )

            if (operation_type.find("Raster_Eng") > -1) and (self.RengData.ecoords != []):
                Feed_Rate = self.Reng_feed*feed_factor
                Raster_step = get_raster_step_1000in(self.rast_step)
                if not self.engraveUP:
                    Raster_step = -Raster_step

                raster_startx = 0

                Yscale = self.laser_pos.yscale
                if self.isRotary:
                    Yscale = Yscale*self.laser_scale.r
                raster_starty = Yscale*starty

                self.reporter.status("Generating EGV data...")
                #self.master.update()
                Raster_Eng_egv_inst = egv(
                    target=lambda s: Raster_Eng_data.append(s))
                Raster_Eng_egv_inst.make_egv_data(
                    self.RengData.ecoords,
                    startX=raster_startx,
                    startY=raster_starty,
                    Feed=Feed_Rate,
                    board_name=self.board_name,
                    Raster_step=Raster_step,
                    reporter=self.reporter,
                    stop_calc=self.stop,
                    FlipXoffset=FlipXoffset,
                    Rapid_Feed_Rate=Rapid_Feed,
                    use_laser=True
                )
                # self.RengData.reset_path()

            if (operation_type.find("Gcode_Cut") > -1) and (self.GcodeData.ecoords != []):
                self.reporter.status("Generating EGV data...")
                #self.master.update()
                Gcode_coords = self.GcodeData.ecoords
                if self.mirror or self.rotate:
                    Gcode_coords = self.mirror_rotate_vector_coords(
                        Gcode_coords)

                Gcode_coords, startx, starty = scale_vector_coords(
                    Gcode_coords, startx, starty, self.laser_scale, self.isRotary)
                G_code_Cut_egv_inst = egv(
                    target=lambda s: G_code_Cut_data.append(s))
                G_code_Cut_egv_inst.make_egv_data(
                    Gcode_coords,
                    startX=startx,
                    startY=starty,
                    Feed=None,
                    board_name=self.board_name,
                    Raster_step=0,
                    reporter=self.reporter,
                    stop_calc=self.stop,
                    FlipXoffset=FlipXoffset,
                    Rapid_Feed_Rate=Rapid_Feed,
                    use_laser=True
                )

            ### Join Resulting Data together ###
            data = []
            data.append(ord("I"))
            if Trace_Eng_data != []:
                trace_passes = 1
                for k in range(trace_passes):
                    if len(data) > 4:
                        data[-4] = ord("@")
                    data.extend(Trace_Eng_data)
            if Raster_Eng_data != []:
                num_passes = int(float(self.Reng_passes))
                for k in range(num_passes):
                    if len(data) > 4:
                        data[-4] = ord("@")
                    data.extend(Raster_Eng_data)
            if Vector_Eng_data != []:
                num_passes = int(float(self.Veng_passes))
                for k in range(num_passes):
                    if len(data) > 4:
                        data[-4] = ord("@")
                    data.extend(Vector_Eng_data)
            if Vector_Cut_data != []:
                num_passes = int(float(self.Vcut_passes))
                for k in range(num_passes):
                    if len(data) > 4:
                        data[-4] = ord("@")
                    data.extend(Vector_Cut_data)
            if G_code_Cut_data != []:
                num_passes = int(float(self.Gcde_passes))
                for k in range(num_passes):
                    if len(data) > 4:
                        data[-4] = ord("@")
                    data.extend(G_code_Cut_data)
            if len(data) < 4:
                raise Exception("No laser data was generated.")

            #self.master.update()
            if output_filename != None:
                self.write_egv_to_file(data, output_filename)
            else:
                self.send_egv_data(data, 1, output_filename)
                self.menu_View_Refresh()

        except MemoryError as e:
            msg1 = "Memory Error:"
            msg2 = "Memory Error:  Out of Memory."
            self.reporter.error(msg2)

        except Exception as e:
            print(e)
            msg1 = "Sending Data Stopped: "
            msg2 = "%s" % (e)
            if msg2 == "":
                formatted_lines = traceback.format_exc().splitlines()
            self.reporter.error((msg1+msg2).split("\n")[0])

    def send_egv_data(self, data, num_passes=1, output_filename=None):
        pre_process_CRC = self.pre_pr_crc
        if self.k40 != None:
            self.k40.set_timeout(int(float(self.t_timeout)))
            self.k40.set_n_timeouts(int(float(self.n_timeouts)))
            time_start = time()
            self.k40.send_data(data, self.reporter, self.stop,
                               num_passes, pre_process_CRC, True)
            self.run_time = time()-time_start
            if DEBUG:
                print(("Elapsed Time: %.6f" % (time()-time_start)))

        else:
            self.reporter.warning("Laser is not initialized.")
            
            return
        self.menu_View_Refresh()

    ##########################################################################
    ##########################################################################
    def write_egv_to_file(self, data, fname):
        if len(data) == 0:
            raise Exception("No data available to write to file.")
        try:
            fout = open(fname, 'w')
        except:
            raise Exception(
                "Unable to open file ( %s ) for writing." % (fname))
        fout.write("Document type : LHYMICRO-GL file\n")
        fout.write("Creator-Software: K40 Whisperer\n")

        fout.write("\n")
        fout.write("%0%0%0%0%")
        for char_val in data:
            char = chr(char_val)
            fout.write("%s" % (char))

        # fout.write("\n")
        fout.close
        self.menu_View_Refresh()
        self.reporter.status("Data saved to: %s" % (fname))

    def Home(self, event=None):
        if self.GUI_Disabled:
            self.reporter.error("Busy")
            return
        if self.k40 != None:
            self.k40.home_position()
        else:
            self.reporter.error("Laser not initialized")
        self.laser_pos.x = 0.0
        self.laser_pos.y = 0.0
        self.reporter.data("laser_pos", self.laser_pos.aslist())
        self.pos_offset = Position(0.0, 0.0)
        self.menu_View_Refresh()

    def GoTo(self):
        xpos = float(self.gotoX)
        ypos = float(self.gotoY)
        if self.k40 != None:
            self.k40.home_position()
        self.laser_pos.x = 0.0
        self.laser_pos.y = 0.0
        self.Rapid_Move(xpos, ypos)
        self.reporter.data("laser_pos", self.laser_pos.aslist())
        self.menu_View_Refresh()

    def Reset(self):
        if self.k40 != None:
            try:
                self.k40.reset_usb()
                self.reporter.status("USB Reset Succeeded")
            except:
                self.reporter.error(traceback.format_exc())
                pass

    def Stop(self, event=None):
        if self.stop[0] == True:
            return
        line1 = "Do you want to abort all jobs?"
        line2 = "Sending data to the laser from K40 Whisperer is currently Paused."
        line3 = "Press \"Cancel\" to resume."
        if self.k40 != None:
            self.k40.pause_un_pause()

        if message_ask_ok_cancel("Stop Laser Job.", "%s\n\n%s\n%s" % (line1, line2, line3)):
            self.stop[0] = True
        else:
            if self.k40 != None:
                self.k40.pause_un_pause()

    def Release_USB(self):
        if self.k40 != None:
            try:
                self.k40.release_usb()
                self.reporter.status("USB Release Succeeded")
            except:
                self.reporter.error(traceback.format_exc())
                pass
            self.k40 = None

    def Initialize_Laser(self, event=None):
        if self.GUI_Disabled:
            self.reporter.error("Busy")
            return
        self.reporter.status("Initializing Laser")
        self.stop[0] = True
        self.Release_USB()
        self.k40 = None
        self.move_head_window_temporary(Position(0.0, 0.0))
        self.k40 = K40_CLASS()

        try:
            self.k40.initialize_device(None, False)
            self.k40.say_hello()
            if self.init_home:
                self.Home()
            else:
                self.Unlock()
            self.reporter.status("Laser initialized")

        except Exception as e:
            error_text = "%s" % (e)
            if "BACKEND" in error_text.upper():
                error_text = error_text + " (libUSB driver not installed)"
            self.reporter.error(f"USB Error: {error_text}")
            self.k40 = None
            self.reporter.error(traceback.format_exc())

        except:
            self.reporter.error("Unknown USB Error")
            self.k40 = None
            self.reporter.error(traceback.format_exc())

    def Unlock(self, event=None):
        if self.GUI_Disabled:
            self.reporter.error("Busy")
            return
        if self.k40 != None:
            try:
                self.k40.unlock_rail()
                self.reporter.status("Rail Unlock Succeeded")
            except:
                self.reporter.error("Rail Unlock Failed.")
                pass

    ##########################################################################
    ##########################################################################

    def Reset_RasterPath_and_Update_Time(self, varName=0, index=0, mode=0):
        self.RengData.reset_path()
        self.refreshTime()

    def View_Refresh_and_Reset_RasterPath(self, varName=0, index=0, mode=0):
        self.RengData.reset_path()
        self.SCALE = 0
        self.menu_View_Refresh()

    def menu_View_inputCSYS_Refresh_Callback(self, varName, index, mode):
        self.move_head_window_temporary(Position(0.0, 0.0))
        self.SCALE = 0
        self.menu_View_Refresh()

    def menu_View_Refresh_Callback(self, varName=0, index=0, mode=0):
        self.SCALE = 0
        self.menu_View_Refresh()

    def menu_View_Refresh(self):
        print("menu_View_Refresh")
        pass

        # try:
        #     app.master.title(title_text+"   " + self.DESIGN_FILE)
        # except:
        #     pass
        # dummy_event = Event()
        # dummy_event.widget = self.master
        # self.Master_Configure(dummy_event, 1)
        # self.Plot_Data()
        # xmin, xmax, ymin, ymax = self.Get_Design_Bounds()
        # W = xmax-xmin
        # H = ymax-ymin

        # if self.units == "in":
        #     X_display = self.laser_pos.x + self.pos_offset.x/1000.0
        #     Y_display = self.laser_pos.y + self.pos_offset.y/1000.0
        #     W_display = W
        #     H_display = H
        #     U_display = self.units
        # else:
        #     X_display = (
        #         self.laser_pos.x + self.pos_offset.x/1000.0)*self.units_scale
        #     Y_display = (
        #         self.laser_pos.y + self.pos_offset.y/1000.0)*self.units_scale
        #     W_display = W*self.units_scale
        #     H_display = H*self.units_scale
        #     U_display = self.units
        # if self.HomeUR:
        #     X_display = -X_display

        # self.reporter.status(" Current Position: X=%.3f Y=%.3f    ( W X H )=( %.3f%s X %.3f%s ) "
        #                        % (X_display,
        #                            Y_display,
        #                            W_display,
        #                            U_display,
        #                            H_display,
        #                            U_display))

        # self.statusbar.configure(bg='white')

    def Entry_Design_Scale_Callback(self, varname, index, mode):
        self.menu_Reload_Design()

    def menu_Inside_First_Callback(self, varName, index, mode):
        if self.GcodeData.ecoords != []:
            if self.VcutData.sorted == True:
                self.menu_Reload_Design()
            elif self.VengData.sorted == True:
                self.menu_Reload_Design()

    def menu_Mode_Change(self):
        dummy_event = Event()
        dummy_event.widget = self.master
        self.Master_Configure(dummy_event, 1)

    def menu_Calc_Raster_Time(self, event=None):
        self.set_gui("disabled")
        self.stop[0] = False
        self.make_raster_coords()
        self.stop[0] = True
        self.refreshTime()
        self.set_gui("normal")
        self.menu_View_Refresh()

    def bindConfigure(self, event):
        if not self.initComplete:
            self.initComplete = 1
            self.menu_Mode_Change()

    def Recalculate_RQD_Click(self, event):
        self.menu_View_Refresh()


    ##########################################
    #        CANVAS PLOTTING STUFF           #
    ##########################################
    

    def Plot_Data(self):
       
        # # setup bounds and dimensions
        # cszw = int(self.PreviewCanvas.cget("width"))
        # cszh = int(self.PreviewCanvas.cget("height"))
        # buff = 10
        # wc = float(cszw/2)
        # hc = float(cszh/2)

        # maxx = float(self.laser_bed_size.x) / self.units_scale
        # minx = 0.0
        # maxy = 0.0
        # miny = -float(self.laser_bed_size.y) / self.units_scale
        # midx = (maxx+minx)/2
        # midy = (maxy+miny)/2

        if self.inputCSYS and self.RengData.image == None:
            xmin, xmax, ymin, ymax = 0.0, 0.0, 0.0, 0.0
        else:
            xmin, xmax, ymin, ymax = self.Get_Design_Bounds()

        ######################################
        ###       Plot Raster Image        ###
        ######################################
        if self.RengData.image != None:
            if self.include_Reng:
                try:
                    self.Reng_image = self.RengData.image.convert("L")
                    input_dpi = 1000*self.design_scale
                    wim, him = self.RengData.image.size
                    new_SCALE = self.SCALE #(1.0/self.PlotScale)/input_dpi #FIXME
                    if new_SCALE != self.SCALE:
                        self.SCALE = new_SCALE
                        nw = int(self.SCALE*wim)
                        nh = int(self.SCALE*him)

                        plot_im = self.RengData.image.convert("L")

                        if self.negate:
                            plot_im = ImageOps.invert(plot_im)

                        if self.halftone == False:
                            plot_im = plot_im.point(
                                lambda x: 0 if x < 128 else 255, '1')
                            plot_im = plot_im.convert("L")

                        if self.mirror:
                            plot_im = ImageOps.mirror(plot_im)

                        if self.rotate:
                            plot_im = plot_im.rotate(90, expand=True)
                            nh = int(self.SCALE*wim)
                            nw = int(self.SCALE*him)

                        self.Reng_image = plot_im.resize((nw, nh), PIL.Image.ANTIALIAS)
                    #self.reporter.data("Reng_image", self.Reng_image.tobytes()) #FIXME
                except:
                    self.SCALE = 1
                    self.reporter.warning(traceback.format_exc())
                
        else:
            self.Reng_image = None
            self.reporter.data("Reng_image", "")

        ######################################
        ###       Plot Reng Coords         ###
        ######################################
        if self.include_Rpth and self.RengData.ecoords != []:

            Xscale = 1/self.laser_scale.x
            Yscale = 1/self.laser_scale.y
            if self.isRotary:
                Rscale = 1/self.laser_scale.r
                Yscale = Yscale*Rscale

            lines = ecoords2lines(self.RengData.ecoords,
                                    Scale(Xscale, Yscale),
                                    Position(0, -ymax))
            
            self.Reng_coords = lines
            self.reporter.data("Reng_coords", lines)

        ######################################
        ###       Plot Veng Coords         ###
        ######################################
        if self.include_Veng:

            plot_coords = self.VengData.ecoords
            if self.mirror or self.rotate:
                plot_coords = self.mirror_rotate_vector_coords(plot_coords)

            lines = ecoords2lines(self.VengData.ecoords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))

            self.Veng_coords = lines
            self.reporter.data("Veng_coords", lines)

        ######################################
        ###       Plot Vcut Coords         ###
        ######################################
        if self.include_Vcut:

            plot_coords = self.VcutData.ecoords
            if self.mirror or self.rotate:
                plot_coords = self.mirror_rotate_vector_coords(plot_coords)

            lines = ecoords2lines(self.VcutData.ecoords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))

            self.Vcut_coords = lines
            self.reporter.data("Vcut_coords", lines)

        ######################################
        ###       Plot Gcode Coords        ###
        ######################################
        if self.include_Gcde:

            plot_coords = self.GcodeData.ecoords
            if self.mirror or self.rotate:
                plot_coords = self.mirror_rotate_vector_coords(plot_coords)

            lines = ecoords2lines(self.RengData.ecoords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))
            
            self.Gcde_coords = lines
            self.reporter.data("Gcde_coords", lines)

        ######################################
        ###       Plot Trace Coords        ###
        ######################################
        if self.include_Trace:
            #####
            Xscale = 1/self.laser_scale.x
            Yscale = 1/self.laser_scale.y
            if self.isRotary:
                Rscale = 1/self.laser_scale.r
                Yscale = Yscale*Rscale
            ######
            trace_coords = self.make_trace_path()

            lines = ecoords2lines(trace_coords,
                                    Scale(Xscale, Yscale),
                                    Position(-xmin, -ymax))
            
            self.trace_coords = lines
            self.reporter.data("Trace_coords", lines)

        ######################################
        self.refreshTime()


################################################################################
#                          Startup Application                                 #
################################################################################

if __name__ == "__main__":
    app = Laser_Service.instance()
    app.Initialize_Laser()
