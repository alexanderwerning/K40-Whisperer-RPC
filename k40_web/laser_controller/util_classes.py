from k40_web.laser_controller.ecoords import ECoord


class Vector():
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def aslist(self):
        return [self.x, self.y]


class Position(Vector):
    pass


class Dimensions(Vector):
    pass


class Scale():
    def __init__(self, x, y, r=0):
        self.x = x
        self.y = y
        self.r = r

    def aslist(self):
        return [self.x, self.y, self.r]


class DesignTransform():
    def __init__(self, scale=1.0, rotate=False, mirror=False, negate=False, halftone=False, ht_size=500):
        self.scale = scale
        self.rotate = rotate
        self.mirror = mirror
        self.negate = negate
        self.halftone = halftone
        self.ht_size = ht_size


class BezierSettings():
    def __init__(self, weight, m1, m2):
        self.weight = weight
        self.m1 = m1
        self.m2 = m2


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


class DesignBounds():
    def __init__(self, xmin=0, xmax=0, ymin=0, ymax=0):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    @property
    def bounds(self):
        return self.xmin, self.xmax, self.ymin, self.ymax

    def rotate(self):
        self.xmin, self.ymin = self.ymin, self.xmin
        self.xmax, self.ymax = self.ymax, self.xmax
        return self
    
    def contains(self, other, margin=0):
        return (self.xmin < other.xmin+margin and
                self.xmax > other.xmax-margin and
                self.ymin < other.ymin+margin and
                self.ymax > other.ymax-margin)
    def from_tuple(tuple):
        assert len(tuple) == 4
        return DesignBounds(*tuple)


class Design():
    def __init__(self, RengData=ECoord(), VengData=ECoord(), VcutData=ECoord(), GcodeData=ECoord(), bounds=DesignBounds()):
        self.RengData = RengData
        self.VengData = VengData
        self.VcutData = VcutData
        self.GcodeData = GcodeData
        self.bounds = bounds
    
    def reset(self):
        self.RengData = ECoord()
        self.VengData = ECoord()
        self.VcutData = ECoord()
        self.GcodeData = ECoord()
        self.bounds = DesignBounds(0, 0, 0, 0)
