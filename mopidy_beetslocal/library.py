from __future__ import unicode_literals

import datetime
import logging
import os
import sqlite3
import sys

from mopidy import backend
from mopidy.exceptions import ExtensionError
from mopidy.models import Album, Artist, Ref, SearchResult, Track, Image

from uritools import uricompose, urisplit, uridecode

import beets.library
from . import SCHEME

logger = logging.getLogger(__name__)


class ItemAdapter:

    @classmethod
    def get_date(self,item):
        return f'{item.year}-{item.month:02}-{item.day:02}'

    @classmethod
    def get_artist(self,item:beets.library.Item):
        uri = uricompose(
            scheme=SCHEME,
            path=f'artist:{item.mb_artistid}',
        )
        return Artist(
                uri=uri,
                name=item.artist,
                sortname=item.artist_sort,
                musicbrainz_id=item.mb_artistid,
            )
        
    @classmethod
    def get_albumartist(self,item):
        uri = uricompose(
            scheme=SCHEME,
            path=f'artist:{item.mb_albumartistid}',
        )
        return Artist(
                uri=uri,
                name=item.albumartist,
                sortname=item.albumartist_sort,
                musicbrainz_id=item.mb_albumartistid,
            )

    @classmethod
    def get_album(self,item:beets.library.Item):
        album = item.get_album()
        return self.get_album_from_album(album)

    @classmethod
    def get_album_from_album(self,album:beets.library.Album):
        uri = uricompose(
            scheme=SCHEME,
            path=f'album:{album.id}',
        )
        return Album(
                uri=uri,
                name=album.album,
                artists=[self.get_albumartist(album)],
                num_tracks=album.albumtotal,
                num_discs=album.disctotal,
                date=self.get_date(album),
                musicbrainz_id=album.mb_albumid,
            )

    @classmethod
    def get_track(self,item):
        path = item.path.decode('utf-8')
        uri = uricompose(
            scheme=SCHEME,
            path=f'track:{item.id}:{path}',
        )
        return Track(
                uri=uri,
                name=item.title,
                artists=[self.get_artist(item)],
                album=self.get_album(item),
                # composers=
                # performers=
                genre=item.genre,
                track_no=item.track,
                disc_no=item.disc,
                date=self.get_date(item),
                length=int(item.length),
                bitrate=item.bitrate,
                comment=item.comments,
                musicbrainz_id=item.mb_trackid,
                last_modified=int(item.mtime),
            )


