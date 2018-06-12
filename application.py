import os
import base64
import json
from io import BytesIO
import aperturelib as apt
from flask import Flask, jsonify, request, json
from flask_cors import cross_origin
import options as req_opts

application = Flask(__name__)


@application.route('/')
def index():
    return jsonify(success=True, message='hello world!')


@application.route('/aperture', methods=['POST', 'OPTIONS'])
@cross_origin(allow_headers=['Content-Type'], methods=['POST', 'OPTIONS'])
def aperture():
    # Get the image file and it's extension
    img_file = request.files['image']
    img_ext = img_file.mimetype.split('image/')[1]

    apt_opts = {}
    pil_opts = {}
    if 'options' in request.form:
        apt_opts = json.loads(request.form['options'])
        apt_opts = req_opts.deserialize(apt_opts)
        pil_opts = {
            'quality': apt_opts['quality'],
            'optimize': apt_opts['optimize']
        }

    if 'watermark' in request.files:
        apt_opts['wmark-img'] = request.files['watermark']

    # Get original size
    img_file.seek(0, os.SEEK_END)
    size_orig = img_file.tell()
    img_file.seek(0, 0)  # reset fp to beginning

    aperture_results = apt.format_image(img_file, apt_opts)
    response_images = []

    for image in aperture_results:
        response_images.append(
            get_response_for_image(image, size_orig, img_ext, **pil_opts))

    return jsonify(success=True, images=response_images)


def get_response_for_image(image, size, ext, **kwargs):
    stream = BytesIO()
    apt.save(image, stream, format=ext, **kwargs)
    size_new = stream.getbuffer().nbytes

    # Convert to base64 string
    str_b64 = base64.b64encode(stream.getvalue()).decode()
    str_web_b64 = 'data:image/' + ext + ';base64,' + str_b64

    # Close the stream
    stream.truncate(0)
    stream.close()

    return {'image': str_web_b64, 'size': {'before': size, 'after': size_new}}


if __name__ == '__main__':
    application.run(debug=True)