from os import mkdir
from os.path import join,exists,splitext
import io
from google.cloud import storage
from google.cloud.storage import Blob
from PIL import Image,ImageDraw
from json import loads,dumps
from uuid import uuid1
from datetime import datetime,timezone
from threading import Thread

from src.logger import get_logger
logger = get_logger(__name__)

import sys
from src.credentials_loader import load_service_account_info
service_account_info = load_service_account_info()
sys.path.append('infnotebook')
from define import define
from result import Result

BUCKET_NAMES = {
    'informations': 'bucket-inf-notebook-informations',
    'details': 'bucket-inf-notebook-details',
    'musicselect': 'bucket-inf-notebook-musicselect',
    'resources': 'bucket-inf-notebook-resources2',
    'discordwebhooks': 'bucket-inf-notebook-discordwebhook',
}

informations_dirname = 'informations'
details_dirname = 'details'
musicselect_dirname = 'musicselect'

result_rivalname_fillbox = (
    (
        define.details_graphtarget_name_area[0],
        define.details_graphtarget_name_area[1]
    ),
    (
        define.details_graphtarget_name_area[2],
        define.details_graphtarget_name_area[3]
    )
)

musicselect_rivals_fillbox = (
    (
        define.musicselect_rivals_name_area[0],
        define.musicselect_rivals_name_area[1],
    ),
    (
        define.musicselect_rivals_name_area[2],
        define.musicselect_rivals_name_area[3]
    )

)

