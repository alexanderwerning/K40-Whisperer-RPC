
from k40_web.laser_controller.interpolate import interpolate
from k40_web.laser_controller.utils import generate_bezier

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