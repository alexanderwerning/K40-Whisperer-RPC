"""This module collects all functions pulled out from k40_whisperer.py"""

from time import time
from math import sqrt
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
            res = f"{h}h "
        if m > 0:
            res += f"{m}m "
        if h == 0:
            res += f"{s}s "
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


def get_raster_step_1000in(rast_step):
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


def Sort_Paths(ecoords, i_loop=2):
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

def ecoords2lines(ecoords, scale, shift):
    lines = []
    loop_old = -1
    xold = 0
    yold = 0
    for line in ecoords:
        XY = line
        x1 = XY[0]*scale.x+shift.x
        y1 = XY[1]*scale.y+shift.y
        loop = XY[2]
        # check and see if we need to move to a new discontinuous start point
        if (loop == loop_old):
            lines.append([xold, yold, x1, y1])
        loop_old = loop
        xold = x1
        yold = y1
    return lines



from k40_web.laser_controller.interpolate import interpolate

'''This Example opens an Image and transform the image into halftone.  -Isai B. Cicourel'''
# Create a Half-tone version of the image

def convert_halftoning(image, bezier_settings):
    image = image.convert('L')
    x_lim, y_lim = image.size
    pixel = image.load()

    M1 = bezier_settings.bezier_M1
    M2 = bezier_settings.bezier_M2
    w = bezier_settings.bezier_weight

    if w > 0:
        x, y = generate_bezier(M1, M2, w)

        interp = interpolate(x, y)  # Set up interpolate class
        val_map = []
        # Map Bezier Curve to values between 0 and 255
        for val in range(0, 256):
            # Get the interpolated value at each value
            val_out = int(round(interp[val]))
            val_map.append(val_out)
        # Adjust image
        timestamp = 0
        for y in range(1, y_lim):
            # stamp = int(3*time())  # update every 1/3 of a second
            # if (stamp != timestamp):
            #     timestamp = stamp  # interlock
                # self.reporter.status( # if this would be faster, feedback would be unnecessary
                #     "Adjusting Image Darkness: %.1f %%" % ((100.0*y)/y_lim))
                #self.master.update()
            for x in range(1, x_lim):
                pixel[x, y] = val_map[pixel[x, y]]

    #self.master.update()
    image = image.convert('1')
    return image

from k40_web.laser_controller.convex_hull import hull2D
from PIL import Image, ImageOps

def make_raster_coords(RengData, laser_scale, design_transform, isRotary, bezier_settings, reporter, rast_step):

    if RengData.rpaths:
        return
    try:
        hcoords = []
        if (RengData.image != None and RengData.ecoords == []):
            ecoords = []
            cutoff = 128
            image_temp = RengData.image.convert("L")

            if design_transform.negate:
                image_temp = ImageOps.invert(image_temp)

            if design_transform.mirror:
                image_temp = ImageOps.mirror(image_temp)

            if design_transform.rotate:
                image_temp = rotate_raster(image_temp)

            if isRotary:
                scale_y = laser_scale.y*laser_scale.r
            else:
                scale_y = laser_scale.y

            if laser_scale.x != 1.0 or scale_y != 1.0:
                wim, him = image_temp.size
                nw = int(wim*laser_scale.x)
                nh = int(him*scale_y)
                image_temp = image_temp.resize((nw, nh))

            if design_transform.halftone:
                ht_size_mils = round(1000.0 / float(design_transform.ht_size), 1)
                npixels = int(round(ht_size_mils, 1))
                if npixels == 0:
                    return
                wim, him = image_temp.size
                # Convert to Halftoning and save
                nw = int(wim / npixels)
                nh = int(him / npixels)
                image_temp = image_temp.resize((nw, nh))

                image_temp = convert_halftoning(image_temp, bezier_settings)
                reporter.status("Creating Halftone Image.")
                image_temp = image_temp.resize((wim, him))
            else:
                image_temp = image_temp.point(
                    lambda x: 0 if x < 128 else 255, '1')
                #image_temp = image_temp.convert('1',dither=Image.NONE)

            if DEBUG:
                image_name = os.path.expanduser("~")+"/IMAGE.png"
                image_temp.save(image_name, "PNG")

            Reng_np = image_temp.load()
            wim, him = image_temp.size
            del image_temp
            #######################################
            x = 0
            y = 0
            loop = 1
            LENGTH = 0
            n_scanlines = 0

            my_hull = hull2D()
            bignumber = 9999999
            Raster_step = get_raster_step_1000in(rast_step)
            timestamp = 0
            for i in range(0, him, Raster_step):
                stamp = int(10*time())  # update every second
                if (stamp != timestamp):
                    timestamp = stamp  # interlock
                    reporter.status(f"Creating Scan Lines: {(100.0*i)/him:.1f}%")
                # if self.stop[0] == True:
                #     raise Exception("Action stopped by User.")
                line = []
                cnt = 1
                LEFT = bignumber
                RIGHT = -bignumber
                for j in range(1, wim):
                    if (Reng_np[j, i] == Reng_np[j-1, i]):
                        cnt = cnt+1
                    else:
                        if Reng_np[j-1, i]:
                            laser = "U"
                        else:
                            laser = "D"
                            LEFT = min(j-cnt, LEFT)
                            RIGHT = max(j, RIGHT)

                        line.append((cnt, laser))
                        cnt = 1
                if Reng_np[j-1, i] > cutoff:
                    laser = "U"
                else:
                    laser = "D"
                    LEFT = min(j-cnt, LEFT)
                    RIGHT = max(j, RIGHT)

                line.append((cnt, laser))
                if LEFT != bignumber and RIGHT != -bignumber:
                    LENGTH = LENGTH + (RIGHT - LEFT)/1000.0
                    n_scanlines = n_scanlines + 1

                y = (him-i)/1000.0
                x = 0
                if LEFT != bignumber:
                    hcoords.append([LEFT/1000.0, y])
                if RIGHT != -bignumber:
                    hcoords.append([RIGHT/1000.0, y])
                if hcoords != []:
                    hcoords = my_hull.convexHullecoords(hcoords)

                rng = list(range(0, len(line), 1))

                for i in rng:
                    seg = line[i]
                    delta = seg[0]/1000.0
                    if seg[1] == "D":
                        loop = loop+1
                        ecoords.append([x, y, loop])
                        ecoords.append([x+delta, y, loop])
                    x = x + delta
            
            reporter.status("Creating Scan Lines: 100%")

            RengData.set_ecoords(ecoords, data_sorted=True)
            RengData.len = LENGTH
            RengData.n_scanlines = n_scanlines
        # Set Flag indicating raster paths have been calculated
        RengData.rpaths = True
        RengData.hull_coords = hcoords

    except MemoryError as e:
        reporter.error("Memory Error:  Out of Memory.")

    except Exception as e:
        msg1 = "Making Raster Coords Stopped: "
        msg2 = "%s" % (e)
        reporter.error((msg1+msg2))


