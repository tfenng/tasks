from functools import lru_cache

from pydantic import BaseSettings, validator


class Config(BaseSettings):
    # DAO settings
    POSTGIS_DATABASE_URL: str = "postgresql://hkd:hkd@192.168.1.66:5432/hkd"
    POSTGIS_DATABASE_POOL_SIZE: int = 10
    POSTGIS_DATABASE_POOL_RECYCLE: int = 3600
    POSTGIS_DATABASE_PRINT_SQL: bool = False

    # aws
    # aws_s3_access_key_id: str = "minio123"
    # aws_s3_secret_access_key: str = "minio123"
    # aws_s3_endpoint: str = "192.168.1.31:9000"
    # aws_s3_https: str = "NO"



def set_env():
    config = Config()
    # os.environ["AWS_ACCESS_KEY_ID"] = config.aws_s3_access_key_id
    # os.environ["AWS_SECRET_ACCESS_KEY"] = config.aws_s3_secret_access_key
    # os.environ["AWS_S3_ENDPOINT"] = config.aws_s3_endpoint
    # os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
    # os.environ["AWS_HTTPS"] = config.aws_s3_https
    return config


@lru_cache()
def configs():
    return set_env()


if __name__ == '__main__':
    #os.environ["ai_process_parallel_num_building"] = ''
    pass
