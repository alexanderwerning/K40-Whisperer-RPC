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
from k40_web.laser_controller.utils import format_time, get_raster_step_1000in, generate_bezier, ecoords2lines, make_raster_coords, scale_vector_coords, make_trace_path, optimize_paths, mirror_rotate_vector_coords
from k40_web.laser_controller.nano_library import K40_CLASS
from k40_web.laser_controller.egv import egv
from k40_web.laser_controller.ecoords import ECoord
import json
from pathlib import Path
from math import *
import traceback
import sys
from numbers import Number

from pathlib import Path
from k40_web.laser_controller.filereader import Open_SVG, Open_DXF, Open_G_Code
from k40_web.laser_controller.util_classes import Position, Dimensions, DesignBounds, Scale, DesignTransform, DisplayUnits, BezierSettings, SVG_Settings, Design

version = '0.52'
title_text = "K40 Whisperer V"+version

MAXINT = sys.maxsize

try:
    os.chdir(os.path.dirname(__file__))
except:
    pass

config_path = "./config_init.json"

################################################################################


class Laser_Service():
    _instance = None
    def __init__(self):
        raise RuntimeError('call instance()')
    
    @classmethod
    def instance(cls, reporter):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            self = cls._instance
            self.init_vars()
            self.reporter = reporter
            self.reporter.status("Welcome to K40 Whisperer")
        return cls._instance

    def resetPath(self):
        self.design.reset()
        self.SCALE = 1
        self.design.bounds = DesignBounds(0, 0, 0, 0)
        # if self.HomeUR:
        self.move_head_window_temporary(Position(0.0, 0.0))
        # else:
        #    self.move_head_window_temporary(0.0,0.0)

        self.pos_offset = Position(0.0, 0.0)
    
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


        self.bezier_settings = BezierSettings(self.bezier_weight, self.bezier_M1, self.bezier_M2)
        self.svg_settings = SVG_Settings(inkscape_path="", ink_timeout=self.ink_timeout, default_pxpi=96.0, default_viewbox=(0,0,500,500))

        self.PlotScale = 1.0
        self.GUI_Disabled = False


        self.SCALE = 1
        self.design_transform = DesignTransform(self.design_scale,
                                            self.rotate,
                                            self.mirror,
                                            self.negate,
                                            self.halftone,
                                            self.ht_size)
        self.design = Design()
        self.pos_offset = Position(0,0)

        self.inkscape_warning = False

        self.units = DisplayUnits(self.unit_name)

        self.min_vector_speed = 1.1  # in/min
        self.min_raster_speed = 12  # in/min


