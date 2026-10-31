import os

from buska_core.config import Settings as CoreSettings


class Settings(CoreSettings):
    def __init__(self) -> None:
        super().__init__()
        self.APP_DOWNLOAD_URL = os.getenv("APP_DOWNLOAD_URL", "")
