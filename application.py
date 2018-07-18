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
    orig_stream = BytesIO() # For use if file cannot be compressed.
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

        # Save original stream for later if needed
        img_file.save(orig_stream)  

        img_ext = img_file.mimetype.split('image/')[1]
        if '.' + img_ext.lower() not in apt.SUPPORTED_EXTENSIONS:
            err = 'Provided image was invalid!'
            err_ext = ' Image provided through api request was of invalid format ({}). Valid formats are .jpg/.jpeg, .png and .gif.'.format(
                img_ext)
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

        # Get original size (for later)
        img_file.seek(0, os.SEEK_END)
        size_orig = img_file.tell()
        img_file.seek(0, 0)  # reset fp to beginning

        #Max file size is 50MB
        if size_orig > 52428800:
            err = 'Input image too large.'
            err_ext = ' The input image was {} bytes. Max size is 50MB.'.format(size_orig)
            log(err + err_ext, 'ERROR')
            raise ApertureAPIError(err)

        # Check if a watermark image was provided
        if 'watermark' in request.files:
            wmark_img = request.files['watermark']
            if wmark_img:
                # Check that watermark image is valid
                wmrk_ext = '.' + wmark_img.mimetype.split('image/')[1].lower()
                if wmrk_ext not in apt.SUPPORTED_EXTENSIONS:
                    err = 'Watermark image was invalid!'
                    err_ext = ' Watermark image provided through api request was of invalid format ({}). Valid formats are .jpg/.jpeg, .png and .gif.'.format(
                        wmrk_ext)
                    log(err + err_ext, 'ERROR')
                    raise OptionsError(err)
                apt_opts['wmark-img'] = wmark_img

        # Check if watermark text was provided
        if 'watermarkText' in request.form:
            wmark_txt = request.form['watermarkText']
            if wmark_txt:
                apt_opts['wmark-txt'] = wmark_txt

        aperture_results = []
        try:
            aperture_results = apt.format_image(img_file, apt_opts)
        except Exception as e:
            err = 'Error occurred during formatting of image.'
            err_ext = ' Error occurred during execution of aperturelib.format_image.\n'
            err_ext += str(e) + '\n' + traceback.format_exc()
            log(err + err_ext, 'ERROR')
            raise ApertureAPIError(err)

        # Create options to be passed to apt.save
        if 'quality' in apt_opts:
            pil_opts['quality'] = apt_opts['quality']
            qual = pil_opts['quality']
            mode = None
            if len(aperture_results) > 0:
                mode = aperture_results[0].mode

            #Make sure we at least try to compress all files types
            img_format = img_ext.upper()
            if img_format in ['JPG', 'JPEG']:
                if qual <= 60:
                    pil_opts['optimize'] = True
            elif img_format == 'PNG' and mode not in ['P', 'L']:
                '''
                'quality' values from 1-95 will map to compress_level values between 1 and 9. 
                all values of 'quality' below 47 will map to maximum compression (9). This is because
                this compression doesn't actually degrade image quality, even though the quality
                attribute for .jpg images does. Because of this, users are more likely to provide 
                higher quality levels than lower ones, but we still want them to get a good level 
                of compression with their .png images.
                ---------------------------
                0-46    = 9     71-76   = 4
                47-52   = 8     77-82   = 3
                53-58   = 7     83-88   = 2
                59-64   = 6     89-95   = 1
                65-70   = 5
                ---------------------------
                '''
                comp_lvl = 10 - int((((qual + 5) - 40) / 6))
                if comp_lvl == 0:
                    comp_lvl = 1
                elif comp_lvl > 9:
                    comp_lvl = 9
                pil_opts['compress_level'] = comp_lvl
                #If input image was PNG and desired quality was <=20, convert to palette image
                if qual <= 20:
                    #Degrades image quality but decreases file size dramatically
                    for i in range(len(aperture_results)):
                        aperture_results[i] = aperture_results[i].convert('P', palette=1, colors=256)
            elif img_format in ['PNG', 'GIF']:
                # NOTE:
                # Only single frame Gif's will be handled. Animated Gif's will only have
                #  their first frame saved

                # TODO:
                #Single frame gif's can be compressed a lot if converted to jpg... maybe we can ask
                # users if they want to allow gifs to be converted for more compression?
                #if img_format == 'GIF':
                #   image = image.convert('RGB')
                #   #Would need to ensure filetype changes to match
                '''
                Not sure why this works, but converting palette images to RGB
                and then back to palette helps compress them much better than
                just trying to save the palette image
                '''
                was_P = mode == 'P'
                was_L = mode == 'L'

                for i in range(len(aperture_results)):
                    image = aperture_results[i]

                    #Size of original palette
                    if was_P:
                        cols = int(len(image.getpalette()) / 3)

                    if mode not in ['RGB', 'RGBA']:
                        image = image.convert('RGBA')

                    if was_P:
                        image = image.convert('P', palette=1, colors=cols)
                    elif was_L:
                        image = image.convert('L')

                    aperture_results[i] = image #for some reason, changes don't take effect unless we do this

                #.gif images are always 'P' or 'L' mode.
                #For palette images, just compress as much as possible always
                pil_opts['optimize'] = True

        response_images = []
        for i, image in enumerate(aperture_results):
            try:
                req_res = None
                if 'resolutions' in apt_opts and i < len(
                        apt_opts['resolutions']):
                    req_res = apt_opts['resolutions'][i]
                response_images.append(
                    get_response_for_image(image, req_res, size_orig, img_ext, orig_stream,
                                        ('wmark-txt' not in apt_opts and 'wmark-img' not in apt_opts and 'resolutions' not in apt_opts),
                                        **pil_opts))
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
        resp.status_code = 400  # Bad Request Error. This will update resp.status as well
        return resp

    finally:
        #Always close this
        orig_stream.truncate(0)
        orig_stream.close()

def get_response_for_image(image, req_res, size, ext, orig_stream, can_replace, **kwargs):
    stream = BytesIO()
    apt.save(image, stream, format=ext, **kwargs)
    size_new = stream.getbuffer().nbytes

    str_b64 = None
    #If file was not modified except for attempted compression and
    # output file is larger than input file, replace output file with
    # input file.
    if can_replace and size_new > size:
        size_new = orig_stream.getbuffer().nbytes
        str_b64 = base64.b64encode(orig_stream.getvalue()).decode()
    else:
        # Convert to base64 string
        str_b64 = base64.b64encode(stream.getvalue()).decode()

    # Close the stream
    stream.truncate(0)
    stream.close()

    if req_res:
        return {
            'image': str_b64,
            'meta': {
                'resolution': {
                    'requested': req_res,
                    'actual': image.size
                },
                'size': {
                    'before': size,
                    'after': size_new
                }
            }
        }
    else:
        return {
            'image': str_b64,
            'meta': {
                'size': {
                    'before': size,
                    'after': size_new
                }
            }
        }


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