from kombu import Connection, Exchange, Queue

from fxci_etl.config import Config
from fxci_etl.pulse.handlers.base import PulseHandler, handlers


def get_connection(config: Config):
    pulse = config.pulse
    return Connection(
        hostname=pulse.host,
        port=pulse.port,
        userid=pulse.user,
        password=pulse.password,
        ssl=True,
    )


def get_consumer(
    config: Config, connection: Connection, name: str, callbacks: list[PulseHandler]
):
    pulse = config.pulse
    qconf = pulse.queues[name]
    exchange = Exchange(qconf.exchange, type="topic")
    exchange(connection).declare(
        passive=True
    )  # raise an error if exchange doesn't exist

    queue = Queue(
        name=f"queue/{pulse.user}/{name}",
        exchange=exchange,
        routing_key=qconf.routing_key,
        durable=qconf.durable,
        exclusive=False,
        auto_delete=qconf.auto_delete,
    )

    consumer = connection.Consumer(queue, auto_declare=False, callbacks=callbacks)
    consumer.queues[0].queue_declare()
    consumer.queues[0].queue_bind()
    return consumer


def listen(config: Config, name: str):
    callbacks = [
        cls(config, buffered=False)
        for name, cls in handlers.items()
        if config.etl.handlers is None or name in config.etl.handlers
    ]
    with get_connection(config) as connection:
        with get_consumer(config, connection, name, callbacks):
            while True:
                try:
                    connection.drain_events(timeout=None)
                except TimeoutError:
                    pass


def drain(config: Config, name: str):
    callbacks = [
        cls(config, buffered=True)
        for name, cls in handlers.items()
        if config.etl.handlers is None or name in config.etl.handlers
    ]
    with get_connection(config) as connection:
        with get_consumer(config, connection, name, callbacks):
            connection.drain_events(timeout=0)

    for callback in callbacks:
        callback.process_events()
