from __future__ import unicode_literals

import logging
import os

from mopidy import config, ext

__version__ = '0.0.9'

logger = logging.getLogger(__name__)

SCHEME = 'beetslocal'

class Extension(ext.Extension):
    dist_name = 'Mopidy-BeetsLocal'
    ext_name = SCHEME
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['beetslibrary'] = config.Path()
        schema['use_original_release_date'] = config.Boolean(optional=True)
        schema['directories'] = config.List(optional=True)
        return schema

    def setup(self, registry):
        from .actor import BeetsLocalBackend
        registry.add('backend', BeetsLocalBackend)
        registry.add("http:app", {"name": self.ext_name, "factory": self.webapp})

    def webapp(self, config, core):
        from .web import ImageHandler, IndexHandler

        return [
            # (r"/(index.html)?", IndexHandler, {"root": image_dir}),
            (r"/((.+)(?:jpg|png)$)", ImageHandler, {"path": '/'}),
        ]

