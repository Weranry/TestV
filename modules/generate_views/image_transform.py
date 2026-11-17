#图像旋转
def rotate_image(img, angle):
    if angle and angle != 0:
        return img.rotate(angle, expand=True)
    return img

#图像反色
def invert_image(img):
    return img.point(lambda x: 255 - x)