def offset_ecoords(ecoords_in, offset_val):
    # the (original) pyclipper implementation is not needed here,
    # with convex polygons we can simply shift the vertices.
    # this only applies for the trace coords of course

    filtered_ecoords = []
    first = True
    last_x = 0
    last_y = 0
    removed = []
    for i, ecoord in enumerate(ecoords_in):
        if first:
            first = False
            last_x = ecoord[0]
            last_y = ecoord[1]
            filtered_ecoords.append(ecoord)
        elif last_x != ecoord[0] or last_y != ecoord[1]:
            filtered_ecoords.append(ecoord)
        else:
            removed.append(i)

    edge_normals = []
    for i in range(len(filtered_ecoords)-1):
        x1, y1 = filtered_ecoords[i][0], filtered_ecoords[i][1]
        x2, y2 = filtered_ecoords[i+1][0], filtered_ecoords[i+1][1]
        
        doublelength = 2*sqrt((x2-x1)**2+(y2-y1)**2)
        edge_normals.append([(y2-y1)/doublelength, -(x2-x1)/doublelength])
    
    x1, y1 = filtered_ecoords[-1][0], filtered_ecoords[-1][1]
    x2, y2 = filtered_ecoords[0][0], filtered_ecoords[0][1]
    doublelength = 2*sqrt((x2-x1)**2+(y2-y1)**2)
    loop_normal = [(y2-y1)/doublelength, -(x2-x1)/doublelength]
    edge_normals.append(loop_normal)
    edge_normals.insert(0, loop_normal)

    point_normals = []
    for i in range(len(edge_normals)-1):
        en1 = edge_normals[i]
        en2 = edge_normals[i]
        point_normals.append([en1[0]+en2[0], en1[1]+en2[1]])

    ecoords_out = []
    for i, ecoord in enumerate(filtered_ecoords):
        ecoords_out.append([ecoord[0]+point_normals[i][0]*offset_val,
                            ecoord[1]+point_normals[i][1]*offset_val,
                            ecoord[2]])
        if i+1 in removed:
            ecoords_out.append(ecoords_out[-1])
    
    ecoords_out.append(ecoords_out[0])

    return ecoords_out

def scale_vector_coords(coords, startx, starty, laser_scale, isRotary):
    Xscale = laser_scale.x
    Yscale = laser_scale.y
    if isRotary:
        Yscale = Yscale*laser_scale.r

    coords_scale = []
    if Xscale != 1.0 or Yscale != 1.0:
        for i in range(len(coords)):
            coords_scale.append(coords[i][:])
            x = coords_scale[i][0]
            y = coords_scale[i][1]
            coords_scale[i][0] = x*Xscale
            coords_scale[i][1] = y*Yscale
        scaled_startx = startx*Xscale
        scaled_starty = starty*Yscale
    else:
        coords_scale = coords
        scaled_startx = startx
        scaled_starty = starty

    return coords_scale, scaled_startx, scaled_starty

