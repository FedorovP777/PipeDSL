import logging


class CustomAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        if "extra" in kwargs:
            return "%s [%s]" % (msg, kwargs.get("extra")), kwargs
        return "%s" % (msg,), kwargs


logger = logging.getLogger("App")
formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = CustomAdapter(logger)
logger.setLevel(logging.DEBUG)
