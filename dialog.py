################################################################################
#                         Choose Units Dialog                                  #
################################################################################

import tkinter.simpledialog as tkSimpleDialog


class UnitsDialog(tkSimpleDialog.Dialog):
    def body(self, master):
        self.resizable(0, 0)
        self.title('Units')
        self.iconname("Units")

        try:
            self.iconbitmap(bitmap="@emblem64")
        except:
            pass

        self.uom = StringVar()
        self.uom.set("Millimeters")

        Label(master, text="Select DXF Import Units:").grid(row=0)
        Radio_Units_IN = Radiobutton(
            master, text="Inches",        value="Inches")
        Radio_Units_MM = Radiobutton(
            master, text="Millimeters",   value="Millimeters")
        Radio_Units_CM = Radiobutton(
            master, text="Centimeters",   value="Centimeters")

        Radio_Units_IN.grid(row=1, sticky=W)
        Radio_Units_MM.grid(row=2, sticky=W)
        Radio_Units_CM.grid(row=3, sticky=W)

        Radio_Units_IN.configure(variable=self.uom)
        Radio_Units_MM.configure(variable=self.uom)
        Radio_Units_CM.configure(variable=self.uom)

    def apply(self):
        self.result = self.uom.get()
        return


class toplevel_dummy():
    def winfo_exists(self):
        return False


