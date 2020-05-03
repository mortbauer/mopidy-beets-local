import logging

from mopidy import backend

import pykka

from .library import BeetsLocalLibraryProvider
from . import SCHEME
from uritools import uricompose, urisplit, uridecode, uriencode

logger = logging.getLogger(__name__)


class BeetsLocalBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super(BeetsLocalBackend, self).__init__()
        self.beetslibrary = config[SCHEME]['beetslibrary']
        self.directories = config[SCHEME]['directories']
        self.use_original_release_date = config[SCHEME][
            'use_original_release_date']
        logger.debug("Got library %s" % (self.beetslibrary))
        self.playback = BeetsLocalPlaybackProvider(audio=audio, backend=self)
        self.library = BeetsLocalLibraryProvider(backend=self)
        self.playlists = None
        self.uri_schemes = [SCHEME]


class BeetsLocalPlaybackProvider(backend.PlaybackProvider):

    def translate_uri(self, uri):
        path = uri.split(':',3)[3]
        local_uri = f'file://{path}'
        logger.debug('translate %s to %s',uri,local_uri)
        return local_uri
