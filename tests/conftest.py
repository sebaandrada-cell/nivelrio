from datetime import datetime, timezone

import pytest

from modelo import Estacion, Umbrales


def make_estacion(**kw):
    base = dict(
        id="x", rio="Rio", nombre="Estacion", cuenca="C", fuente="aca", muestreo_min=5,
        umbrales=Umbrales(10.0, 20.0, 40.0, "estimado"), componente="000000-000", id_cha=None,
        lat=41.4, lon=2.2, zona="barcelona",
    )
    base.update(kw)
    return Estacion(**base)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def estacion():
    return make_estacion()
