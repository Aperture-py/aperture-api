import os
import base64

from io import BytesIO
from PIL import Image

from flask import Flask, jsonify, request, Response, make_response, send_file
from flask_cors import cross_origin

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

    # Get original size
    img_file.seek(0, os.SEEK_END)
    size_orig = img_file.tell()
    img_file.seek(0, 0)  # reset fp to beginning

    img = Image.open(img_file)
    img_stream = BytesIO()
    img.save(img_stream, format=img_ext, quality=20)

    # Get new size
    size_new = img_stream.getbuffer().nbytes

    # Get base64 string for web client
    str_b64 = base64.b64encode(img_stream.getvalue()).decode()
    str_web_b64 = 'data:image/' + img_ext + ';base64,' + str_b64

    # Close the stream
    img_stream.truncate(0)
    img_stream.close()

    res_data = jsonify(
        success=True,
        image=str_web_b64,
        size={
            'before': size_orig,
            'after': size_new
        })

    return res_data


if __name__ == '__main__':
    application.run(debug=True)