class StorageAccessor():
    client = None
    blob_musics = None

    def __init__(self):
        self._buckets = {}

    def connect_client(self):
        if self.client is not None:
            return

        if service_account_info is None:
            logger.info('no define service_account_info')
            return

        self.client = storage.Client.from_service_account_info(service_account_info)
        logger.debug('connect client')

    def _get_bucket(self, name: str):
        """バケットを取得し、未接続なら接続する"""
        if name in self._buckets and self._buckets[name] is not None:
            return self._buckets[name]

        if self.client is None:
            self.connect_client()
        if self.client is None:
            return None

        try:
            self._buckets[name] = self.client.get_bucket(BUCKET_NAMES[name])
            logger.debug(f'connect bucket {name}')
        except Exception as ex:
            logger.exception(ex)
            return None

        return self._buckets[name]

    def _upload_image_to_bucket(self, bucket_name: str, object_name: str, image):
        """指定バケットに画像をアップロードする"""
        bucket = self._get_bucket(bucket_name)
        if bucket is None:
            return

        try:
            blob = bucket.blob(object_name)
            self.upload_image(blob, image)
            logger.debug(f'upload {bucket_name} image {object_name}')
        except Exception as ex:
            logger.exception(ex)

    def upload_image(self, blob, image):
        bytes = io.BytesIO()
        image.save(bytes, 'PNG')
        blob.upload_from_file(bytes, True)
        bytes.close()

    def start_uploadcollection(self, result: Result, image: Image.Image, force: bool):
        '''収集画像をアップロードする

        Args:
            result (Result): 対象のリザルト(result.py)
            image (Image): 対象のリザルト画像(PIL.Image)
            force (bool): 強制アップロード

        Returns:
            bool, bool: informationsをアップロードした、detailsをアップロードした
        '''
        self.connect_client()
        if self.client is None:
            return

        object_name = f'{uuid1()}.png'

        informations_trim = force
        details_trim = force

        if result.informations is None:
            informations_trim = True
        else:
            if result.informations.play_mode is None:
                informations_trim = True
            if result.informations.difficulty is None:
                informations_trim = True
            if result.informations.level is None:
                informations_trim = True
            if result.informations.music is None:
                informations_trim = True

        if result.details is None:
            details_trim = True
        else:
            if result.details.clear_type is None or result.details.clear_type.current is None:
                details_trim = True
            if result.details.dj_level is None or result.details.dj_level.current is None:
                details_trim = True
            if result.details.score is None or result.details.score.current is None:
                details_trim = True
            if result.details.graphtarget is None:
                details_trim = True
            if result.details.graphtype == 'gauge' and result.details.options is None:
                details_trim = True

        if informations_trim:
            trim = image.crop(define.informations_trimarea)
            Thread(target=self._upload_image_to_bucket, args=('informations', object_name, trim,)).start()
        if details_trim:
            play_side = result.play_side
            trim = image.crop(define.details_trimarea[play_side])
            image_draw = ImageDraw.Draw(trim)
            image_draw.rectangle(result_rivalname_fillbox, fill=0)
            Thread(target=self._upload_image_to_bucket, args=('details', object_name, trim,)).start()

        return informations_trim, details_trim

    def start_uploadmusicselect(self, image):
        '''選曲画面の収集画像をアップロードする

        Args:
            image (Image): 対象のリザルト画像(PIL.Image)
        '''
        self.connect_client()
        if self.client is None:
            return

        object_name = f'{uuid1()}.png'

        trim = image.crop(define.musicselect_trimarea)
        image_draw = ImageDraw.Draw(trim)
        image_draw.rectangle(musicselect_rivals_fillbox, fill=0)
        Thread(target=self._upload_image_to_bucket, args=('musicselect', object_name, trim,)).start()

    def upload_resource(self, resourcename, targetfilepath):
        bucket = self._get_bucket('resources')
        if bucket is None:
            return

        try:
            blob = bucket.blob(resourcename)
            blob.upload_from_filename(targetfilepath)
            logger.debug(f'upload resource {targetfilepath}')
        except Exception as ex:
            logger.exception(ex)

    def get_resource_timestamp(self, resourcename):
        bucket = self._get_bucket('resources')
        if bucket is None:
            return None

        try:
            blob = bucket.get_blob(resourcename)
            if blob is None:
                return None

            return str(blob.updated)
        except Exception as ex:
            logger.exception(ex)

        return None

    def download_resource(self, resourcename, targetfilepath):
        bucket = self._get_bucket('resources')
        if bucket is None:
            return False

        blob = bucket.get_blob(resourcename)

        try:
            blob.download_to_filename(targetfilepath)
            logger.debug('download resource {targetfilepath}')
        except Exception as ex:
            logger.exception(ex)
            return False

        return True

    def download_discordwebhooks(self) -> dict[dict] | None:
        bucket = self._get_bucket('discordwebhooks')
        if bucket is None:
            return None

        list = {}

        blobs = self.client.list_blobs(BUCKET_NAMES['discordwebhooks'])
        for blob in blobs:
            blob: Blob = blob
            content = loads(blob.download_as_string())

            enddt = datetime.strptime(content['enddatetime'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            nowdt = datetime.now(timezone.utc)

            if nowdt < enddt:
                list[splitext(blob.name)[0]] = content
            else:
                # 終了日時を過ぎたファイルは削除する
                try:
                    blob.delete()
                except Exception:
                    pass


        return list

    def upload_discordwebhook(self, filename: str, value: dict) -> bool:
        '''
        イベント内容ファイルをアップロードする

        Args:
            filename(str): ファイル名
            value(dict): イベント内容
        Returns:
            bool: アップロードの成功
        '''
        bucket = self._get_bucket('discordwebhooks')
        if bucket is None:
            return False

        try:
            blob = bucket.blob(filename)
            blob.upload_from_string(dumps(value))
            logger.debug(f'upload discordwebhooks {filename}')
        except Exception as ex:
            logger.exception(ex)
            return False

        return True

    def save_image(self, basepath, blob: Blob):
        if not exists(basepath):
            mkdir(basepath)

        image_bytes = blob.download_as_bytes()
        image = Image.open(io.BytesIO(image_bytes))
        filepath = join(basepath, blob.name)
        image.save(filepath)

    def download_and_delete_all(self, basedir):
        self.connect_client()
        if self.client is None:
            print('connect client failed')
            return

        if not exists(basedir):
            mkdir(basedir)

        targets = [
            (BUCKET_NAMES['informations'], join(basedir, informations_dirname)),
            (BUCKET_NAMES['details'], join(basedir, details_dirname)),
            (BUCKET_NAMES['musicselect'], join(basedir, musicselect_dirname)),
        ]

        count = 0
        for bucket_name, dirpath in targets:
            blobs = self.client.list_blobs(bucket_name)
            for blob in blobs:
                self.save_image(dirpath, blob)
                blob.delete()
                count += 1

        print(f'download count: {count}')
