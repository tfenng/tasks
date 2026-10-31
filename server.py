import uvicorn

from config import configs
from utils.log_util import log, set_component

SETTINGS = configs()

if __name__ == "__main__":
    set_component(f"tasks")
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s | %(levelname)s    | panorama | %(message)s"
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelname)s    | panorama | %(message)s"
    log().info("Server is Starting")
    uvicorn.run(f"main:app", host="0.0.0.0", port=8080, reload=True, log_config=log_config)