class BeetsLocalLibraryProvider(backend.LibraryProvider):

    ROOT_KEY = f"{SCHEME}:directory"

    def __init__(self, *args, **kwargs):
        super(BeetsLocalLibraryProvider, self).__init__(*args, **kwargs)
        self._directories = []
        self.root_directory = Ref.directory(uri=self.ROOT_KEY, name='Local(Beets)')
        for line in self.backend.directories:
            name, uri = line.rsplit(None, 1)
            ref = Ref.directory(uri=uri, name=name)
            self._directories.append(ref)
        if not os.path.isfile(self.backend.beetslibrary):
            raise ExtensionError('Can not find %s' % self.backend.beetslibrary)
        try:
            self.lib = beets.library.Library(self.backend.beetslibrary)
        except sqlite3.OperationalError as e:
            logger.error('BeetsLocalBackend: %s', err)
            raise ExtensionError('Mopidy-BeetsLocal can not open %s'%self.backend.beetslibrary)
        except sqlite3.DatabaseError as err:
            logger.error('BeetsLocalBackend: %s', err)
            raise ExtensionError('Moidy-BeetsLocal can not open %s'%self.backend.beetslibrary)
        logger.info('Loaded beetslibrary %s',self.backend.beetslibrary)

    
    def search(self, query=None, uris=None, exact=False):
        logger.debug(u'Search query: %s in uris: %s, exact: %s',query, uris, exact)
        if exact:
            try:
                logger.error('Not implemented')
            except:
                logger.exception('aaaaa')
        albums = []
        if not query:
            uri = 'beetslocal:search-all'
            tracks = self.lib.items()
            albums = self.lib.albums()
        else:
            uri = uricompose(
                    scheme=SCHEME,
                     path='search',
                     query=query,
                )
            track_query = self._build_beets_track_query(query)
            logger.debug('query items with "%s":',track_query)
            tracks = self.lib.items(track_query)
            if 'track_name' not in query:
                # when trackname queried dont search for albums
                album_query = self._build_beets_album_query(query)
                logger.debug('Build Query "%s":' % album_query)
                albums = self.lib.albums(album_query)
        logger.debug(u"Query found %s tracks and %s albums"
                     % (len(tracks), len(albums)))
        return SearchResult(
            uri=uri,
            tracks=[ItemAdapter.get_track(track) for track in tracks],
            albums=[ItemAdapter.get_album_from_album(album) for album in albums]
        )

    def browse(self, uri):
        uriparts = urisplit(uridecode(uri))
        try:
            if uriparts.path == 'directory':
                if uriparts.query is None:
                    res = self._directories
                else:
                    res = self._browse_directory(uriparts.getquerydict())
            elif uriparts.path == "artist":
                res = self._browse_artist(uri)
            elif uriparts.path.startswith("album:"):
                res = self._browse_album(uriparts.path.split(':')[1])
            else:
                raise ValueError("Invalid browse URI")
        except Exception as e:
            logger.exception("Error browsing %s: %s", uri, e)
            res = []
        logger.debug('Browse %s got %s',uri,res)
        return res

    def _browse_album(self,album):
        results = []
        for track in self.get_album_items(album):
            path = track.path.decode('utf-8')
            results.append(Ref.track(
                uri=uricompose(
                    scheme=SCHEME,
                    path=f'track:{track.id}:{path}',
                ),
                name=track.title,
                )
            )
        return results

    def _browse_generic_album_container(self,iterator,key,default):
        results = []
        for row in iterator:
            results.append(Ref.directory(
                uri=uricompose(
                    scheme=SCHEME,
                    path='directory',
                    query={'type':'album',key:str(row[0])},
                    ),
                name=str(row[0]) if row[0] else default,
                )
            )
        return results

    def _browse_directory(self,querydict):
        query_type = querydict.pop('type')[0]
        results = []
        if query_type == 'album':
            query = self._build_beets_album_query(self._sanitize_query(querydict=querydict))
            for album in self.get_albums(query):
                results.append(Ref.album(
                    uri=uricompose(
                        scheme=SCHEME,
                        path=f'album:{album.id}',
                    ),
                    name=album.album,
                    )
                )
        elif query_type == 'track':
            results = self._browse_album(querydict.get('album')[0])
        elif query_type == 'genre':
            results = self._browse_generic_album_container(self.get_genres(),key='genre',default='No Genre')
        elif query_type == 'artist':
            results = self._browse_generic_album_container(self.get_artists(),key='artist',default='No Atist')
        elif query_type == 'date':
            results = self._browse_generic_album_container(self.get_release_years(),key='year',default='No Year')
        logger.debug('browse directory %s got %s',dict(querydict),results)
        return results

    def lookup(self,uri):
        parts = uri.split(':')
        item_type = parts[1]
        item_id = parts[2]
        if item_type == 'track':
            tracks = [ItemAdapter.get_track(self.lib.get_item(int(item_id)))]
        elif item_type == 'album':
            album = self.lib.get_album(int(item_id))
            tracks = [ItemAdapter.get_track(item) for item in album.items()]
        else:
            tracks = []
        logger.debug('lookup result for %s is %s',uri,tracks)
        return tracks

    def get_distinct_disabled(self, field, query=None):
        """ not really needed for mopidy """
        logger.warn(u'get_distinct called field: %s, Query: %s',field,query)
        query = self._sanitize_query(query)
        logger.debug(u'Search sanitized query: %s ',query)
        result = []
        if field == 'artist':
            result = self._browse_artist(query)
        elif field == 'genre':
            result = self.get_genres()
        else:
            logger.info(u'get_distinct not fully implemented yet')
            result = []
        return set([v[0] for v in result])

    def _browse_track(self, query):
        return self.lib.items('album_id:\'%s\'' % query['album'][0])

    def get_genres(self):
        return self._query_beets_db('select Distinct genre '
                                    'from albums order by genre')

    def get_artists(self):
        return self._query_beets_db('select Distinct albumartist '
                                    'from albums order by albumartist')

    def get_release_years(self):
        return self._query_beets_db('select Distinct year '
                                    'from albums order by year')

    def get_album_items(self,album_id):
        return self.lib.get_album(int(album_id)).items()

    def get_albums(self,query):
        return self.lib.albums(query)

    def _query_beets_db(self, statement):
        result = []
        logger.debug('query %s',statement)
        with self.lib.transaction() as tx:
            try:
                result = tx.query(statement)
            except Exception:
                # import pdb; pdb.set_trace()
                logger.error('Statement failed: %s', statement)
        return result

    def _sanitize_query(self, uri=None, querydict=None):
        """
        We want a consistent query structure that later code
        can rely on
        """
        # import pdb; pdb.set_trace()
        if querydict is None:
            query = urisplit(uri).getquerydict()
        else:
            query = querydict
        result = {}
        for (key, values) in query.items():
            logger.debug('sanitize_query 1 %s:%s',key,values)
            result_values = []
            for value in values:
                if key == 'date':
                    year = self._sanitize_year(str(value))
                    if year:
                        result_values.append(year)
                    # we possibly could introduce query['year'],
                    # query['month'] etc.
                    # Maybe later
                elif value:
                    result_values.append(value)
            if result_values:
                result[key] = result_values
        return result

    def _sanitize_year(self, datestr):
        """
        Clients may send date field as Date String, Year or Zero
        """
        try:
            year = str(datetime.datetime.strptime(datestr, '%Y').date().year)
        except:
            try:
                year = str(datetime.datetime.strptime(datestr,
                                                      '%Y-%m-%d').date().year)
            except:
                year = None
        return year

    def _build_statement(self, query, query_key, beets_key):
        """
        A proper mopidy query has a Array of values
        Queries from mpd and browse requests hav strings
        """
        statement = ""
        if query_key in query:
            for query_string in query[query_key]:
                if '"' in query_string:
                    statement += " and %s = \'%s\' " % (beets_key,
                                                        query_string)
                else:
                    statement += ' and %s = \"%s\" ' % (beets_key,
                                                        query_string)
        return statement

    def _build_date(self, year, month, day):
        month = 1 if month == 0 else month
        day = 1 if day == 0 else day
        try:
            d = datetime.datetime(
                year,
                month,
                day)
            date = '{:%Y-%m-%d}'.format(d)
        except:
            date = None
        return date

        
    def _build_beets_track_query(self, query):
        """
        Transforms a mopidy query into beets
        query syntax
        """
        beets_query = []
        for key in query.keys():
            if key != 'any':
                if key == 'track_name':
                    name = 'title'
                else:
                    name = key
                beets_query.append('{}:{}'.format(name," ".join(query[key])))
            else:
                beets_query.append(" ".join(query[key]))
            # beets_query += "::(" + "|".join(query[key]) + ") "
        beets_query = ' '.join(beets_query)
        logger.info('from %s constructed beets query %s',query,beets_query)
        return beets_query

    def _build_beets_album_query(self, query):
        """
        Transforms a mopidy query into beets
        query syntax
        """
        beets_query = ""
        for key in query.keys():
            if key != 'any':
                if key == 'artist':
                    beets_query += 'albumartist'
                else:
                    beets_query += key
            beets_query += ":" + " ".join(query[key]) + " "
        logger.info('from %s constructed beets_album_query %s',query,beets_query)
        return '\'%s\'' % beets_query.strip()

    def get_images(self,uris):
        logger.warning('Want images for %s',uris)
        images = {}
        for uri in uris:
            parts = uri.split(':')
            if len(parts) >= 3:
                query_type = parts[1]
                item_id = parts[2]
                album = None
                if query_type == 'album':
                    album = self.lib.get_album(int(item_id))
                elif query_type == 'track':
                    album = self.lib.get_item(int(item_id)).get_album()
                if album is not None and album.artpath is not None:
                    image_path = album.artpath.decode('utf-8')
                    images[uri] =  [
                            Image(
                                uri=f'/{SCHEME}{image_path}'),
                        ]
        return images
