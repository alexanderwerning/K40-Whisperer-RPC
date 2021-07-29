from ecoords import ECoord
from svg_reader import SVG_PXPI_EXCEPTION, SVG_READER, SVG_TEXT_EXCEPTION
from dxf import DXF_CLASS
from g_code_library import G_Code_Rip

def Open_SVG(filename, design_scale, inkscape_path, ink_timeout, reporter):
       
    svg_reader = SVG_READER()
    svg_reader.set_inkscape_path(inkscape_path)
    input_dpi = 1000*design_scale
    svg_reader.image_dpi = input_dpi
    svg_reader.timout = int(float(ink_timeout)*60.0)
    dialog_pxpi = None
    dialog_viewbox = None
    try:
        try:
            try:
                svg_reader.parse_svg(filename)
                svg_reader.make_paths()
            except SVG_PXPI_EXCEPTION as e:
                reporter.error(str(e))
                # pxpi_dialog = pxpiDialog(root, #FIXME
                #                          units,
                #                          svg_reader.SVG_Size,
                #                          svg_reader.SVG_ViewBox,
                #                          svg_reader.SVG_inkscape_version)

                svg_reader = SVG_READER()
                svg_reader.set_inkscape_path(inkscape_path)
                # if True:#pxpi_dialog.result == None: #FIXME
                #     return
                reporter.warning("No units or viewbox defined in svg file, using mm and (0,0,100,100) for now.")
                dialog_pxpi, dialog_viewbox = "mm", (0, 0, 100, 100)#pxpi_dialog.result
                svg_reader.parse_svg(filename)
                svg_reader.set_size(
                    dialog_pxpi, dialog_viewbox, design_scale)
                svg_reader.make_paths()

        except SVG_TEXT_EXCEPTION as e:
            svg_reader = SVG_READER()
            svg_reader.set_inkscape_path(inkscape_path)
            reporter.status("Converting TEXT to PATHS.")
            #master.update()
            svg_reader.parse_svg(filename)
            if dialog_pxpi != None and dialog_viewbox != None:
                svg_reader.set_size(
                    dialog_pxpi, dialog_viewbox, design_scale)
            svg_reader.make_paths(txt2paths=True)

    except Exception as e:
        reporter.error(f"SVG file load failed: {e}")
        return
    except:
        reporter.status(f"Unable To open SVG File: {filename}")
        return
    xmax = svg_reader.Xsize*design_scale
    ymax = svg_reader.Ysize*design_scale
    xmin = 0
    ymin = 0
    
    Design_bounds = (xmin, xmax, ymin, ymax)

    ##########################
    ###   Create ECOORDS   ###
    ##########################
    VcutData = ECoord()
    VengData = ECoord()
    VcutData.make_ecoords(
        svg_reader.cut_lines, scale=design_scale)
    VengData.make_ecoords(
        svg_reader.eng_lines, scale=design_scale)

    ##########################
    ###   Load Image       ###
    ##########################
    RengData = ECoord()
    #RengData.set_image(svg_reader.raster_PIL) #FIXME not created in svg_reader, too slow

    margin = 0.0625  # A bit of margin to prevent the warningwindow for designs that are close to being within the bounds
    if Design_bounds[0] > VengData.bounds[0]+margin or\
        Design_bounds[0] > VcutData.bounds[0]+margin or\
        Design_bounds[1] < VengData.bounds[1]-margin or\
        Design_bounds[1] < VcutData.bounds[1]-margin or\
        Design_bounds[2] > VengData.bounds[2]+margin or\
        Design_bounds[2] > VcutData.bounds[2]+margin or\
        Design_bounds[3] < VengData.bounds[3]-margin or\
        Design_bounds[3] < VcutData.bounds[3]-margin:
        line1 = "Warning:\n"
        line2 = "There is vector cut or vector engrave data located outside of the SVG page bounds.\n\n"
        line3 = "K40 Whisperer will attempt to use all of the vector data.  "
        line4 = "Please verify that the vector data is not outside of your lasers working area before engraving."
        reporter.warning(line1+line2+line3+line4)
    
    return VcutData, VengData, RengData, Design_bounds


