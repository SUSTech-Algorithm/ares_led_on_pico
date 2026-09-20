from ares_led_demo.demo import main


def test_demo_entry_point_is_callable():
    assert callable(main)
