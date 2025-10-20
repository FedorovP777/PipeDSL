import logging
from typing import Tuple, Any, MutableMapping


class CustomAdapter(logging.LoggerAdapter[logging.Logger]):
    def process(
            self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> Tuple[str, MutableMapping[str, Any]]:
        if "extra" in kwargs:
            return f"{msg} [{kwargs.get('extra')}]", kwargs
        return msg, kwargs


base_logger = logging.getLogger("App")
formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
base_logger.addHandler(ch)
base_logger.setLevel(logging.DEBUG)

logger: CustomAdapter = CustomAdapter(base_logger)