def make_trace_path(design_bounds, laser_scale, RengData,
    Vcut_coords, Veng_coords, Gcode_coords, trace_gap, isRotary):
    my_hull = hull2D()
    xmin, xmax, ymin, ymax = design_bounds.bounds
    startx = xmin
    starty = ymax


    RengHullCoords = []
    Xscale = 1/laser_scale.x
    Yscale = 1/laser_scale.y
    if isRotary:
        Rscale = 1/laser_scale.r
        Yscale = Yscale*Rscale

    for point in RengData.hull_coords:
        RengHullCoords.append(
            [point[0]*Xscale+xmin, point[1]*Yscale, point[2]])

    all_coords = []
    all_coords.extend(Vcut_coords)
    all_coords.extend(Veng_coords)
    all_coords.extend(Gcode_coords)
    all_coords.extend(RengHullCoords)

    trace_coords = []
    if all_coords != []:
        trace_coords = my_hull.convexHullecoords(all_coords)
        trace_coords = offset_ecoords(trace_coords, trace_gap)

    trace_coords, startx, starty = scale_vector_coords(
        trace_coords, startx, starty, laser_scale, isRotary)
    return trace_coords

def optimize_paths(ecoords, inside_check=True):
    order_out = Sort_Paths(ecoords)
    lastx = -999
    lasty = -999
    Acc = 0.004
    cuts = []

    for line in order_out:
        temp = line
        if temp[0] > temp[1]:
            step = -1
        else:
            step = 1

        loop_old = -1

        for i in range(temp[0], temp[1]+step, step):
            x1 = ecoords[i][0]
            y1 = ecoords[i][1]
            loop = ecoords[i][2]
            # check and see if we need to move to a new discontinuous start point
            if (loop != loop_old):
                dx = x1-lastx
                dy = y1-lasty
                dist = sqrt(dx*dx + dy*dy)
                if dist > Acc:
                    cuts.append([[x1, y1]])
                else:
                    cuts[-1].append([x1, y1])
            else:
                cuts[-1].append([x1, y1])
            lastx = x1
            lasty = y1
            loop_old = loop

    if inside_check:
        #####################################################
        # For each loop determine if other loops are inside #
        #####################################################
        Nloops = len(cuts)
        LoopTree = []
        for iloop in range(Nloops):
            LoopTree.append([])

            ipoly = cuts[iloop]
            ## Check points in other loops (could just check one) ##
            if ipoly != []:
                for jloop in range(Nloops):
                    if jloop != iloop:
                        inside = 0
                        inside = inside + \
                            point_inside_polygon(
                                cuts[jloop][0][0], cuts[jloop][0][1], ipoly)
                        if inside > 0:
                            LoopTree[iloop].append(jloop)
        #####################################################
        for i in range(Nloops):
            lns = []
            lns.append(i)
            remove_self_references(LoopTree, lns, LoopTree[i])

        order = []
        loops = list(range(Nloops))
        for i in range(Nloops):
            if LoopTree[i] != []:
                addlist(LoopTree, order, loops, LoopTree[i])
                LoopTree[i] = []
            if loops[i] != []:
                order.append(loops[i])
                loops[i] = []
    # END inside_check
        ecoords_out = []
        for i in order:
            line = cuts[i]
            for coord in line:
                ecoords_out.append([coord[0], coord[1], i])
    # END inside_check
    else:
        ecoords_out = []
        for i in range(len(cuts)):
            line = cuts[i]
            for coord in line:
                ecoords_out.append([coord[0], coord[1], i])

    return ecoords_out

def remove_self_references(LoopTree, loop_numbers, loops):
    for i in range(0, len(loops)):
        for j in range(0, len(loop_numbers)):
            if loops[i] == loop_numbers[j]:
                loops.pop(i)
                return
        if LoopTree[loops[i]] != []:
            loop_numbers.append(loops[i])
            remove_self_references(
                loop_numbers, LoopTree[loops[i]])

def addlist(LoopTree, order, loops, list):
    for i in list:
        # this try/except is a bad hack fix to a recursion error. It should be fixed properly later.
        try:
            if LoopTree[i] != []:
                # too many recursions here causes cmp error
                addlist(LoopTree, order, loops, LoopTree[i])
                LoopTree[i] = []
        except:
            pass
        if loops[i] != []:
            order.append(loops[i])
            loops[i] = []

def mirror_rotate_vector_coords(coords, design_bounds, design_transform):
    if not design_transform.rotate and not design_transform.mirror:
        return coords.copy()

    xmin = design_bounds.xmin
    xmax = design_bounds.xmax
    coords_rotate_mirror = []

    for i in range(len(coords)):
        coords_rotate_mirror.append(coords[i][:])
        if design_transform.mirror:
            coords_rotate_mirror[i][0] = xmin + xmax-coords_rotate_mirror[i][0]

        if design_transform.rotate:
            x = coords_rotate_mirror[i][0]
            y = coords_rotate_mirror[i][1]
            coords_rotate_mirror[i][0] = -y
            coords_rotate_mirror[i][1] = x

    return coords_rotate_mirror
