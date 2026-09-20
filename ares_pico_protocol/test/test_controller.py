import pytest

from ares_pico_protocol.controller import CommandError, LedController


def pixels(frame):
    return [tuple(frame[index:index + 3]) for index in range(0, len(frame), 3)]


def test_single_uses_zero_based_inclusive_range():
    controller = LedController()
    frame = controller.apply_single([4, 1, 2, 255, 0, 0, 0, 0, 255])
    assert pixels(frame) == [
        (0, 0, 0),
        (255, 0, 0),
        (0, 0, 255),
        (0, 0, 0),
    ]


def test_segment_preserves_leds_outside_closed_range():
    controller = LedController()
    controller.apply_segment([5, 0, 4, 10, 20, 30])
    frame = controller.apply_segment([5, 1, 3, 255, 0, 0])
    assert pixels(frame) == [
        (10, 20, 30),
        (255, 0, 0),
        (255, 0, 0),
        (255, 0, 0),
        (10, 20, 30),
    ]


def test_resize_preserves_overlap_and_blacks_new_leds():
    controller = LedController()
    controller.apply_segment([2, 0, 1, 1, 2, 3])
    frame = controller.apply_segment([4, 2, 2, 9, 8, 7])
    assert pixels(frame) == [
        (1, 2, 3),
        (1, 2, 3),
        (9, 8, 7),
        (0, 0, 0),
    ]


def test_manual_command_stops_animation():
    controller = LedController()
    controller.start_animation([10, 0, 9, 1])
    assert controller.animation is not None
    controller.apply_segment([10, 2, 4, 1, 2, 3])
    assert controller.animation is None


@pytest.mark.parametrize('effect', range(1, 11))
def test_all_default_animations_generate_a_frame(effect):
    controller = LedController()
    controller.start_animation([20, 3, 16, effect])
    frame = controller.tick()
    assert frame is not None
    assert len(frame) == 60


def test_animation_zero_stops_and_holds():
    controller = LedController()
    controller.start_animation([8, 0, 7, 3])
    shown = controller.tick()
    held = controller.start_animation([8, 0, 7, 0])
    assert held == shown
    assert controller.tick() is None


@pytest.mark.parametrize(
    'command',
    [
        [0, 0, 0, 1, 2, 3],
        [5, -1, 2, 1, 2, 3],
        [5, 3, 2, 1, 2, 3],
        [5, 0, 5, 1, 2, 3],
        [5, 0, 1, 256, 0, 0],
    ],
)
def test_invalid_segment_is_rejected(command):
    controller = LedController()
    with pytest.raises(CommandError):
        controller.apply_segment(command)


def test_single_length_is_strict():
    controller = LedController()
    with pytest.raises(CommandError, match='length'):
        controller.apply_single([3, 0, 1, 255, 0, 0])


def test_animation_parameter_validation():
    controller = LedController()
    controller.start_animation([10, 0, 9, 1, 10, 20, 30, 2])
    assert controller.animation.params == (10, 20, 30, 2)
    with pytest.raises(CommandError, match='direction'):
        controller.start_animation([10, 0, 9, 8, 10, 20, 30, 0])
