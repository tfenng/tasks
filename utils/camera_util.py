import math
import numpy as np

# 弧度制转换为角度制
def radians_to_degrees(radians):
    degrees = math.degrees(radians)
    return degrees
def euler_from_quaternion(w, x, y, z):
    """
    将四元数转换为欧拉角（滚转、俯仰、偏航）
    yaw偏航是绕z轴的弧度旋转（逆时针）
    pitch俯仰是绕y轴的弧度旋转（逆时针）
    roll滚转是绕x轴的弧度旋转（逆时针）
    """
    """
    Convert quaternion to Euler angles (in radians).
    q should be a tuple/list of 4 values (w, x, y, z).
    """
    # roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2, sinp)  # use 90 degrees if out of range
    else:
        pitch = math.asin(sinp)

        # yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return  math.degrees(roll),  math.degrees(pitch), math.degrees(yaw)







##
# omega,phi,kappa <-> heading(yaw),pitch,roll
##
def convert_opk_to_ypr(omega, phi, kappa):
    return kappa, omega, phi


if __name__ == '__main__':
    yaw,pitch,roll=euler_from_quaternion(0.7071067811865476, 0, 0, 0.7071067811865475)
    print(yaw,pitch,roll)
