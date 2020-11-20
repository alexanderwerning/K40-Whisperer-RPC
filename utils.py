"""This module collects all functions pulled out from k40_whisperer.py"""

DEBUG = False
QUIET = False

def format_time(time_in_seconds):
    # format the duration from seconds to something human readable
    if time_in_seconds != None and time_in_seconds >= 0:
        s = round(time_in_seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        res = ""
        if h > 0:
            res = "%dh " % (h)
        if m > 0:
            res += "%dm " % (m)
        if h == 0:
            res += "%ds " % (s)
        return res
    else:
        return "?"


def Scale_Text_Value(format_txt, Text_Value, factor):
    try:
        return format_txt % (float(Text_Value)*factor)
    except:
        return ''


def rotate_raster(image_in):
    wim, him = image_in.size
    im_rotated = Image.new("L", (him, wim), "white")

    image_in_np = image_in.load()
    im_rotated_np = im_rotated.load()

    for i in range(1, him):
        for j in range(1, wim):
            im_rotated_np[i, wim-j] = image_in_np[j, i]
    return im_rotated


def get_raster_step_1000in(self, rast_step):
    val_in = float(rast_step)
    value = int(round(val_in*1000.0, 1))
    return value


def generate_bezier(M1, M2, w, n=100):
    if (M1 == M2):
        x1 = 0
        y1 = 0
    else:
        x1 = 255*(1-M2)/(M1-M2)
        y1 = M1*x1
    x = []
    y = []
    # Calculate Bezier Curve
    for step in range(0, n+1):
        t = float(step)/float(n)
        Ct = 1 / (pow(1-t, 2)+2*(1-t)*t*w+pow(t, 2))
        x.append(Ct*(2*(1-t)*t*w*x1+pow(t, 2)*255))
        y.append(Ct*(2*(1-t)*t*w*y1+pow(t, 2)*255))
    return x, y


def LASER_Size(units, laserXsize, laserYsize):
    MINX = 0.0
    MAXY = 0.0
    if units == "in":
        MAXX = float(laserXsize)
        MINY = -float(laserYsize)
    else:
        MAXX = float(laserXsize)/25.4
        MINY = -float(laserYsize)/25.4

    return (MAXX-MINX, MAXY-MINY)


def gcode_error_message(message):
    error_report = Toplevel(width=525, height=60)
    error_report.title("G-Code Reading Errors/Warnings")
    error_report.iconname("G-Code Errors")
    error_report.grab_set()
    return_value = StringVar()
    return_value.set("none")

    try:
        error_report.iconbitmap(bitmap="@emblem64")
    except:
        debug_message(traceback.format_exc())
        pass

    def Close_Click(event):
        return_value.set("close")
        error_report.destroy()

    # Text Box
    Error_Frame = Frame(error_report)
    scrollbar = Scrollbar(Error_Frame, orient=VERTICAL)
    Error_Text = Text(Error_Frame, width="80", height="20",
                        yscrollcommand=scrollbar.set, bg='white')
    for line in message:
        Error_Text.insert(END, line+"\n")
    scrollbar.config(command=Error_Text.yview)
    scrollbar.pack(side=RIGHT, fill=Y)
    # End Text Box

    Button_Frame = Frame(error_report)
    close_button = Button(Button_Frame, text=" Close ")
    close_button.bind("<ButtonRelease-1>", Close_Click)
    close_button.pack(side=RIGHT, fill=X)

    Error_Text.pack(side=LEFT, fill=BOTH, expand=1)
    Button_Frame.pack(side=BOTTOM)
    Error_Frame.pack(side=LEFT, fill=BOTH, expand=1)

    root.wait_window(error_report)
    return return_value.get()

def Sort_Paths(self, ecoords, i_loop=2):
    ##########################
    ###   find loop ends   ###
    ##########################
    Lbeg = []
    Lend = []
    if len(ecoords) > 0:
        Lbeg.append(0)
        loop_old = ecoords[0][i_loop]
        for i in range(1, len(ecoords)):
            loop = ecoords[i][i_loop]
            if loop != loop_old:
                Lbeg.append(i)
                Lend.append(i-1)
            loop_old = loop
        Lend.append(i)

    #######################################################
    # Find new order based on distance to next beg or end #
    #######################################################
    order_out = []
    use_beg = 0
    if len(ecoords) > 0:
        order_out.append([Lbeg[0], Lend[0]])
    inext = 0
    total = len(Lbeg)
    for i in range(total-1):
        if use_beg == 1:
            ii = Lbeg.pop(inext)
            Lend.pop(inext)
        else:
            ii = Lend.pop(inext)
            Lbeg.pop(inext)

        Xcur = ecoords[ii][0]
        Ycur = ecoords[ii][1]

        dx = Xcur - ecoords[Lbeg[0]][0]
        dy = Ycur - ecoords[Lbeg[0]][1]
        min_dist = dx*dx + dy*dy

        dxe = Xcur - ecoords[Lend[0]][0]
        dye = Ycur - ecoords[Lend[0]][1]
        min_diste = dxe*dxe + dye*dye

        inext = 0
        inexte = 0
        for j in range(1, len(Lbeg)):
            dx = Xcur - ecoords[Lbeg[j]][0]
            dy = Ycur - ecoords[Lbeg[j]][1]
            dist = dx*dx + dy*dy
            if dist < min_dist:
                min_dist = dist
                inext = j
            ###
            dxe = Xcur - ecoords[Lend[j]][0]
            dye = Ycur - ecoords[Lend[j]][1]
            diste = dxe*dxe + dye*dye
            if diste < min_diste:
                min_diste = diste
                inexte = j
            ###
        if min_diste < min_dist:
            inext = inexte
            order_out.append([Lend[inexte], Lbeg[inexte]])
            use_beg = 1
        else:
            order_out.append([Lbeg[inext], Lend[inext]])
            use_beg = 0
    ###########################################################
    return order_out

#####################################################
# determine if a point is inside a given polygon or not
# Polygon is a list of (x,y) pairs.
# http://www.ariel.com.au/a/python-point-int-poly.html
#####################################################

def point_inside_polygon(x, y, poly):
    n = len(poly)
    inside = -1
    p1x = poly[0][0]
    p1y = poly[0][1]
    for i in range(n+1):
        p2x = poly[i % n][0]
        p2y = poly[i % n][1]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                    if p1x == p2x or x <= xinters:
                        inside = inside * -1
        p1x, p1y = p2x, p2y

    return inside

################################################################################
#             Function for outputting messages to different locations          #
#            depending on what options are enabled                             #
################################################################################
def fmessage(text, newline=True):
    if (not QUIET):
        if newline == True:
            try:
                sys.stdout.write(text)
                sys.stdout.write("\n")
                debug_message(traceback.format_exc())
            except:
                debug_message(traceback.format_exc())
                pass
        else:
            try:
                sys.stdout.write(text)
                debug_message(traceback.format_exc())
            except:
                debug_message(traceback.format_exc())
                pass

################################################################################
#                               Message Box                                    #
################################################################################


def message_box(title, message):
    title = "%s (K40 Whisperer V%s)" % (title, version)
    tkinter.messagebox.showinfo(title, message)

################################################################################
#                          Message Box ask OK/Cancel                           #
################################################################################


def message_ask_ok_cancel(title, mess):
    result = tkinter.messagebox.askokcancel(title, mess)
    return result

################################################################################
#                         Debug Message Box                                    #
################################################################################


def debug_message(message):
    title = "Debug Message"
    if DEBUG:
        tkinter.messagebox.showinfo(title, message)