from django.conf import settings

def ssl_media(request):
    """
    changes MEDIA_URL to https if using SSL connection
    """
    media_url = settings.MEDIA_URL
    parts = media_url.split(':')

    protocol = 'https' if request.is_secure() else 'http'
    new_media_url = f"{protocol}:" + ":".join(parts[1:])
    return {'MEDIA_URL': new_media_url}
