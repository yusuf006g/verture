import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    translate_source: str = os.getenv("TRANSLATE_SOURCE", "en")
    translate_target: str = os.getenv("TRANSLATE_TARGET", "ru")
    database_path: str = os.getenv("DATABASE_PATH", "data/loads.db")
    export_path: str = os.getenv("EXPORT_PATH", "data/loads.xlsx")
    # Доля диспетчера в процентах от ставки (1.8 = 1.8%)
    dispatcher_percent: float = float(os.getenv("DISPATCHER_PERCENT", "1.8"))


settings = Settings()
Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
Path(settings.export_path).parent.mkdir(parents=True, exist_ok=True)