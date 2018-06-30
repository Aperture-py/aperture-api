import os
import base64
import json
from io import BytesIO
import aperturelib as apt
from flask import Flask, jsonify, request, json
from flask_cors import cross_origin
import options as req_opts
from errors import OptionsError, ApertureAPIError
import traceback

application = Flask(__name__)


@application.route('/')
def index():
    return jsonify(success=True, message='hello world!')


@application.route('/aperture', methods=['POST', 'OPTIONS'])
@cross_origin(allow_headers=['Content-Type'], methods=['POST', 'OPTIONS'])
def aperture():
    try:
        # Get the image file and it's extension & error check
        img_file = None
        if 'image' in request.files:
            img_file = request.files['image']
        if not img_file:
            err = 'No input image was provided!'
            err_ext = ' Either the api request did not contain an image, or the image could not be read.'
            log(err + err_ext, 'ERROR')
            raise OptionsError(err)

        img_ext = img_file.mimetype.split('image/')[1]
        if '.' + img_ext.lower() not in apt.SUPPORTED_EXTENSIONS:
            err = 'Provided image was invalid!'
            err_ext = ' Image provided through api request was of invalid format ({}). Valid formats are .jpg/.jpeg, .png and .gif.'.format(img_ext)
            log(err + err_ext, 'ERROR')
            raise OptionsError(err)

        apt_opts = {}
        pil_opts = {}

        # Error check the provided quality
        qual = None
        if 'quality' in request.form:
            qual = request.form['quality']
        if not qual:
            err = "No quality value provided!"
            err_ext = ' API request did not contain a quality value. A compression/quality value must be provided!'
            log(err + err_ext, 'ERROR')
            raise OptionsError(err)
        else:
            apt_opts['quality'] = qual

        # Check for resolutions. Don't need to error if it doesn't exist, b/c it's not required
        if 'resolutions' in request.form:
            res = request.form['resolutions']
            if res:
                apt_opts['resolutions'] = res
        
        # Parse options (quality and resolutions)
        try:
            apt_opts = req_opts.deserialize(apt_opts)
        except Exception as e:
            err = 'Could not parse options!'
            err_ext = ' Error occurred during parsing of aperture options.\n'
            err_ext += str(e)
            log(err + err_ext, 'ERROR')
            raise ApertureAPIError(err)

        # Create options to be passed to apt.save (just quality for now)
        # TODO: Maybe copy compression logic from CLI into here?
        if 'quality' in apt_opts:
            pil_opts['quality'] = apt_opts['quality']
            # pil_opts['optimize'] = apt_opts['optimize']
            # ...

        # Check if a watermark image was provided
        if 'watermark' in request.files:
            wmark_img = request.files['watermark']
            if wmark_img:
                # Check that watermark image is valid
                wmrk_ext = '.' + wmark_img.mimetype.split('image/')[1].lower()
                if wmrk_ext not in apt.SUPPORTED_EXTENSIONS:
                    err = 'Watermark image was invalid!'
                    err_ext = ' Watermark image provided through api request was of invalid format ({}). Valid formats are .jpg/.jpeg, .png and .gif.'.format(wmrk_ext)
                    log(err + err_ext, 'ERROR')
                    raise OptionsError(err)
                apt_opts['wmark-img'] = wmark_img

        # Check if watermark text was provided
        if 'watermarkText' in request.form:
            wmark_txt = request.form['watermarkText']
            if wmark_txt:
                apt_opts['wmark-txt'] = wmark_txt

        # Get original size
        img_file.seek(0, os.SEEK_END)
        size_orig = img_file.tell()
        img_file.seek(0, 0)  # reset fp to beginning

        aperture_results = []
        try:
            aperture_results = apt.format_image(img_file, apt_opts)
        except Exception as e:
            err = 'Error occurred during formatting of image.'
            err_ext = ' Error occurred during execution of aperturelib.format_image.\n'
            err_ext += str(e) + '\n' + traceback.format_exc()
            log(err + err_ext, 'ERROR')
            raise ApertureAPIError(err)
            
        response_images = []

        for i,image in enumerate(aperture_results):
            try:
                req_res = None
                if 'resolutions' in apt_opts and i < len(apt_opts['resolutions']):
                    req_res = apt_opts['resolutions'][i]
                response_images.append(get_response_for_image(image, req_res, size_orig, img_ext, **pil_opts))
            except Exception as e:
                err = 'Error occurred during compression of image.'
                err_ext = ' Error occurred during execution of application.get_response_for_image. This most likely occurred during execution of base64.b64encode or apreturelib.save.\n'
                err_ext += str(e) + '\n' + traceback.format_exc()
                log(err + err_ext, 'ERROR')
                raise ApertureAPIError(err)   

        # If here, success!
        if len(response_images) > 1:
            return jsonify(images=response_images, success=True)
        elif len(response_images) == 1:
            resp = response_images[0]
            resp['success'] = True
            return jsonify(resp)
        else:
            #Shouldn't ever happen...
            err = 'Error occurred during image formatting.'
            err_ext = ' There was a problem formatting/saving images. No data was returned from application.get_response_for_image.'
            log(err + err_ext, 'ERROR')
            raise ApertureAPIError(err)    

    except Exception as e:
        # Detailed error has already been logged. Just return simple error msg to client.
        # Create error response:
        '''
        TODO: (Maybe) allow for multiple errors to make their way here. This
        might be a bad idea because that would require continuing through portions 
        of the image formatting process after errors have been encountered...
        For now, just come here each time an error is encountered and log it by itself
        '''
        errs = [{'message': str(e)}]
        resp = jsonify(errors=errs, success=False)
        resp.status_code = 400 # Bad Request Error. This will update resp.status as well
        return resp


def get_response_for_image(image, req_res, size, ext, **kwargs):
    stream = BytesIO()
    apt.save(image, stream, format=ext, **kwargs)
    size_new = stream.getbuffer().nbytes

    # Convert to base64 string
    str_b64 = base64.b64encode(stream.getvalue()).decode()
    str_web_b64 = 'data:image/' + ext + ';base64,' + str_b64

    # Close the stream
    stream.truncate(0)
    stream.close()

    if req_res:
        return {'image': str_web_b64, 'meta': {'resolution': {'requested': req_res, 'actual': image.size}, 'size': {'before': size, 'after': size_new}}}
    else:
        return {'image': str_web_b64, 'meta': {'size': {'before': size, 'after': size_new}}}

def log(msg, level):
    level = level.upper()
    if level == "ERROR":
        print("ERROR: " + msg)
    elif level == "WARN":
        print("WARNING: " + msg)
    else:
        print(msg)


if __name__ == '__main__':
    application.run(debug=True)