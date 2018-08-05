import unittest
from io import BytesIO
import base64
import re as re
from application import application
import aperturelib as apt


class ImageDiffTest(unittest.TestCase):
    '''Test if an image formatted by aperturelib locally produces
    an IDENTICAL image size if the image is sent across the web and back.

    This test is needed as the resultant image sent back by the web API
    is a base64 encoded string, in which base64 encoding can apparently
    make file sizes roughly 33% larger: https://www.davidbcalhoun.com/2011/when-to-base64-encode-images-and-when-not-to/

    Results thus far:
        - Image sizes are exactly the same when formatted locally, or on the web
        api and sent back to the client.

        - This was tested using options, such as quality and optimization, but
        the structure of the anticipated request has now changed (still trying
        to figure out how to get it to send both the file and formatting options
        in the same request form within the test, as that does work in browser).
    '''

    def setUp(self):
        application.config['TESTING'] = True
        client = application.test_client()
        self.client = client

    def test_diff(self):
        # This image is under Creative Commons CC0 License
        img_path = 'tests/images/puma_1920_1524.jpg'
        img = open(img_path, 'rb')
        files = {'image': (BytesIO(img.read()), 'ok.jpg')}
        img.close()

        # TODO: Figure out how to send an options hash in form data separate of the file
        # options = {'quality': 75, 'optimize': True}

        res = self.client.post('/aperture', data=files)

        img_b64_web = res.json['images'][0]['image']
        img_b64_raw = re.sub('^data:image/.+;base64,', '', img_b64_web)

        stream_web = BytesIO(base64.b64decode(img_b64_raw))
        size_from_web = stream_web.getbuffer().nbytes

        apt_img = apt.open(img_path)
        stream_apt = BytesIO()
        # TODO: Use dynamic options
        apt.save(apt_img, stream_apt, format='jpeg')

        size_from_apt = stream_apt.getbuffer().nbytes

        self.assertEqual(
            size_from_web, size_from_apt,
            'final image sizes the same from both web and locally run aperture')