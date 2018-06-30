QUALITY_MIN = 1
QUALITY_MAX = 95

from errors import OptionsError


def deserialize(opts):
    parsed = opts

    if 'resolutions' in opts:
        parsed['resolutions'] = parse_resolutions(opts['resolutions'])

    if 'quality' in opts:
        parsed['quality'] = parse_quality(opts['quality'])

    return parsed


def parse_resolutions(resolutions):
    '''Parses and extracts the resolutions to use for resizing each image.

    Args:
        resolutions: A string containing image resolutions.
            The resolution string is expected to have an 'x' used to separate
            the dimensions of each resolution.
            If multiple resolutions are provided, they must be wrapped in a string
            with each resolution separated by a comma.
            
            Examples:
            "800x800"
            "1600x900,1280x1024"

    Returns:
        A list of tuples for each resolution, where each tuple is (width, height).

    Raises:
        ApertureError: An error occurred parsing the resolutions.
    '''
    resolutions_parsed = []
    if resolutions is not None:
        resolutions = resolutions.split(',')
        for res in resolutions:
            try:
                w, h = res.lower().split('x')
                r = (int(w), int(h))
            except ValueError:
                raise OptionsError(
                    'Supplied resolution \'{}\' is not valid. Resolutions must be in form \'<width>x<height>\' and must be comma separated'.
                    format(res))
            else:
                resolutions_parsed.append(r)

    return resolutions_parsed


def parse_quality(quality):
    '''Parses and validate the quality value.
    
    Args:
        quality: A string containing the quality value
    
    Returns:
        An integer containing the parsed quality value
    
    Raises:
        ApertureError: An error occured parsing the quality value.
    '''
    err = 'Supplied quality value \'{}\' is not valid. Quality value must be an integer between 1 and 95'.format(
        quality)

    try:
        quality = int(quality)
    except ValueError:
        raise OptionsError(err)

    if quality not in range(QUALITY_MIN, QUALITY_MAX + 1):
        raise OptionsError(err)

    return quality
