import logging

# Setup logging
log        = logging.getLogger('ryu.app.rfproxy')
handler    = logging.StreamHandler()
log_format = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
formatter  = logging.Formatter(log_format, '%b %d %H:%M:%S')
handler.setFormatter(formatter)
log.addHandler(handler)
log.propagate = 0
log.setLevel(logging.INFO)
