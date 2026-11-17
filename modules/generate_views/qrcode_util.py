import qrcode

#二维码生成
def generate_qrcode(data, box_size=10, border=2, fill_color=0, back_color=255):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    # 转为L模式，方便paste到P模式画布
    if img.mode != 'L':
        img = img.convert('L')
    return img
