from mahjong_env.selfplay import parse_py_spec


def test_plain_class():
    assert parse_py_spec("py:mjbots.online:CoachPlayer") == ("mjbots.online", "CoachPlayer", {})


def test_keyword_arguments():
    module, cls, kw = parse_py_spec("py:mybots.nn:NetPlayer?model=/models/v2.onnx;temperature=0.5;greedy=true;n=3")
    assert (module, cls) == ("mybots.nn", "NetPlayer")
    assert kw == {"model": "/models/v2.onnx", "temperature": 0.5, "greedy": True, "n": 3}
