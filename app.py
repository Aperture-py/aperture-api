import base64
import re
from io import BytesIO
from PIL import Image
from flask import Flask, jsonify, request, Response, make_response
from flask_cors import cross_origin
app = Flask(__name__)


@app.route('/')
def index():
    resp = make_response(jsonify('hello world!'))
    return resp


@app.route('/aperture', methods=['POST', 'OPTIONS'])
@cross_origin(allow_headers=['Content-Type'], methods=['POST', 'OPTIONS'])
def aperture():
    if request.is_json:
        data = request.get_json(cache=False)
        image_data = data['image']

        # Get first occurence of image meta data, need this for later (example: data:image/jpeg:base64)
        meta = re.search('^data:image/.+;base64,', image_data).group()
        f_type = meta.split('/')[1].split(';')[0]
        # only replace the first occurence, since that's all there should be (if not then it's malformed)
        image_data_raw = image_data.replace(meta, '', 1)
        # convert the base64 string to bytes
        encoded_b64 = bytes(image_data_raw, 'utf-8')
        # decode it
        stream_orig = BytesIO(base64.b64decode(encoded_b64))
        size_orig = stream_orig.getbuffer().nbytes
        img = Image.open(stream_orig)

        stream_new = BytesIO()
        img.save(stream_new, format=f_type, quality=20)
        size_new = stream_new.getbuffer().nbytes
        img = Image.open(stream_new)

        str_b64 = base64.b64encode(stream_new.getvalue()).decode()
        str_web_b64 = meta + str_b64

        stream_new.truncate(0)
        stream_new.close()

        res_data = jsonify(
            success=True,
            image=str_web_b64,
            size={
                'before': size_orig,
                'after': size_new
            })

        return res_data
    return jsonify(success=False)


if __name__ == '__main__':
    app.run(debug=True)