def Open_G_Code(filename, reporter):
    g_rip = G_Code_Rip()
    try:
        msg = g_rip.Read_G_Code(
            filename, XYarc2line=True, arc_angle=2, units="in", Accuracy="")
        Error_Text = ""
        if msg != []:
            reporter.error("\n".join(msg))

    except Exception as e:
        reporter.error(f"G-Code Load Failed:  {e}")

    ecoords = g_rip.generate_laser_paths(g_rip.g_code_data)
    GcodeData = ECoord()
    GcodeData.set_ecoords(ecoords, data_sorted=True)
    Design_bounds = GcodeData.bounds

    return GcodeData, Design_bounds


def Open_DXF(filename, design_scale, reporter):

    dxf_import = DXF_CLASS()
    tolerance = .0005
    try:
        fd = open(filename)
        dxf_import.GET_DXF_DATA(
            fd, lin_tol=tolerance, get_units=True, units=None)
        fd.seek(0)

        dxf_units = dxf_import.units
        if dxf_units == "Unitless":
            #d = UnitsDialog(root) #FIXME
            #dxf_units = d.result
            reporter.warning("No unit defined in dxf file, using mm.")
            dxf_scale = 1.0
        if dxf_units == "Inches":
            dxf_scale = 25.4
        elif dxf_units == "Feet":
            dxf_scale = 25.4*12.0
        elif dxf_units == "Miles":
            dxf_scale = 5280.0*25.4*12.0
        elif dxf_units == "Millimeters":
            dxf_scale = 1.0
        elif dxf_units == "Centimeters":
            dxf_scale = 10.0
        elif dxf_units == "Meters":
            dxf_scale = 1000.0
        elif dxf_units == "Kilometers":
            dxf_scale = 1000000.0
        elif dxf_units == "Microinches":
            dxf_scale = 25.4/1000000.0
        elif dxf_units == "Mils":
            dxf_scale = 25.4/1000.0
        else:
            return

        lin_tol = tolerance / dxf_scale * design_scale
        dxf_import.GET_DXF_DATA(
            fd, lin_tol=lin_tol, get_units=False, units=None)
        fd.close()
    # except StandardError as e:
    except Exception as e:
        msg1 = "DXF Load Failed:"
        msg2 = "%s" % (e)
        reporter.error((msg1+msg2).split("\n")[0])
    except:
        reporter.error("Unable To open Drawing Exchange File (DXF) file.")
        return

    dxf_engrave_coords = dxf_import.DXF_COORDS_GET_TYPE(
        engrave=True, new_origin=False)
    dxf_cut_coords = dxf_import.DXF_COORDS_GET_TYPE(
        engrave=False, new_origin=False)

    if dxf_import.dxf_messages != "":
        msg_split = dxf_import.dxf_messages.split("\n")
        msg_split.sort()
        msg_split.append("")
        mcnt = 1
        msg_out = ""
        for i in range(1, len(msg_split)):
            if msg_split[i-1] == msg_split[i]:
                mcnt = mcnt+1
            else:
                if msg_split[i-1] != "":
                    msg_line = f"{msg_split[i-1]} ({mcnt} places)\n"
                    msg_out = msg_out + msg_line
                mcnt = 1
        reporter.information(msg_out)

    ##########################
    ###   Create ECOORDS   ###
    ##########################
    VcutData = ECoord()
    VengData = ECoord()
    VcutData.make_ecoords(dxf_cut_coords, scale=dxf_scale)
    VengData.make_ecoords(dxf_engrave_coords, scale=dxf_scale)

    xmin = min(VcutData.bounds[0], VengData.bounds[0])
    xmax = max(VcutData.bounds[1], VengData.bounds[1])
    ymin = min(VcutData.bounds[2], VengData.bounds[2])
    ymax = max(VcutData.bounds[3], VengData.bounds[3])
    Design_bounds = (xmin, xmax, ymin, ymax)

    return VcutData, VengData, Design_bounds