################################################################################
    def set_var_with_check(self, name, value):
        print(f"set var with check {name}, {value}, {type(value)}")
        callbacks = {"Reng_feed": self.Entry_Reng_feed_Callback,
                    "Veng_feed": self.Entry_Veng_feed_Callback,
                    "Vcut_feed": self.Entry_Vcut_feed_Callback,
                    "step": self.Entry_Step_Callback,
                    "Rstep": self.Entry_Rstep_Callback,
                    "bezier_settings": self.Entry_bezier_settings_callback,
                    "ink_timeout":  self.Entry_Ink_Timeout_Callback,
                    "timeout": self.Entry_Timeout_Callback,
                    "n_timeouts": self.Entry_N_Timeouts_Callback,
                    "n_EGV_passes": self.Entry_N_EGV_Passes_Callback,
                    "laser_pos": lambda x: self.mouse_click(x[0], x[1]),
                    "laser_size": self.Entry_Laser_Area_Callback,
                    "laser_scale": self.Entry_Laser_Scale_Callback,
                    "rapid_feed": self.Entry_Laser_Rapid_Feed_Callback,
                    "Reng_passes": self.Entry_Reng_passes_Callback,
                    "Veng_passes": self.Entry_Veng_passes_Callback,
                    "Vcut_passes": self.Entry_Vcut_passes_Callback,
                    "Gcde_passes": self.Entry_Gcde_passes_Callback,
                    "Trace_gap": self.Entry_Trace_Gap_Callback,
                    "trace_speed": self.Entry_Trace_Speed_Callback,
                    "inkscape_path": self.Entry_Inkscape_Path_Callback}
        binary_vars = ["include_Reng", "include_Veng", "include_Vcut", "include_Gcde",
                "include_Time", "include_Trace",
                "halftone", "invert", "HomeUR", "inputCSYS",
                "mirror", "rotate", "engraveUP", "init_home", "post_home", "post_beep",
                "post_disp", "post_exec", "pre_pr_crc", "inside_first", "comb_engrave",
                "comb_vector", "zoom2image", "rotary", "trace_w_laser"]
        if name in callbacks:
            callbacks[name](value)
        elif name in binary_vars:
            setattr(self, name, value==True)
            self.reporter.data(name, value==True)
        else:
            self.reporter.error(f"Callback {name} not accessible")

    def entry_set(self, field, calc_flag=0):
        if calc_flag == 3:
            self.reporter.fieldError(field)
            self.reporter.error("Value should be a number. ")
        elif calc_flag == 2:
            self.reporter.fieldError(field)
        elif (calc_flag == 0 or calc_flag == 1):
            self.reporter.fieldClear(field)

    def Quit_Click(self):
        self.reporter.status("Exiting!")
        self.Release_USB()

    # callback laser_pos
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

        if (self.inputCSYS and self.design.RengData.image == None) or no_size:
            xmin, xmax, ymin, ymax = 0.0, 0.0, 0.0, 0.0
        else:
            xmin, xmax, ymin, ymax = self.Get_Design_Bounds().bounds

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

        if self.design.RengData.rpaths:
            Reng_time = 0
        else:
            Reng_time = None
        Veng_time = 0
        Vcut_time = 0

        if self.design.RengData.len != None:
            # these equations are a terrible hack based on measured raster engraving times
            # to be fixed someday
            if Raster_eng_feed*60.0 <= 300:
                accel_time = 8.3264*(Raster_eng_feed*60.0)**(-0.7451)
            else:
                accel_time = 2.5913*(Raster_eng_feed*60.0)**(-0.4795)

            t_accel = self.design.RengData.n_scanlines * accel_time
            Reng_time = ((self.design.RengData.len)/Raster_eng_feed) * \
                Raster_eng_passes + t_accel
        if self.design.VengData.len != None:
            Veng_time = (self.design.VengData.len / Vector_eng_feed +
                         self.design.VengData.move / rapid_feed) * Vector_eng_passes
        if self.design.VcutData.len != None:
            Vcut_time = (self.design.VcutData.len / Vector_cut_feed +
                         self.design.VcutData.move / rapid_feed) * Vector_cut_passes

        Gcode_time = self.design.GcodeData.gcode_time * Gcode_passes

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

        if self.design.GcodeData.ecoords == []:
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

    def check_velocity(self, new_value, low_speed_limit, name, equal=True):
        if not isinstance(new_value, Number):
            return 3     # Value not a number
        vfactor = (25.4/60.0)*self.units.velocity_scale()
        low_limit = low_speed_limit*vfactor
        if new_value < low_limit or (not equal and new_value == low_limit):
            self.reporter.error(f"{name} should be greater than {'or equal to' if equal else ''} {low_limit}")
            return 2  # Value is invalid number
        return 0         # Value is a valid number

    def check_larger_than(self, value, name, limit=0, equal=True):
        if not isinstance(value, Number):
            return 3 # Value not a number
        if value < limit or (not equal and value == limit):
            self.reporter.error(f"{name} should be greater than {'or equal to' if equal else ''} {limit}")
            return 2  # Value is invalid number
        return 0         # Value is a valid number
    
    def check_between(self, value, name, lower_limit, upper_limit, include_lower=True, include_upper=True):
        if not isinstance(value, Number):
            return 3 # Value not a number
        if (value < lower_limit or (not include_lower and value == lower_limit)
            or value > upper_limit or (not include_upper and value == upper_limit)):
            self.reporter.error(f"{name} should be between {lower_limit} and {upper_limit}")
            return 2  # Value is invalid number
        return 0         # Value is a valid number

    def Entry_Reng_feed_Callback(self, value):
        check_result = self.check_velocity(value, self.min_raster_speed, "Feed Rate")
        if check_result == 0:
            self.Reng_feed = value
            self.reporter.data("Reng_feed", self.Reng_feed)
        self.entry_set("Reng_feed", check_result)

    def Entry_Veng_feed_Callback(self, value):
        check_result = self.check_velocity(value, self.min_vector_speed, "Feed Rate")
        if check_result == 0:
            self.Veng_feed = value
            self.reporter.data("Veng_feed", self.Veng_feed)
        self.entry_set("Veng_feed", check_result)

    def Entry_Vcut_feed_Callback(self, value):
        check_result = self.check_velocity(value, self.min_vector_speed, "Feed Rate")
        if check_result == 0:
            self.Vcut_feed = value
            self.reporter.data("Vcut_feed", self.Vcut_feed)
        self.entry_set("Vcut_feed", check_result)

    def Entry_Step_Callback(self, value):
        check_result = self.check_larger_than(value, "Step", equal=False)
        if check_result == 0:
            self.jog_step = value
            self.reporter.data("jog_step", self.jog_step)
        self.entry_set("Step", check_result)

    def Entry_Rstep_Callback(self, value):
        check_result = self.check_between(value, "Step", 0, 0.063, include_lower=False)
        if check_result == 0:
            self.rast_step = value
            self.reporter.data("Step", self.rast_step)
        self.design.RengData.reset_path()
        self.entry_set("Rstep", check_result)

    def Entry_bezier_settings_callback(self, value):
        weight, m1, m2 = value
        self.bezier_settings.weight = weight
        self.bezier_settings.m1 = m1
        self.bezier_settings.m2 = m2
        self.Reset_RasterPath_and_Update_Time()
        self.bezier_plot()

    def bezier_plot(self):
        num = 10
        x, y = generate_bezier(self.bezier_settings, n=num)
        self.reporter.data("bezier_plot", dict(x=x, y=y))

    def Entry_Ink_Timeout_Callback(self, value):
        check_result = self.check_larger_than(value, "Timeout")
        if check_result == 0:
            self.svg_settings.ink_timeout = value
            self.reporter.data("ink_timeout", self.svg_settings.ink_timeout)
        self.entry_set("Ink_Timeout", check_result)

    def Entry_Timeout_Callback(self, value):
        check_result = self.check_larger_than(value, "Timeout", equal=False)
        if check_result == 0:
            self.t_timeout = value
        self.entry_set("Timeout", check_result)

    def Entry_N_Timeouts_Callback(self, value):
        check_result = self.check_larger_than(value, "N_Timeouts", equal=False)
        if check_result == 0:
            self.n_timeouts = int(value)
        self.entry_set("N_Timeouts", check_result)

    def Entry_N_EGV_Passes_Callback(self, value):
        check_result = self.check_larger_than(value, "EGV passes", limit=1)
        if check_result == 0:
            self.n_egv_passes = int(value)
        self.entry_set("N_EGV_Passes", check_result)

    def Entry_Laser_Area_Callback(self, value):
        w, h = value
        check_result = self.check_larger_than(w, "Width", equal=False)
        if check_result == 0:
            self.laser_bed_size.x = w
        self.entry_set("Laser_Area_Width", check_result)
        check_result = self.check_larger_than(h, "Height", equal=False)
        if check_result == 0:
            self.laser_bed_size.y = h
        self.reporter.data("laser_bed_size", self.laser_bed_size.aslist())
        self.entry_set("Laser_Area_Height", check_result)
        self.Reset_RasterPath_and_Update_Time()

    def Entry_Laser_Scale_Callback(self, value):
        if len(value) == 2:
            x, y = value
            r = 1
        elif len(value) == 3:
            x, y, r = value
        check_result = self.check_larger_than(x, "X scale factor", equal=False)
        if check_result == 0:
            self.laser_scale.x = x
        self.entry_set("Laser_X_Scale", check_result)
        check_result = self.check_larger_than(y, "Y scale factor", equal=False)
        if check_result == 0:
            self.laser_scale.y = y
        self.entry_set("Laser_Y_Scale", check_result)
        check_result = self.check_larger_than(r, "Rotary scale factor", equal=False)
        if check_result == 0:
            self.laser_scale.r = r
        self.reporter.data("laser_scale", self.laser_scale.aslist())
        self.entry_set("Laser_R_Scale", check_result)
        self.Reset_RasterPath_and_Update_Time()

    def Entry_Laser_Rapid_Feed_Callback(self, value):
        check_result = self.check_velocity(value, 1, "Rapid feed")
        if check_result == 0:
            self.rapid_feed = value
            self.reporter.data("rapid_feed", self.rapid_feed)
        self.entry_set("Laser_Rapid_Feed", check_result)

    def Entry_Reng_passes_Callback(self, value):
        check_result = self.check_larger_than(value, "Number of passes", limit=1)
        if check_result == 0:
            self.Reng_passes = int(value)
            self.reporter.data("Reng_passes", self.Reng_passes)
        self.entry_set("Reng_passes", check_result)

    def Entry_Veng_passes_Callback(self, value):
        check_result = self.check_larger_than(value, "Number of passes", limit=1)
        if check_result == 0:
            self.Veng_passes = int(value)
            self.reporter.data("Veng_passes", self.Veng_passes)
        self.entry_set("Veng_passes", check_result)

    def Entry_Vcut_passes_Callback(self, value):
        check_result = self.check_larger_than(value, "Number of passes", limit=1)
        if check_result == 0:
            self.Vcut_passes = int(value)
            self.reporter.data("Vcut_passes", self.Vcut_passes)
        self.entry_set("Vcut_passes", check_result)

    def Entry_Gcde_passes_Callback(self, value):
        check_result = self.check_larger_than(value, "Number of passes", limit=1)
        if check_result == 0:
            self.Gcde_passes = int(value)
            self.reporter.data("Gcde_passes", self.Gcde_passes)
        self.entry_set("Gcde_passes", check_result)

    def Entry_Trace_Gap_Callback(self, value):
        check_result = 0 if isinstance(value, Number) else 3
        if check_result == 0:
            self.trace_gap = int(value)
            self.reporter.data("trace_gap", self.trace_gap)
        self.entry_set("Trace_Gap", check_result)

    def Entry_Trace_Speed_Callback(self, value):
        check_result = self.check_velocity(value, self.min_vector_speed, "Feed Rate")
        if check_result == 0:
            self.trace_speed = value
            self.reporter.data("trace_speed", self.trace_speed)
        self.entry_set("Trace_Speed", check_result)

    def Entry_Inkscape_Path_Callback(self, inkscape_path):
        if self.inkscape_warning == False:
            self.inkscape_warning = True
            msg1 = "Beware:"
            msg2 = "Most people should leave the 'Inkscape Executable' entry field blank. "
            msg3 = "K40 Whisperer will find Inkscape in one of the the standard locations after you install Inkscape."
            self.reporter.information(msg1+" "+msg2+msg3)
        path = Path(inkscape_path)
        if not path.exists():
            self.reporter.error("The path {path} does not exist")
        else:
            self.inkscape_path = path

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
            result = Open_DXF(filepath, self.design_transform.scale, self.reporter)
            if result is not None:
                self.design = result
            else:
                self.design.reset()
        elif TYPE == '.SVG':
            self.resetPath()
            result = Open_SVG(filepath,
                            self.design_transform.scale,
                            self.svg_settings,
                            self.reporter)
            if result is not None:
                self.design = result
            else:
                self.design.reset()
        elif TYPE == '.EGV':
            self.EGV_Send_Window(filepath)
        else:
            self.resetPath()
            result = Open_G_Code(filepath,
                                self.reporter)
            if result is not None:
                self.design = result
            else:
                self.design.reset()

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
        make_raster_coords(self.design.RengData, self.laser_scale, self.design_transform, self.isRotary, self.bezier_settings, self.reporter, self.rast_step)

    ##########################################################################

    def Get_Design_Bounds(self):
        if self.rotate:
            return self.design.bounds.rotate()
        else:
            return self.design.bounds

    def move_head_window_temporary(self, offset):
        if self.GUI_Disabled:
            return
        dx_inches = round(offset.x, 3)
        dy_inches = round(offset.y, 3)
        Xnew, Ynew = self.XY_in_bounds(dx_inches, dy_inches, no_size=True)

        pos_offset_X = round((Xnew-self.laser_pos.x), 3)
        pos_offset_Y = round((Ynew-self.laser_pos.y), 3)
        new_pos_offset = Position(pos_offset_X, pos_offset_Y)

        if self.inputCSYS and self.design.RengData.image == None:
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
        xmin, xmax, ymin, ymax = self.Get_Design_Bounds().bounds

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
        self.Move_Arb_Step(self.jog_step, 0)

    def Move_Arb_Left(self, dummy=None):
        self.Move_Arb_Step(-self.jog_step, 0)

    def Move_Arb_Up(self, dummy=None):
        self.Move_Arb_Step(0, self.jog_step)

    def Move_Arb_Down(self, dummy=None):
        self.Move_Arb_Step(0, -self.jog_step)

    ####################################################

    def Move_Right(self, dummy=None):
        self.Rapid_Move(self.jog_step, 0)

    def Move_Left(self, dummy=None):
        self.Rapid_Move(-self.jog_step, 0)

    def Move_Up(self, dummy=None):
        self.Rapid_Move(0, self.jog_step)

    def Move_Down(self, dummy=None):
        self.Rapid_Move(0, -self.jog_step)

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
        Rapid_feed = float(self.rapid_feed)/self.units.velocity_scale()
        Rapid_inst.make_egv_rapid(
            dxmils, dymils, Feed=Rapid_feed, board_name=self.board_name)
        self.send_egv_data(Rapid_data, 1, None)
        self.stop[0] = True

    def Vector_Cut(self, output_filename=None):
        self.Prepare_for_laser_run("Vector Cut: Processing Vector Data.")
        if self.design.VcutData.ecoords != []:
            self.send_data("Vector_Cut", output_filename)
        else:
            self.reporter.warning("No vector data to cut")
        self.Finish_Job()

    def Vector_Eng(self, output_filename=None):
        self.Prepare_for_laser_run("Vector Engrave: Processing Vector Data.")
        if self.design.VengData.ecoords != []:
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
            if self.design.RengData.ecoords != []:
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
            if self.design.RengData.ecoords != [] or self.design.VengData.ecoords != []:
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
        if self.design.VcutData.ecoords != [] or self.design.VengData.ecoords != []:
            self.send_data("Vector_Eng+Vector_Cut", output_filename)
        else:
            self.reporter.warning("No vector data.")
        self.Finish_Job()

    def Raster_Vector_Cut(self, output_filename=None):
        self.Prepare_for_laser_run(
            "Raster Engraving: Processing Image and Vector Data.")
        try:
            self.make_raster_coords()
            if self.design.RengData.ecoords != [] or self.design.VengData.ecoords != [] or self.design.VcutData.ecoords != []:
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
        if self.design.GcodeData.ecoords != []:
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
        if self.inputCSYS and self.design.RengData.image == None:
            bounds = 0.0, 0.0, 0.0, 0.0
        else:
            bounds = self.Get_Design_Bounds()
        
        Vcut_coords = mirror_rotate_vector_coords(self.design.VcutData.ecoords, self.design.bounds, self.design_transform)
        Veng_coords = mirror_rotate_vector_coords(self.design.VengData.ecoords, self.design.bounds, self.design_transform)
        Gcode_coords = mirror_rotate_vector_coords(self.design.GcodeData.ecoords, self.design.bounds, self.design_transform)
        
        if self.design.RengData.ecoords == []:
            self.make_raster_coords()
        return make_trace_path(bounds, self.laser_scale, self.design.RengData, Vcut_coords, Veng_coords, Gcode_coords, self.trace_gap, self.isRotary)

    ################################################################################

    def send_data(self, operation_type=None, output_filename=None):
        num_passes = 0
        if self.k40 == None and output_filename == None:
            self.reporter.error("Laser Cutter is not Initialized...")
            return
        try:
            feed_factor = self.units.velocity_scale()
            xmin, xmax, ymin, ymax = self.Get_Design_Bounds().bounds

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

            if (operation_type.find("Vector_Cut") > -1) and (self.design.VcutData.ecoords != []):
                Feed_Rate = float(self.Vcut_feed)*feed_factor
                self.reporter.status("Vector Cut: Determining Cut Order....")
                #self.master.update()
                if not self.design.VcutData.sorted and self.inside_first:
                    self.design.VcutData.set_ecoords(optimize_paths(
                        self.design.VcutData.ecoords), data_sorted=True)

                self.reporter.status("Generating EGV data...")
                #self.master.update()

                Vcut_coords = self.design.VcutData.ecoords
                Vcut_coords = mirror_rotate_vector_coords(Vcut_coords, self.design.bounds, self.design_transform)

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

            if (operation_type.find("Vector_Eng") > -1) and (self.design.VengData.ecoords != []):
                Feed_Rate = float(self.Veng_feed)*feed_factor
                self.reporter.status(
                    "Vector Engrave: Determining Cut Order....")
                ##self.master.update()
                if not self.design.VengData.sorted and self.inside_first:
                    self.design.VengData.set_ecoords(optimize_paths(
                        self.design.VengData.ecoords, inside_check=False), data_sorted=True)
                self.reporter.status("Generating EGV data...")
                #self.master.update()

                Veng_coords = self.design.VengData.ecoords
                Veng_coords = mirror_rotate_vector_coords(Veng_coords, self.design.bounds, self.design_transform)

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

            if (operation_type.find("Raster_Eng") > -1) and (self.design.RengData.ecoords != []):
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
                    self.design.RengData.ecoords,
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
                # self.design.RengData.reset_path()

            if (operation_type.find("Gcode_Cut") > -1) and (self.design.GcodeData.ecoords != []):
                self.reporter.status("Generating EGV data...")
                #self.master.update()
                Gcode_coords = self.design.GcodeData.ecoords
                Gcode_coords = mirror_rotate_vector_coords(Gcode_coords, self.design.bounds, self.design_transform)

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

    def GoTo(self, pos):
        xpos = pos[0]
        ypos = pos[1]
        if not isinstance(xpos, Number) or not isinstance(ypos, Number):
            self.reporter.error("Goto parameters are not numbers")
            return
        if (xpos < 0.0) and (not self.HomeUR):
            self.reporter.error("Goto x value should be greater than 0.0")
            return
        elif (xpos > 0.0) and self.HomeUR:
            self.reporter.error("Goto x value should be less than 0.0")
            return
        elif ypos > 0:
            self.reporter.error("Goto y value should be less than 0.0")
            return

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
        self.design.RengData.reset_path()
        self.refreshTime()

    def View_Refresh_and_Reset_RasterPath(self, varName=0, index=0, mode=0):
        self.design.RengData.reset_path()
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

    def Entry_Design_Scale_Callback(self, varname, index, mode):
        self.menu_Reload_Design()

    def menu_Inside_First_Callback(self, varName, index, mode):
        if self.design.GcodeData.ecoords != []:
            if self.design.VcutData.sorted == True:
                self.menu_Reload_Design()
            elif self.design.VengData.sorted == True:
                self.menu_Reload_Design()

    def menu_Calc_Raster_Time(self, event=None):
        self.set_gui("disabled")
        self.stop[0] = False
        self.make_raster_coords()
        self.stop[0] = True
        self.refreshTime()
        self.set_gui("normal")
        self.menu_View_Refresh()

    ##########################################
    #        CANVAS PLOTTING STUFF           #
    ##########################################
    

    def Plot_Data(self):
        if self.inputCSYS and self.design.RengData.image == None:
            xmin, xmax, ymin, ymax = 0.0, 0.0, 0.0, 0.0
        else:
            xmin, xmax, ymin, ymax = self.Get_Design_Bounds().bounds

        ######################################
        ###       Plot Raster Image        ###
        ######################################
        if self.design.RengData.image != None:
            if self.include_Reng:
                try:
                    self.Reng_image = self.design.RengData.image.convert("L")
                    input_dpi = 1000*self.design_scale
                    wim, him = self.design.RengData.image.size
                    new_SCALE = self.SCALE #(1.0/self.PlotScale)/input_dpi #FIXME
                    if new_SCALE != self.SCALE:
                        self.SCALE = new_SCALE
                        nw = int(self.SCALE*wim)
                        nh = int(self.SCALE*him)

                        plot_im = self.design.RengData.image.convert("L")

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
        if self.include_Rpth and self.design.RengData.ecoords != []:

            Xscale = 1/self.laser_scale.x
            Yscale = 1/self.laser_scale.y
            if self.isRotary:
                Rscale = 1/self.laser_scale.r
                Yscale = Yscale*Rscale

            lines = ecoords2lines(self.design.RengData.ecoords,
                                    Scale(Xscale, Yscale),
                                    Position(0, -ymax))
            
            #self.Reng_coords = lines
            self.reporter.data("Reng_coords", lines)

        ######################################
        ###       Plot Veng Coords         ###
        ######################################
        if self.include_Veng:
            plot_coords = mirror_rotate_vector_coords(self.design.VengData.ecoords, self.design.bounds, self.design_transform)

            lines = ecoords2lines(plot_coords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))

            #self.Veng_coords = lines
            self.reporter.data("Veng_coords", lines)

        ######################################
        ###       Plot Vcut Coords         ###
        ######################################
        if self.include_Vcut:

            plot_coords = mirror_rotate_vector_coords(self.design.VcutData.ecoords, self.design.bounds, self.design_transform)

            lines = ecoords2lines(plot_coords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))

            #self.Vcut_coords = lines
            self.reporter.data("Vcut_coords", lines)

        ######################################
        ###       Plot Gcode Coords        ###
        ######################################
        if self.include_Gcde:
            plot_coords = mirror_rotate_vector_coords(self.design.GcodeData.ecoords, self.design.bounds, self.design_transform)

            lines = ecoords2lines(plot_coords,
                                    Scale(1, 1),
                                    Position(-xmin, -ymax))
            
            #self.Gcde_coords = lines
            self.reporter.data("Gcde_coords", lines)

        ######################################
        ###       Plot Trace Coords        ###
        ######################################
        if self.include_Trace:
            Xscale = 1/self.laser_scale.x
            Yscale = 1/self.laser_scale.y
            if self.isRotary:
                Rscale = 1/self.laser_scale.r
                Yscale = Yscale*Rscale

            trace_coords = self.make_trace_path()
            lines = ecoords2lines(trace_coords,
                                    Scale(Xscale, Yscale),
                                    Position(-xmin, -ymax))
            
            #self.trace_coords = lines
            self.reporter.data("Trace_coords", lines)

        ######################################
        self.refreshTime()


################################################################################
#                          Startup Application                                 #
################################################################################

if __name__ == "__main__":
    app = Laser_Service.instance()
    app.Initialize_Laser()