class pxpiDialog(tkSimpleDialog.Dialog):

    def __init__(self,
                 parent,
                 units="mm",
                 SVG_Size=None,
                 SVG_ViewBox=None,
                 SVG_inkscape_version=None):

        self.result = None
        self.svg_pxpi = StringVar()
        self.other = StringVar()
        self.svg_width = StringVar()
        self.svg_height = StringVar()
        self.svg_units = StringVar()
        self.fixed_size = False
        self.svg_units.set(units)
        if units == "mm":
            self.scale = 1.0
        else:
            self.scale = 1/25.4

        ###################################
        ##       Set initial pxpi          #
        ###################################
        pxpi = 72.0
        if SVG_inkscape_version != None:
            if SVG_inkscape_version >= .92:
                pxpi = 96.0
            else:
                pxpi = 90.0

        self.svg_pxpi.set("%d" % (pxpi))
        self.other.set("%d" % (pxpi))

        ###################################
        ##       Set minx/miny            #
        ###################################
        if SVG_ViewBox != None and SVG_ViewBox[0] != None and SVG_ViewBox[1] != None:
            self.minx_pixels = SVG_ViewBox[0]
            self.miny_pixels = SVG_ViewBox[1]
        else:
            self.minx_pixels = 0.0
            self.miny_pixels = 0.0

        ###################################
        ##       Set Initial Size         #
        ###################################
        if SVG_Size != None and SVG_Size[2] != None and SVG_Size[3] != None:
            self.width_pixels = SVG_Size[2]
            self.height_pixels = SVG_Size[3]
        elif SVG_ViewBox != None and SVG_ViewBox[2] != None and SVG_ViewBox[3] != None:
            self.width_pixels = SVG_ViewBox[2]
            self.height_pixels = SVG_ViewBox[3]
        else:
            self.width_pixels = 500.0
            self.height_pixels = 500.0
        ###################################
        ##       Set Initial Size         #
        ###################################
        if SVG_Size[0] != None and SVG_Size[1] != None:
            width = SVG_Size[0]
            height = SVG_Size[1]
            self.fixed_size = True
        else:
            width = self.width_pixels/float(self.svg_pxpi.get())*25.4
            height = self.height_pixels/float(self.svg_pxpi.get())*25.4

        self.svg_width.set("%f" % (width*self.scale))
        self.svg_height.set("%f" % (height*self.scale))
        ###################################
        tkinter.simpledialog.Dialog.__init__(self, parent)

    def body(self, master):
        self.resizable(0, 0)
        self.title('SVG Import Scale:')
        self.iconname("SVG Scale")
        try:
            self.iconbitmap(bitmap="@emblem64")
        except:
            pass

        ###########################################################################
        def Entry_custom_Check():
            try:
                value = float(self.other.get())
                if value <= 0.0:
                    return 2  # Value is invalid number
            except:
                return 3     # Value not a number
            return 0         # Value is a valid number

        def Entry_custom_Callback(varName, index, mode):
            if Entry_custom_Check() > 0:
                Entry_Custom_pxpi.configure(bg='red')
            else:
                Entry_Custom_pxpi.configure(bg='white')
                pxpi = float(self.other.get())
                width = self.width_pixels/pxpi*25.4
                height = self.height_pixels/pxpi*25.4
                if self.fixed_size:
                    pass
                else:
                    Set_Value(width=width*self.scale, height=height*self.scale)
                self.svg_pxpi.set("custom")
        ###################################################

        def Entry_Width_Check():
            try:
                value = float(self.svg_width.get())/self.scale
                if value <= 0.0:
                    return 2  # Value is invalid number
            except:
                return 3     # Value not a number
            return 0         # Value is a valid number

        def Entry_Width_Callback(varName, index, mode):
            if Entry_Width_Check() > 0:
                Entry_Custom_Width.configure(bg='red')
            else:
                Entry_Custom_Width.configure(bg='white')
                width = float(self.svg_width.get())/self.scale
                pxpi = self.width_pixels*25.4/width
                height = self.height_pixels/pxpi*25.4
                Set_Value(other=pxpi, height=height*self.scale)
                self.svg_pxpi.set("custom")
        ###################################################

        def Entry_Height_Check():
            try:
                value = float(self.svg_height.get())
                if value <= 0.0:
                    return 2  # Value is invalid number
            except:
                return 3     # Value not a number
            return 0         # Value is a valid number

        def Entry_Height_Callback(varName, index, mode):
            if Entry_Height_Check() > 0:
                Entry_Custom_Height.configure(bg='red')
            else:
                Entry_Custom_Height.configure(bg='white')
                height = float(self.svg_height.get())/self.scale
                pxpi = self.height_pixels*25.4/height
                width = self.width_pixels/pxpi*25.4
                Set_Value(other=pxpi, width=width*self.scale)
                self.svg_pxpi.set("custom")
        ###################################################

        def SVG_pxpi_callback(varName, index, mode):
            if self.svg_pxpi.get() == "custom":
                try:
                    pxpi = float(self.other.get())
                except:
                    pass
            else:
                pxpi = float(self.svg_pxpi.get())
                width = self.width_pixels/pxpi*25.4
                height = self.height_pixels/pxpi*25.4
                if self.fixed_size:
                    Set_Value(other=pxpi)
                else:
                    Set_Value(other=pxpi, width=width*self.scale,
                              height=height*self.scale)

        ###########################################################################

        def Set_Value(other=None, width=None, height=None):
            self.svg_pxpi.trace_vdelete("w", self.trace_id_svg_pxpi)
            self.other.trace_vdelete("w", self.trace_id_pxpi)
            self.svg_width.trace_vdelete("w", self.trace_id_width)
            self.svg_height.trace_vdelete("w", self.trace_id_height)
            self.update_idletasks()

            if other != None:
                self.other.set("%f" % (other))
            if width != None:
                self.svg_width.set("%f" % (width))
            if height != None:
                self.svg_height.set("%f" % (height))

            self.trace_id_svg_pxpi = self.svg_pxpi.trace_variable(
                "w", SVG_pxpi_callback)
            self.trace_id_pxpi = self.other.trace_variable(
                "w", Entry_custom_Callback)
            self.trace_id_width = self.svg_width.trace_variable(
                "w", Entry_Width_Callback)
            self.trace_id_height = self.svg_height.trace_variable(
                "w", Entry_Height_Callback)
            self.update_idletasks()

        ###########################################################################
        t0 = "This dialog opens if the SVG file you are opening\n"
        t1 = "does not contain enough information to determine\n"
        t2 = "the intended physical size of the design.\n"
        t3 = "Select an SVG Import Scale:\n"
        Title_Text0 = Label(master, text=t0+t1+t2, anchor=W)
        Title_Text1 = Label(master, text=t3, anchor=W)

        Radio_SVG_pxpi_96 = Radiobutton(
            master, text=" 96 units/in", value="96")
        Label_SVG_pxpi_96 = Label(
            master, text="(File saved with Inkscape v0.92 or newer)", anchor=W)

        Radio_SVG_pxpi_90 = Radiobutton(
            master, text=" 90 units/in", value="90")
        Label_SVG_pxpi_90 = Label(
            master, text="(File saved with Inkscape v0.91 or older)", anchor=W)

        Radio_SVG_pxpi_72 = Radiobutton(
            master, text=" 72 units/in", value="72")
        Label_SVG_pxpi_72 = Label(
            master, text="(File saved with Adobe Illustrator)", anchor=W)

        Radio_Res_Custom = Radiobutton(master, text=" Custom:", value="custom")
        Bottom_row = Label(master, text=" ")

        Entry_Custom_pxpi = Entry(master, width="10")
        Entry_Custom_pxpi.configure(textvariable=self.other)
        Label_pxpi_units = Label(master, text="units/in", anchor=W)
        self.trace_id_pxpi = self.other.trace_variable(
            "w", Entry_custom_Callback)

        Label_Width = Label(master, text="Width", anchor=W)
        Entry_Custom_Width = Entry(master, width="10")
        Entry_Custom_Width.configure(textvariable=self.svg_width)
        Label_Width_units = Label(
            master, textvariable=self.svg_units, anchor=W)
        self.trace_id_width = self.svg_width.trace_variable(
            "w", Entry_Width_Callback)

        Label_Height = Label(master, text="Height", anchor=W)
        Entry_Custom_Height = Entry(master, width="10")
        Entry_Custom_Height.configure(textvariable=self.svg_height)
        Label_Height_units = Label(
            master, textvariable=self.svg_units, anchor=W)
        self.trace_id_height = self.svg_height.trace_variable(
            "w", Entry_Height_Callback)

        if self.fixed_size == True:
            Entry_Custom_Width.configure(state="disabled")
            Entry_Custom_Height.configure(state="disabled")
        ###########################################################################
        rn = 0
        Title_Text0.grid(row=rn, column=0, columnspan=5, sticky=W)

        rn = rn+1
        Title_Text1.grid(row=rn, column=0, columnspan=5, sticky=W)

        rn = rn+1
        Radio_SVG_pxpi_96.grid(row=rn, sticky=W)
        Label_SVG_pxpi_96.grid(row=rn, column=1, columnspan=50, sticky=W)

        rn = rn+1
        Radio_SVG_pxpi_90.grid(row=rn, sticky=W)
        Label_SVG_pxpi_90.grid(row=rn, column=1, columnspan=50, sticky=W)

        rn = rn+1
        Radio_SVG_pxpi_72.grid(row=rn, column=0, sticky=W)
        Label_SVG_pxpi_72.grid(row=rn, column=1, columnspan=50, sticky=W)

        rn = rn+1
        Radio_Res_Custom.grid(row=rn, column=0, sticky=W)
        Entry_Custom_pxpi.grid(row=rn, column=1, sticky=E)
        Label_pxpi_units.grid(row=rn, column=2, sticky=W)

        rn = rn+1
        Label_Width.grid(row=rn, column=0, sticky=E)
        Entry_Custom_Width.grid(row=rn, column=1, sticky=E)
        Label_Width_units.grid(row=rn, column=2, sticky=W)

        rn = rn+1
        Label_Height.grid(row=rn, column=0, sticky=E)
        Entry_Custom_Height.grid(row=rn, column=1, sticky=E)
        Label_Height_units.grid(row=rn, column=2, sticky=W)

        rn = rn+1
        Bottom_row.grid(row=rn, columnspan=50)

        Radio_SVG_pxpi_96.configure(variable=self.svg_pxpi)
        Radio_SVG_pxpi_90.configure(variable=self.svg_pxpi)
        Radio_SVG_pxpi_72.configure(variable=self.svg_pxpi)
        Radio_Res_Custom.configure(variable=self.svg_pxpi)
        self.trace_id_svg_pxpi = self.svg_pxpi.trace_variable(
            "w", SVG_pxpi_callback)
        ###########################################################################

    def apply(self):
        width = float(self.svg_width.get())/self.scale
        height = float(self.svg_height.get())/self.scale
        pxpi = float(self.other.get())
        viewbox = [self.minx_pixels, self.miny_pixels,
                   width/25.4*pxpi, height/25.4*pxpi]
        self.result = pxpi, viewbox
        return
